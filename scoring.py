"""
scoring.py - Explainable Name Matching Score for PhoneInfo

This module provides a decomposed, auditable scoring formula for matching
a customer's claimed name against phone-owner names returned by ME/SYNC APIs.

The score is designed to be:
1. EXPLAINABLE - each component has a clear reason and weight
2. ADJUSTABLE - all weights/thresholds are in scoring_config.json
3. AUDITABLE - every score comes with a breakdown showing exactly why

Usage:
    from scoring import ScoreEngine

    engine = ScoreEngine(db_conn)  # or ScoreEngine(db_conn, config_path="custom.json")
    result = engine.score_match(cal_name="חביבה פראס", api_first="Havi", api_last="Prass")

    print(result["final_score"])        # 0-100
    print(result["risk_tier"])          # "HIGH" / "MEDIUM" / "LOW" / "VERY LOW"
    print(result["breakdown"])          # detailed audit dict
    print(result["explanation"])        # human-readable string

Author: PhoneInfo / Cal Risk Department
"""

import json
import os
from fuzzywuzzy import fuzz
from functions import (
    transliterate_name,
    is_hebrew,
    detect_language,
    get_all_nicknames_for_name,
)


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scoring_config.json")

def load_config(config_path=None):
    """Load scoring configuration from JSON file."""
    path = config_path or _DEFAULT_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Return sensible defaults if config file is missing
        return _default_config()


def _default_config():
    """Fallback defaults if scoring_config.json is missing."""
    return {
        "weights": {"last_name": 0.65, "first_name": 0.35},
        "match_types": {
            "exact": 100, "nickname": 90, "transliteration_exact": 95,
            "transliteration_fuzzy_high": 80, "fuzzy_high": 75,
            "fuzzy_medium": 50, "fuzzy_low": 25, "no_match": 0,
        },
        "fuzzy_thresholds": {"high": 85, "medium": 65, "low": 45},
        "risk_tiers": {
            "high_confidence":   {"min": 85, "label": "HIGH"},
            "medium_confidence": {"min": 60, "label": "MEDIUM"},
            "low_confidence":    {"min": 35, "label": "LOW"},
            "no_match":          {"min": 0,  "label": "VERY LOW"},
        },
        "bonuses": {"both_names_exact": 5, "multi_api_agreement": 5},
        "penalties": {"only_first_name_match": -10},
    }


# ---------------------------------------------------------------------------
# Single-name component matcher
# ---------------------------------------------------------------------------

