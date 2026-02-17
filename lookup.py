"""
lookup.py - Generic phone lookup pipeline.

Provides provider-agnostic functions for the cache -> API -> save -> translate -> score
pipeline. Works with any provider implementing the BaseProvider interface.
"""

from datetime import datetime, timezone
from db import clean_data_for_db
from transliteration import transliterate_name, is_hebrew
from scoring import ScoreEngine


def check_cache_freshness(db_result, refresh_days, cache_only):
    """Check whether cached data should be used.

    Returns True if the cached data is fresh enough to use.
    """
    if cache_only:
        return True
    if refresh_days == 0:
        return False  # Always refresh
    api_call_time_str = db_result.get("api_call_time", "")
    if not api_call_time_str:
        return False
    api_call_time = datetime.fromisoformat(api_call_time_str)
    if api_call_time.tzinfo is None:
        api_call_time = api_call_time.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - api_call_time).days
    return age_days < refresh_days


def lookup(provider, db, phone, cal_name, refresh_days, cache_only=False, use_cache=True):
    """Look up phone using any provider: check cache, call API if needed, save to DB.

    Args:
        provider: BaseProvider instance
        db: SQLite connection
        phone: Phone number (international format)
        cal_name: Contact name for matching
        refresh_days: Refresh entries older than N days (0 = always refresh)
        cache_only: If True, never call API — return cache or "NOT IN CACHE"
        use_cache: If False, skip cache check entirely and always call API

    Returns: (result_dict, api_called, from_cache)
    """
    # Check cache first (if enabled)
    if use_cache:
        db_result = provider.get_from_cache(db, phone)

        if db_result and check_cache_freshness(db_result, refresh_days, cache_only):
            # Update cal_name if different
            if cal_name and db_result.get("cal_name") != cal_name:
                db_result["cal_name"] = cal_name
                result = provider.cache_to_result(db_result)
                result["phone_number"] = phone
                result["cal_name"] = cal_name
                result[f"{provider.name}.api_call_time"] = db_result.get("api_call_time", "")
                provider.save_to_cache(db, phone, cal_name, result)
            else:
                result = provider.cache_to_result(db_result)
                result["phone_number"] = phone
                result["cal_name"] = cal_name or db_result.get("cal_name", "")

            return result, False, True

    # Cache-only mode but nothing in cache (or cache disabled)
    if cache_only:
        result = clean_data_for_db(provider.empty_result())
        result["phone_number"] = phone
        result["cal_name"] = cal_name
        primary_key = provider.get_primary_name_key()
        result[primary_key] = "NOT IN CACHE"
        return result, False, False

    # Call API
    api_result = provider.call_api(phone)

    if api_result is None:
        flattened = clean_data_for_db(provider.flatten({}))
    else:
        flattened = clean_data_for_db(provider.flatten(api_result))

    flattened["phone_number"] = phone
    flattened["cal_name"] = cal_name
    flattened[f"{provider.name}.api_call_time"] = datetime.now(timezone.utc).isoformat()

    # Save to DB
    provider.save_to_cache(db, phone, cal_name, flattened)

    return flattened, True, False


def _clean_apostrophes(text):
    """Remove apostrophe variants from text."""
    return str(text or "").replace("'", "").replace("\u2019", "").replace("`", "")


def translate_and_score(provider, result, cal_name, db):
    """Clean, transliterate, and score results for any provider. Modifies result dict in-place."""
    prefix = provider.name
    names = provider.get_name_fields(result)

    first = _clean_apostrophes(names.get("first", ""))
    last = _clean_apostrophes(names.get("last", ""))
    common_name = _clean_apostrophes(names.get("common_name", ""))

    # Write cleaned names back
    provider.set_name_fields(result, first, last, common_name)

    # Determine primary name for error checking
    check_name = common_name or first
    is_error = check_name.startswith("ERROR:") or check_name == "NOT IN CACHE"
    if is_error:
        result[f"{prefix}.translated"] = ""
        result[f"{prefix}.matching"] = 0
        result[f"{prefix}.risk_tier"] = ""
        return

    # Transliterate non-Hebrew names
    all_names = [common_name, first, last] if common_name else [first, last]
    translated_parts = []
    for name in all_names:
        if name and not is_hebrew(name):
            translated = transliterate_name(name)
            if translated:
                translated_parts.append(translated)

    # Deduplicate words while preserving order
    all_words = ' '.join(translated_parts).split()
    result[f"{prefix}.translated"] = ' '.join(dict.fromkeys(w for w in all_words if w))

    # Score
    if cal_name and (first or last):
        engine = ScoreEngine(conn=db)
        score_result = engine.score_match(
            cal_name=cal_name,
            api_first=first,
            api_last=last,
            api_common_name=common_name,
            api_source=provider.display_name,
        )
        result[f"{prefix}.matching"] = score_result["final_score"]
        result[f"{prefix}.risk_tier"] = score_result["risk_tier"]
        result[f"{prefix}.score_explanation"] = score_result["explanation"]
    else:
        result[f"{prefix}.matching"] = 0
        result[f"{prefix}.risk_tier"] = ""
