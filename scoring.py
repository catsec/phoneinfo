"""
scoring.py - Word-Bag Name Matching Score for PhoneInfo

Compares all words from the customer's claimed name (cal_name) against all
words from the API result. No first/last name distinction.

Rule: if 2+ words match → score 100 (HIGH confidence).

Usage:
    from scoring import ScoreEngine

    engine = ScoreEngine(db_conn)
    result = engine.score_match(cal_name="חביבה פראס", api_first="Havi", api_last="Prass")

    print(result["final_score"])        # 0-100
    print(result["risk_tier"])          # "HIGH" / "MEDIUM" / "LOW" / "VERY LOW"
    print(result["breakdown"])          # detailed audit dict
    print(result["explanation"])        # human-readable string
"""

import json
import os
from fuzzywuzzy import fuzz
from transliteration import transliterate_name, is_hebrew, detect_language
from db import get_all_nicknames_for_name


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
        return _default_config()


def _default_config():
    """Fallback defaults if scoring_config.json is missing."""
    return {
        "word_match_threshold": 75,
        "match_types": {
            "exact": 100, "nickname": 100, "transliteration_exact": 100,
            "transliteration_fuzzy_high": 80, "fuzzy_high": 75,
            "fuzzy_medium": 50, "fuzzy_low": 25, "no_match": 0,
        },
        "fuzzy_thresholds": {"high": 75, "medium": 60, "low": 40},
        "risk_tiers": {
            "high_confidence":   {"min": 85, "label": "HIGH"},
            "medium_confidence": {"min": 60, "label": "MEDIUM"},
            "low_confidence":    {"min": 35, "label": "LOW"},
            "no_match":          {"min": 0,  "label": "VERY LOW"},
        },
        "bonuses": {"multi_api_agreement": 5},
    }


# ---------------------------------------------------------------------------
# Word-level matcher
# ---------------------------------------------------------------------------

def _match_word(cal_word, api_word, conn, config, use_nicknames=True):
    """
    Match a single word from cal_name against a single word from API result.

    Tries strategies in order of confidence:
    1. Exact match
    2. Nickname match (via nicknames DB) — only when use_nicknames=True
    3. Transliteration + exact match
    4. Transliteration + fuzzy match
    5. Direct fuzzy match

    Returns:
        dict with keys: score (0-100), match_type (str), details (str)
    """
    if not cal_word or not api_word:
        return {"score": 0, "match_type": "no_match", "details": "empty"}

    mt = config["match_types"]
    ft = config["fuzzy_thresholds"]

    cal_clean = cal_word.strip()
    api_clean = api_word.strip()

    # --- 1. Exact match ---
    if cal_clean == api_clean:
        return {"score": mt["exact"], "match_type": "exact", "details": "exact"}

    # --- 2. Nickname match (first word only) ---
    if use_nicknames and conn:
        cal_variants = set(get_all_nicknames_for_name(conn, cal_clean))
        api_variants = set(get_all_nicknames_for_name(conn, api_clean))

        api_transliterated = _transliterate_if_needed(api_clean)
        if api_transliterated and api_transliterated != api_clean:
            api_variants.update(get_all_nicknames_for_name(conn, api_transliterated))

        overlap = cal_variants & api_variants
        if overlap:
            return {
                "score": mt["nickname"],
                "match_type": "nickname",
                "details": f"nickname: {', '.join(sorted(overlap))}",
            }

        if api_transliterated in cal_variants:
            return {
                "score": mt["nickname"],
                "match_type": "nickname",
                "details": "nickname via transliteration",
            }

    # --- 3. Transliteration + exact ---
    api_transliterated = _transliterate_if_needed(api_clean)
    cal_transliterated = _transliterate_if_needed(cal_clean)

    if api_transliterated and api_transliterated == cal_clean:
        return {"score": mt["transliteration_exact"], "match_type": "transliteration_exact", "details": "transliteration exact"}
    if cal_transliterated and cal_transliterated == api_clean:
        return {"score": mt["transliteration_exact"], "match_type": "transliteration_exact", "details": "transliteration exact"}

    # --- 4. Transliteration + fuzzy ---
    best_trans_score = 0

    if api_transliterated and api_transliterated != api_clean:
        best_trans_score = max(best_trans_score, fuzz.ratio(cal_clean, api_transliterated))
    if cal_transliterated and cal_transliterated != cal_clean:
        best_trans_score = max(best_trans_score, fuzz.ratio(cal_transliterated, api_clean))
    if api_transliterated and cal_transliterated:
        best_trans_score = max(best_trans_score, fuzz.ratio(cal_transliterated, api_transliterated))

    # --- 5. Direct fuzzy ---
    direct_fuzzy = fuzz.ratio(cal_clean, api_clean)
    best_fuzzy = max(direct_fuzzy, best_trans_score)

    if best_fuzzy >= ft["high"]:
        if best_trans_score > direct_fuzzy:
            return {"score": mt["transliteration_fuzzy_high"], "match_type": "transliteration_fuzzy_high", "details": f"fuzzy {best_fuzzy}%"}
        else:
            return {"score": mt["fuzzy_high"], "match_type": "fuzzy_high", "details": f"fuzzy {best_fuzzy}%"}
    elif best_fuzzy >= ft["medium"]:
        return {"score": mt["fuzzy_medium"], "match_type": "fuzzy_medium", "details": f"fuzzy {best_fuzzy}%"}
    elif best_fuzzy >= ft["low"]:
        return {"score": mt["fuzzy_low"], "match_type": "fuzzy_low", "details": f"fuzzy {best_fuzzy}%"}
    else:
        return {"score": mt["no_match"], "match_type": "no_match", "details": f"fuzzy {best_fuzzy}%"}