def _match_single_word_internal(cal_word, api_word, conn, config):
    """
    Internal helper to match a single word (no word splitting).
    Used for both first names and individual last name words.
    """
    mt = config["match_types"]
    ft = config["fuzzy_thresholds"]

    cal_clean = cal_word.strip()
    api_clean = api_word.strip()

    # --- 1. Exact match ---
    if cal_clean == api_clean:
        return {
            "score": mt["exact"],
            "match_type": "exact",
            "details": f"exact"
        }

    # --- 2. Transliteration + exact ---
    api_transliterated = _transliterate_if_needed(api_clean)
    cal_transliterated = _transliterate_if_needed(cal_clean)

    if api_transliterated and api_transliterated == cal_clean:
        return {
            "score": mt["transliteration_exact"],
            "match_type": "transliteration_exact",
            "details": f"transliteration exact"
        }
    if cal_transliterated and cal_transliterated == api_clean:
        return {
            "score": mt["transliteration_exact"],
            "match_type": "transliteration_exact",
            "details": f"transliteration exact"
        }

    # --- 3. Transliteration + fuzzy ---
    best_transliteration_score = 0

    if api_transliterated and api_transliterated != api_clean:
        score = fuzz.ratio(cal_clean, api_transliterated)
        if score > best_transliteration_score:
            best_transliteration_score = score

    if cal_transliterated and cal_transliterated != cal_clean:
        score = fuzz.ratio(cal_transliterated, api_clean)
        if score > best_transliteration_score:
            best_transliteration_score = score

    if api_transliterated and cal_transliterated:
        score = fuzz.ratio(cal_transliterated, api_transliterated)
        if score > best_transliteration_score:
            best_transliteration_score = score

    # --- 4. Direct fuzzy match ---
    direct_fuzzy = fuzz.ratio(cal_clean, api_clean)
    best_fuzzy = max(direct_fuzzy, best_transliteration_score)

    # Classify based on best fuzzy score
    if best_fuzzy >= ft["high"]:
        if best_transliteration_score > direct_fuzzy:
            return {
                "score": mt["transliteration_fuzzy_high"],
                "match_type": "transliteration_fuzzy_high",
                "details": f"fuzzy {best_fuzzy}%"
            }
        else:
            return {
                "score": mt["fuzzy_high"],
                "match_type": "fuzzy_high",
                "details": f"fuzzy {best_fuzzy}%"
            }
    elif best_fuzzy >= ft["medium"]:
        return {
            "score": mt["fuzzy_medium"],
            "match_type": "fuzzy_medium",
            "details": f"fuzzy {best_fuzzy}%"
        }
    elif best_fuzzy >= ft["low"]:
        return {
            "score": mt["fuzzy_low"],
            "match_type": "fuzzy_low",
            "details": f"fuzzy {best_fuzzy}%"
        }
    else:
        return {
            "score": mt["no_match"],
            "match_type": "no_match",
            "details": f"fuzzy {best_fuzzy}%"
        }


