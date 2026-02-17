"""
lookup.py - Core phone lookup pipeline.

Provides reusable functions for the cache→API→save→translate→score pipeline,
eliminating duplication across REST API, single query, and batch processing routes.
"""

from datetime import datetime, timezone
from db import (
    get_from_db_with_age, save_to_db, convert_db_to_response, clean_data_for_db,
    me_flat_to_db_data, get_from_sync_db, save_to_sync_db, sync_flat_to_db_data,
)
from api_me import call_api as me_call_api, flatten_user_data as me_flatten_user_data
from api_sync import call_api as sync_call_api, flatten_user_data as sync_flatten_user_data
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


def lookup_me(db, phone, cal_name, refresh_days, cache_only, api_url, sid, token):
    """Look up phone via ME: check cache, call API if needed, save to DB.

    Returns: (result_dict, api_called, from_cache)
        result_dict: flat dict with me.* keys
        api_called: True if an API call was made
        from_cache: True if result came from cache
    """
    from_cache = False
    api_called = False
    api_result_status = ""

    # Check cache
    db_result = get_from_db_with_age(db, phone)

    if db_result and check_cache_freshness(db_result, refresh_days, cache_only):
        # Update cal_name if different
        if db_result.get("cal_name") != cal_name and cal_name:
            db_result["cal_name"] = cal_name
            save_to_db(db, phone, cal_name, db_result, update_time=False)

        result = convert_db_to_response(db_result)
        result["phone_number"] = phone
        result["cal_name"] = cal_name or db_result.get("cal_name", "")
        return result, False, True

    # Cache-only mode but nothing in cache
    if cache_only:
        result = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
        result["phone_number"] = phone
        result["cal_name"] = cal_name
        result["me.common_name"] = "NOT IN CACHE"
        return result, False, False

    # Call ME API
    api_result = me_call_api(phone, api_url, sid, token)
    api_called = True
    api_result_status = "success" if api_result is not None else "fail"

    if api_result is None:
        flattened = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
    else:
        flattened = clean_data_for_db(me_flatten_user_data(api_result, prefix="me"))

    flattened["phone_number"] = phone
    flattened["cal_name"] = cal_name
    flattened["me.api_call_time"] = datetime.now(timezone.utc).isoformat()

    # Save to DB
    save_to_db(db, phone, cal_name, me_flat_to_db_data(flattened))

    return flattened, True, False


def lookup_sync(db, phone, cal_name, refresh_days, cache_only, api_url, api_token):
    """Look up phone via SYNC: check cache, call API if needed, save to DB.

    Returns: (result_dict, api_called, from_cache)
        result_dict: dict with sync.first_name, sync.last_name, sync.api_call_time
        api_called: True if an API call was made
        from_cache: True if result came from cache
    """
    # Check cache
    db_result = get_from_sync_db(db, phone)

    if db_result and check_cache_freshness(db_result, refresh_days, cache_only):
        result = {
            "sync.first_name": db_result.get("first_name", ""),
            "sync.last_name": db_result.get("last_name", ""),
            "sync.api_call_time": db_result.get("api_call_time", ""),
        }
        return result, False, True

    # Cache-only mode but nothing in cache
    if cache_only:
        result = {
            "sync.first_name": "NOT IN CACHE",
            "sync.last_name": "",
            "sync.api_call_time": "",
        }
        return result, False, False

    # Call SYNC API
    api_result = sync_call_api(phone, api_url, api_token)
    api_called = True

    if api_result:
        sync_flat = sync_flatten_user_data(api_result, prefix="sync")
    else:
        sync_flat = sync_flatten_user_data({}, prefix="sync")

    result = {
        "sync.first_name": sync_flat.get("sync.first_name", ""),
        "sync.last_name": sync_flat.get("sync.last_name", ""),
        "sync.api_call_time": datetime.now(timezone.utc).isoformat(),
    }

    # Save to cache
    save_to_sync_db(db, phone, cal_name, sync_flat_to_db_data(sync_flat))

    return result, True, False


def _clean_apostrophes(text):
    """Remove apostrophe variants from text."""
    return str(text or "").replace("'", "").replace("\u2019", "").replace("`", "")


def translate_and_score_me(result, cal_name, db):
    """Clean, transliterate, and score ME results. Modifies result dict in-place."""
    me_common_name = _clean_apostrophes(result.get("me.common_name", ""))
    me_first_name = _clean_apostrophes(result.get("me.first_name", ""))
    me_last_name = _clean_apostrophes(result.get("me.last_name", ""))

    result["me.common_name"] = me_common_name
    result["me.first_name"] = me_first_name
    result["me.last_name"] = me_last_name

    # Skip for error/not-in-cache results
    is_error = me_common_name.startswith("ERROR:") or me_common_name == "NOT IN CACHE"
    if is_error:
        result["me.translated"] = ""
        result["me.matching"] = 0
        result["me.risk_tier"] = ""
        return

    # Transliterate non-Hebrew names
    translated_common = transliterate_name(me_common_name) if me_common_name and not is_hebrew(me_common_name) else ""
    translated_first = transliterate_name(me_first_name) if me_first_name and not is_hebrew(me_first_name) else ""
    translated_last = transliterate_name(me_last_name) if me_last_name and not is_hebrew(me_last_name) else ""

    all_translated = f"{translated_common} {translated_first} {translated_last}".split()
    result["me.translated"] = ' '.join(dict.fromkeys(w for w in all_translated if w))

    # Score
    if cal_name:
        engine = ScoreEngine(conn=db)
        score_result = engine.score_match(
            cal_name=cal_name,
            api_first=me_first_name,
            api_last=me_last_name,
            api_common_name=me_common_name,
            api_source="ME"
        )
        result["me.matching"] = score_result["final_score"]
        result["me.risk_tier"] = score_result["risk_tier"]
        result["me.score_explanation"] = score_result["explanation"]
    else:
        result["me.matching"] = 0
        result["me.risk_tier"] = ""


def translate_and_score_sync(result, cal_name, db):
    """Clean, transliterate, and score SYNC results. Modifies result dict in-place."""
    sync_first = _clean_apostrophes(result.get("sync.first_name", ""))
    sync_last = _clean_apostrophes(result.get("sync.last_name", ""))

    result["sync.first_name"] = sync_first
    result["sync.last_name"] = sync_last

    # Skip for error/not-in-cache results
    is_error = sync_first.startswith("ERROR:") or sync_first == "NOT IN CACHE"
    if is_error:
        result["sync.translated"] = ""
        result["sync.matching"] = 0
        result["sync.risk_tier"] = ""
        return

    # Transliterate non-Hebrew names
    sync_translated_first = transliterate_name(sync_first) if sync_first and not is_hebrew(sync_first) else ""
    sync_translated_last = transliterate_name(sync_last) if sync_last and not is_hebrew(sync_last) else ""

    all_sync_translated = f"{sync_translated_first} {sync_translated_last}".split()
    result["sync.translated"] = ' '.join(dict.fromkeys(w for w in all_sync_translated if w))

    # Score
    if cal_name and (sync_first or sync_last):
        engine = ScoreEngine(conn=db)
        sync_score_result = engine.score_match(
            cal_name=cal_name,
            api_first=sync_first,
            api_last=sync_last,
            api_source="SYNC"
        )
        result["sync.matching"] = sync_score_result["final_score"]
        result["sync.risk_tier"] = sync_score_result["risk_tier"]
        result["sync.score_explanation"] = sync_score_result["explanation"]
    else:
        result["sync.matching"] = 0
        result["sync.risk_tier"] = ""