def _transliterate_if_needed(word):
    """Transliterate a word to Hebrew if it's not already Hebrew."""
    if not word:
        return ""
    lang = detect_language(word)
    if lang == "he":
        return word
    return transliterate_name(word)


def _extract_words(text):
    """Extract meaningful words from a name string."""
    if not text:
        return []
    skip = {'-', '–', '—', 'בע"מ', 'בעמ', 'ltd', 'בע״מ'}
    words = []
    for w in text.strip().split():
        w = w.strip()
        if w and len(w) > 1 and w.lower() not in skip:
            words.append(w)
    return words


# ---------------------------------------------------------------------------
# Main scoring engine
# ---------------------------------------------------------------------------

class ScoreEngine:
    """
    Word-bag name matching engine.

    Compares all words from cal_name against all words from API result.
    2+ word matches → score 100 (HIGH confidence).
    """

    def __init__(self, conn=None, config_path=None):
        self.conn = conn
        self.config = load_config(config_path)

    def score_match(self, cal_name, api_first="", api_last="", api_common_name="",
                    api_source="ME"):
        """
        Score how well cal_name matches an API result using word-bag matching.

        All words from cal_name are compared against all words from the API.
        If 2+ words match (score >= threshold), final score is 100.

        Args:
            cal_name: Customer's claimed name (e.g., "נטע לי כהן")
            api_first: First name from API result
            api_last: Last name from API result
            api_common_name: Common/display name from API (used as additional words)
            api_source: "ME" or "SYNC" (for audit trail)

        Returns:
            dict with: final_score, risk_tier, risk_action, breakdown, explanation
        """
        cal_words = _extract_words(cal_name)
        if not cal_words:
            return self._empty_result("Empty customer name")

        # Collect all API words from all name fields, deduplicated
        api_all_words = []
        for name_part in [api_first, api_last, api_common_name]:
            api_all_words.extend(_extract_words(name_part))
        api_all_words = list(dict.fromkeys(api_all_words))

        if not api_all_words:
            return self._empty_result("No name returned from API")

        threshold = self.config.get("word_match_threshold", 75)

        # Match each cal_word against best api_word
        # Nickname lookup only for the first word (typically the first name)
        word_results = []
        for i, cal_w in enumerate(cal_words):
            best = {"score": -1, "match_type": "no_match", "details": "", "api_word": ""}
            for api_w in api_all_words:
                result = _match_word(cal_w, api_w, self.conn, self.config, use_nicknames=(i == 0))
                if result["score"] > best["score"]:
                    best = {**result, "api_word": api_w}
            best["score"] = max(0, best["score"])
            word_results.append({"cal_word": cal_w, **best})

        # Count strong matches
        strong_matches = [m for m in word_results if m["score"] >= threshold]
        matched_count = len(strong_matches)

        # Determine final score
        if matched_count >= 2:
            final_score = 100
        elif matched_count == 1:
            final_score = 75
        else:
            # No strong matches — use best available score
            final_score = max((m["score"] for m in word_results), default=0)

        final_score = max(0, min(100, int(final_score)))
        tier = self._get_risk_tier(final_score)

        # Build explanation
        api_display = f"{api_first} {api_last}".strip() or api_common_name
        lines = [
            f"Customer: {cal_name}",
            f"{api_source} API: {api_display}",
            "",
        ]
        for m in word_results:
            marker = "+" if m["score"] >= threshold else "-"
            lines.append(f"  [{marker}] {m['cal_word']} ~ {m.get('api_word', '?')} → {m['match_type']} ({m['score']})")
        lines.append("")
        lines.append(f"Matched: {matched_count}/{len(cal_words)} words")
        lines.append(f"Final score: {final_score} → {tier['label']}")

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
                "word_matches": [
                    {
                        "cal_word": m["cal_word"],
                        "api_word": m.get("api_word", ""),
                        "score": m["score"],
                        "match_type": m["match_type"],
                        "details": m["details"],
                    }
                    for m in word_results
                ],
                "matched_count": matched_count,
                "threshold": threshold,
            },
            "explanation": "\n".join(lines),
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


# ---------------------------------------------------------------------------
# Backward-compatible wrapper
# ---------------------------------------------------------------------------

def calculate_similarity_v2(cal_name, api_first, api_last, api_common_name, conn,
                            config_path=None):
    """
    Drop-in replacement for the old calculate_similarity function.
    Returns an integer score 0-100 for backward compatibility.
    """
    engine = ScoreEngine(conn=conn, config_path=config_path)
    result = engine.score_match(
        cal_name=cal_name,
        api_first=api_first,
        api_last=api_last,
        api_common_name=api_common_name
    )
    return result["final_score"]