def _match_single_name(cal_word, api_word, conn, config, is_first_name=True):
    """
    Score how well a single name component matches.

    For last names: splits into words and finds best word-to-word match
    For first names: uses full name matching with nicknames

    Tries matching strategies in order of confidence:
    1. Exact match (after normalization)
    2. Nickname match (via nicknames DB)
    3. Transliteration + exact match
    4. Transliteration + fuzzy match
    5. Direct fuzzy match

    Returns:
        dict with keys: score (0-100), match_type (str), details (str)
    """
    if not cal_word or not api_word:
        return {"score": 0, "match_type": "no_match", "details": "Empty name"}

    mt = config["match_types"]
    ft = config["fuzzy_thresholds"]

    cal_clean = cal_word.strip()
    api_clean = api_word.strip()

    # --- WORD-BY-WORD MATCHING FOR LAST NAMES ---
    # If it's a last name, split into words and find best match
    if not is_first_name:
        # Split into words (handles "טלמור - נקניקיות", "כהן לוי", etc.)
        cal_words = [w.strip() for w in cal_clean.split() if w.strip() and len(w.strip()) > 1]
        api_words = [w.strip() for w in api_clean.split() if w.strip() and len(w.strip()) > 1]

        if not cal_words or not api_words:
            return {"score": 0, "match_type": "no_match", "details": "No valid words in last name"}

        # Try matching each cal word against each api word
        best_result = {"score": 0, "match_type": "no_match", "details": ""}

        for cal_w in cal_words:
            for api_w in api_words:
                # Skip common suffixes/prefixes
                if api_w in ['-', '–', '—', 'בע"מ', 'בעמ', 'ltd', 'בע״מ']:
                    continue

                # Recursively call this function for single-word comparison
                # (but mark as first_name=True to use the regular matching logic)
                result = _match_single_word_internal(cal_w, api_w, conn, config)

                if result["score"] > best_result["score"]:
                    best_result = result
                    # Update details to show which words matched
                    best_result["details"] = f"Last name word match: '{cal_w}' ~ '{api_w}' → {result['details']}"

        return best_result

    # --- REGULAR MATCHING FOR FIRST NAMES ---
    # For first names, use the full logic including nicknames

    # --- 1. Exact match ---
    if cal_clean == api_clean:
        return {
            "score": mt["exact"],
            "match_type": "exact",
            "details": f"'{cal_clean}' == '{api_clean}'"
        }

    # --- 2. Nickname match (only for first names) ---
    if is_first_name and conn:
        cal_variants = set(get_all_nicknames_for_name(conn, cal_clean))
        api_variants = set(get_all_nicknames_for_name(conn, api_clean))

        # Also try transliterated api_word for nickname lookup
        api_transliterated = _transliterate_if_needed(api_clean)
        if api_transliterated and api_transliterated != api_clean:
            api_variants.update(get_all_nicknames_for_name(conn, api_transliterated))

        # Check if any variant from cal_name overlaps with api variants
        overlap = cal_variants & api_variants
        if overlap:
            return {
                "score": mt["nickname"],
                "match_type": "nickname",
                "details": f"'{cal_clean}' ↔ '{api_clean}' via nickname(s): {', '.join(sorted(overlap))}"
            }

        # Check if transliterated API name is in cal_name's variants
        if api_transliterated in cal_variants:
            return {
                "score": mt["nickname"],
                "match_type": "nickname",
                "details": f"'{cal_clean}' ↔ '{api_clean}' (transliterated: '{api_transliterated}') via nicknames"
            }

    # --- 3. Transliteration + exact ---
    api_transliterated = _transliterate_if_needed(api_clean)
    cal_transliterated = _transliterate_if_needed(cal_clean)

    # Try both directions
    if api_transliterated and api_transliterated == cal_clean:
        return {
            "score": mt["transliteration_exact"],
            "match_type": "transliteration_exact",
            "details": f"'{api_clean}' → '{api_transliterated}' == '{cal_clean}'"
        }
    if cal_transliterated and cal_transliterated == api_clean:
        return {
            "score": mt["transliteration_exact"],
            "match_type": "transliteration_exact",
            "details": f"'{cal_clean}' → '{cal_transliterated}' == '{api_clean}'"
        }

    # --- 4. Transliteration + fuzzy ---
    best_transliteration_score = 0
    best_transliteration_detail = ""

    if api_transliterated and api_transliterated != api_clean:
        score = fuzz.ratio(cal_clean, api_transliterated)
        if score > best_transliteration_score:
            best_transliteration_score = score
            best_transliteration_detail = f"'{cal_clean}' ~ '{api_transliterated}' (from '{api_clean}') = {score}%"

    if cal_transliterated and cal_transliterated != cal_clean:
        score = fuzz.ratio(cal_transliterated, api_clean)
        if score > best_transliteration_score:
            best_transliteration_score = score
            best_transliteration_detail = f"'{cal_transliterated}' (from '{cal_clean}') ~ '{api_clean}' = {score}%"

    # Also compare both transliterated forms
    if api_transliterated and cal_transliterated:
        score = fuzz.ratio(cal_transliterated, api_transliterated)
        if score > best_transliteration_score:
            best_transliteration_score = score
            best_transliteration_detail = f"'{cal_transliterated}' ~ '{api_transliterated}' = {score}%"

    if best_transliteration_score >= ft["high"]:
        return {
            "score": mt["transliteration_fuzzy_high"],
            "match_type": "transliteration_fuzzy_high",
            "details": best_transliteration_detail
        }

    # --- 5. Direct fuzzy match ---
    direct_fuzzy = fuzz.ratio(cal_clean, api_clean)
    if direct_fuzzy >= ft["high"]:
        return {
            "score": mt["fuzzy_high"],
            "match_type": "fuzzy_high",
            "details": f"'{cal_clean}' ~ '{api_clean}' = {direct_fuzzy}%"
        }

    # Use best of transliteration fuzzy and direct fuzzy
    best_fuzzy = max(direct_fuzzy, best_transliteration_score)
    best_detail = (
        best_transliteration_detail if best_transliteration_score > direct_fuzzy
        else f"'{cal_clean}' ~ '{api_clean}' = {direct_fuzzy}%"
    )

    if best_fuzzy >= ft["medium"]:
        return {
            "score": mt["fuzzy_medium"],
            "match_type": "fuzzy_medium",
            "details": best_detail
        }
    elif best_fuzzy >= ft["low"]:
        return {
            "score": mt["fuzzy_low"],
            "match_type": "fuzzy_low",
            "details": best_detail
        }
    else:
        return {
            "score": mt["no_match"],
            "match_type": "no_match",
            "details": f"Best match: {best_detail}" if best_detail else f"'{cal_clean}' vs '{api_clean}' = {direct_fuzzy}%"
        }


def _transliterate_if_needed(word):
    """Transliterate a word to Hebrew if it's not already Hebrew."""
    if not word:
        return ""
    lang = detect_language(word)
    if lang == "he":
        return word  # Already Hebrew
    return transliterate_name(word)


# ---------------------------------------------------------------------------
# Main scoring engine
# ---------------------------------------------------------------------------

class ScoreEngine:
    """
    Explainable name matching engine.

    Separates first and last name matching, applies configurable weights,
    and produces an auditable breakdown for every score.
    """

    def __init__(self, conn=None, config_path=None):
        """
        Args:
            conn: SQLite connection (for nickname lookups). Can be None.
            config_path: Path to scoring_config.json. Uses default if None.
        """
        self.conn = conn
        self.config = load_config(config_path)

    def score_match(self, cal_name, api_first="", api_last="", api_common_name="",
                    api_source="ME"):
        """
        Score how well cal_name matches an API result.

        Args:
            cal_name: Customer's claimed name (Hebrew, e.g., "חביבה פראס")
            api_first: First name from API result
            api_last: Last name from API result
            api_common_name: Common/display name from API (used as fallback)
            api_source: "ME" or "SYNC" (for audit trail)

        Returns:
            dict with: final_score, risk_tier, risk_action, breakdown, explanation
        """
        # Parse cal_name into first/last
        cal_parts = cal_name.strip().split() if cal_name else []
        if len(cal_parts) >= 2:
            cal_last = cal_parts[-1]
            cal_first_parts = cal_parts[:-1]
            cal_first = " ".join(cal_first_parts)
        elif len(cal_parts) == 1:
            cal_first = cal_parts[0]
            cal_last = ""
        else:
            return self._empty_result("Empty customer name")

        # Parse api_common_name as fallback
        api_common_parts = api_common_name.strip().split() if api_common_name else []
        if not api_first and api_common_parts:
            api_first = api_common_parts[0]
        if not api_last and len(api_common_parts) >= 2:
            api_last = " ".join(api_common_parts[1:])

        if not api_first and not api_last:
            return self._empty_result("No name returned from API")

        weights = self.config["weights"]
        bonuses = self.config.get("bonuses", {})
        penalties = self.config.get("penalties", {})

        # --- Score last name ---
        if cal_last and api_last:
            last_result = _match_single_name(
                cal_last, api_last, self.conn, self.config, is_first_name=False
            )
        elif not cal_last:
            last_result = {"score": 0, "match_type": "no_input", "details": "No last name provided by customer"}
        else:
            last_result = {"score": 0, "match_type": "no_api_data", "details": "No last name from API"}

        # --- Score first name (try each cal_first_part for best match) ---
        if cal_first and api_first:
            # If customer has multiple first names (e.g., "מרי חביבה"),
            # try each part and take the best
            best_first_result = {"score": 0, "match_type": "no_match", "details": ""}
            for part in cal_first_parts:
                result = _match_single_name(
                    part, api_first, self.conn, self.config, is_first_name=True
                )
                if result["score"] > best_first_result["score"]:
                    best_first_result = result

            # Also try matching against common_name first word if different from api_first
            if api_common_parts and api_common_parts[0] != api_first:
                for part in cal_first_parts:
                    result = _match_single_name(
                        part, api_common_parts[0], self.conn, self.config, is_first_name=True
                    )
                    if result["score"] > best_first_result["score"]:
                        best_first_result = result

            first_result = best_first_result
        elif not cal_first:
            first_result = {"score": 0, "match_type": "no_input", "details": "No first name provided"}
        else:
            first_result = {"score": 0, "match_type": "no_api_data", "details": "No first name from API"}

        # --- Weighted combination ---
        w_last = weights["last_name"]
        w_first = weights["first_name"]

        # Handle missing components: if one side is missing, give full weight to the other
        if not cal_last or (not api_last and not api_common_name):
            # No last name to compare — score is first-name only
            base_score = first_result["score"]
        elif not cal_first:
            base_score = last_result["score"]
        else:
            base_score = (last_result["score"] * w_last) + (first_result["score"] * w_first)

        # --- Bonuses ---
        bonus = 0
        bonus_reasons = []

        exact_types = {"exact", "transliteration_exact", "nickname"}
        if (first_result["match_type"] in exact_types and last_result["match_type"] in exact_types):
            b = bonuses.get("both_names_exact", 5)
            bonus += b
            bonus_reasons.append(f"+{b} both names exact match")

        # --- Penalties ---
        penalty = 0
        penalty_reasons = []

        if (first_result["score"] >= 75 and last_result["score"] == 0
                and cal_last and api_last):
            p = abs(penalties.get("only_first_name_match", -10))
            penalty += p
            penalty_reasons.append(f"-{p} first name matches but last name doesn't (weak evidence)")

        # --- Final score ---
        final_score = max(0, min(100, int(base_score + bonus - penalty)))

        # --- Risk tier ---
        tier = self._get_risk_tier(final_score)

        # --- Build explanation ---
        explanation = self._build_explanation(
            cal_name, api_first, api_last, api_common_name, api_source,
            first_result, last_result, w_first, w_last,
            bonus, bonus_reasons, penalty, penalty_reasons,
            final_score, tier
        )

        return {
            "final_score": final_score,
            "risk_tier": tier["label"],
            "risk_action": tier.get("action", ""),
            "breakdown": {
                "cal_name": cal_name,
                "api_source": api_source,
                "api_first": api_first,
                "api_last": api_last,
                "api_common_name": api_common_name,
                "first_name": {
                    "score": first_result["score"],
                    "match_type": first_result["match_type"],
                    "weight": w_first,
                    "weighted_score": round(first_result["score"] * w_first, 1),
                    "details": first_result["details"],
                },
                "last_name": {
                    "score": last_result["score"],
                    "match_type": last_result["match_type"],
                    "weight": w_last,
                    "weighted_score": round(last_result["score"] * w_last, 1),
                    "details": last_result["details"],
                },
                "base_score": round(base_score, 1),
                "bonus": bonus,
                "bonus_reasons": bonus_reasons,
                "penalty": penalty,
                "penalty_reasons": penalty_reasons,
            },
            "explanation": explanation,
        }

    def score_multi_api(self, cal_name, me_result=None, sync_result=None):
        """
        Score across multiple API sources and combine results.

        Args:
            cal_name: Customer's claimed name
            me_result: dict with keys: first_name, last_name, common_name (from ME API)
            sync_result: dict with keys: first_name, last_name (from SYNC API)

        Returns:
            dict with: final_score, risk_tier, me_score, sync_score, combined_explanation
        """
        results = {}

        if me_result and (me_result.get("first_name") or me_result.get("last_name") or me_result.get("common_name")):
            me_score = self.score_match(
                cal_name,
                api_first=me_result.get("first_name", ""),
                api_last=me_result.get("last_name", ""),
                api_common_name=me_result.get("common_name", ""),
                api_source="ME"
            )
            results["me"] = me_score

        if sync_result and (sync_result.get("first_name") or sync_result.get("last_name")):
            sync_score = self.score_match(
                cal_name,
                api_first=sync_result.get("first_name", ""),
                api_last=sync_result.get("last_name", ""),
                api_source="SYNC"
            )
            results["sync"] = sync_score

        if not results:
            return self._empty_result("No API data available")

        # Take the best score as primary
        best_key = max(results, key=lambda k: results[k]["final_score"])
        best = results[best_key]
        final_score = best["final_score"]

        # Multi-API agreement bonus
        if len(results) == 2:
            me_s = results["me"]["final_score"]
            sync_s = results["sync"]["final_score"]
            if me_s >= 60 and sync_s >= 60:
                agreement_bonus = self.config.get("bonuses", {}).get("multi_api_agreement", 5)
                final_score = min(100, final_score + agreement_bonus)

        tier = self._get_risk_tier(final_score)

        return {
            "final_score": final_score,
            "risk_tier": tier["label"],
            "risk_action": tier.get("action", ""),
            "best_source": best_key.upper(),
            "me_score": results.get("me", {}).get("final_score"),
            "sync_score": results.get("sync", {}).get("final_score"),
            "me_breakdown": results.get("me", {}).get("breakdown"),
            "sync_breakdown": results.get("sync", {}).get("breakdown"),
            "me_explanation": results.get("me", {}).get("explanation", ""),
            "sync_explanation": results.get("sync", {}).get("explanation", ""),
        }

    def _get_risk_tier(self, score):
        """Map a score to a risk tier from config."""
        tiers = self.config["risk_tiers"]
        for tier_key in ["high_confidence", "medium_confidence", "low_confidence", "no_match"]:
            tier = tiers[tier_key]
            if score >= tier["min"]:
                return tier
        return tiers["no_match"]

    def _empty_result(self, reason):
        """Return a zero-score result with explanation."""
        return {
            "final_score": 0,
            "risk_tier": "VERY LOW",
            "risk_action": "High risk - no data to verify identity",
            "breakdown": {"reason": reason},
            "explanation": f"Score: 0 — {reason}",
        }

    def _build_explanation(self, cal_name, api_first, api_last, api_common_name,
                           api_source, first_result, last_result,
                           w_first, w_last, bonus, bonus_reasons,
                           penalty, penalty_reasons, final_score, tier):
        """Build a human-readable explanation string for audit purposes."""
        lines = []
        lines.append(f"Customer: {cal_name}")
        api_display = f"{api_first} {api_last}".strip() or api_common_name
        lines.append(f"{api_source} API returned: {api_display}")
        lines.append("")

        lines.append(f"Last name: {last_result['details']}")
        lines.append(f"  → {last_result['match_type']} → score {last_result['score']} × weight {w_last} = {round(last_result['score'] * w_last, 1)}")
        lines.append("")

        lines.append(f"First name: {first_result['details']}")
        lines.append(f"  → {first_result['match_type']} → score {first_result['score']} × weight {w_first} = {round(first_result['score'] * w_first, 1)}")
        lines.append("")

        base = round(last_result['score'] * w_last + first_result['score'] * w_first, 1)
        lines.append(f"Base score: {base}")

        if bonus_reasons:
            for r in bonus_reasons:
                lines.append(f"Bonus: {r}")
        if penalty_reasons:
            for r in penalty_reasons:
                lines.append(f"Penalty: {r}")

        lines.append(f"Final score: {final_score} → {tier['label']}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backward-compatible wrapper
# ---------------------------------------------------------------------------

def calculate_similarity_v2(cal_name, api_first, api_last, api_common_name, conn,
                            config_path=None):
    """
    Drop-in replacement for the old calculate_similarity function.
    Returns an integer score 0-100 for backward compatibility.

    For the full breakdown, use ScoreEngine directly.
    """
    engine = ScoreEngine(conn=conn, config_path=config_path)
    result = engine.score_match(
        cal_name=cal_name,
        api_first=api_first,
        api_last=api_last,
        api_common_name=api_common_name
    )
    return result["final_score"]
