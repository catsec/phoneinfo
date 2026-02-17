"""REST API endpoints blueprint."""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
from db import (
    get_db, get_from_db_with_age, save_to_db, convert_db_to_response,
    clean_data_for_db, me_flat_to_db_data, get_from_sync_db, save_to_sync_db,
    sync_flat_to_db_data, get_all_nicknames_for_name,
)
from config import API_URL, SID, TOKEN, SYNC_API_URL, SYNC_API_TOKEN, limiter
from api_me import call_api as me_call_api, flatten_user_data as me_flatten_user_data
from api_sync import call_api as sync_call_api, flatten_user_data as sync_flatten_user_data
from transliteration import transliterate_name
from scoring import ScoreEngine

api_bp = Blueprint("api", __name__)


@api_bp.route("/me", methods=["POST"])
def me_api():
    """
    ME API wrapper - checks cache, calls external API if needed, stores in DB.

    Input: {
        "phone": "972...",
        "cal_name": "...",
        "use_cache": true,      # optional, default true - check cache first
        "refresh_days": 7,      # optional - refresh if data older than N days (0 = always refresh)
        "noapi": false          # optional, default false - if true, only use cache
    }
    Output: { "phone_number": "...", "common_name": "...", ..., "from_cache": bool }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    phone = data.get("phone")
    cal_name = data.get("cal_name", "")
    use_cache = data.get("use_cache", True)
    refresh_days = data.get("refresh_days")
    noapi = data.get("noapi", False)

    if not phone:
        return jsonify({"error": "phone is required"}), 400

    try:
        db = get_db()
        db_result = None

        # Check cache first if enabled
        if use_cache:
            db_result = get_from_db_with_age(db, phone)
            if db_result:
                # Update cal_name if different
                if cal_name and db_result.get("cal_name") != cal_name:
                    db_result["cal_name"] = cal_name
                    save_to_db(db, phone, cal_name, db_result, update_time=False)

                # Check if refresh is needed
                needs_refresh = False
                if refresh_days is not None:
                    if refresh_days == 0:
                        needs_refresh = True
                    else:
                        api_call_time_str = db_result.get("api_call_time", "")
                        if api_call_time_str:
                            api_call_time = datetime.fromisoformat(api_call_time_str)
                            if api_call_time.tzinfo is None:
                                api_call_time = api_call_time.replace(tzinfo=timezone.utc)
                            age_days = (datetime.now(timezone.utc) - api_call_time).days
                            needs_refresh = age_days >= refresh_days
                        else:
                            needs_refresh = True  # No timestamp, needs refresh

                if not needs_refresh:
                    result = convert_db_to_response(db_result)
                    result["from_cache"] = True
                    return jsonify(result)

        # If noapi mode, return empty result or cached data
        if noapi:
            if use_cache and db_result:
                result = convert_db_to_response(db_result)
                result["from_cache"] = True
                return jsonify(result)
            else:
                result = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
                result["phone_number"] = phone
                result["cal_name"] = cal_name
                result["me.common_name"] = "NOT IN CACHE"
                result["from_cache"] = False
                return jsonify(result)

        # Call the ME API
        api_result = me_call_api(phone, API_URL, SID, TOKEN)

        if api_result is None:
            flattened_result = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
        else:
            flattened_result = clean_data_for_db(me_flatten_user_data(api_result, prefix="me"))

        flattened_result["phone_number"] = phone
        flattened_result["cal_name"] = cal_name
        flattened_result["me.api_call_time"] = datetime.now(timezone.utc).isoformat()

        save_to_db(db, phone, cal_name, me_flat_to_db_data(flattened_result))

        flattened_result["from_cache"] = False
        return jsonify(flattened_result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/sync", methods=["POST"])
def sync_api():
    """
    SYNC API wrapper - checks cache, calls external API if needed, stores in DB.

    Input: {
        "phone": "972...",
        "use_cache": true,      # optional, default true
        "refresh_days": 7,      # optional - refresh if older than N days
        "noapi": false          # optional - if true, only use cache
    }
    Output: { "phone_number": "...", "sync.first_name": "...", "sync.last_name": "...", "from_cache": bool }
    """
    if not SYNC_API_URL or not SYNC_API_TOKEN:
        return jsonify({"error": "SYNC API not configured"}), 501

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    phone = data.get("phone")
    use_cache = data.get("use_cache", True)
    refresh_days = data.get("refresh_days")
    noapi = data.get("noapi", False)

    if not phone:
        return jsonify({"error": "phone is required"}), 400

    try:
        db = get_db()
        db_result = None

        # Check cache first
        if use_cache:
            db_result = get_from_sync_db(db, phone)
            if db_result:
                needs_refresh = False
                if refresh_days is not None:
                    if refresh_days == 0:
                        needs_refresh = True
                    else:
                        api_call_time_str = db_result.get("api_call_time", "")
                        if api_call_time_str:
                            api_call_time = datetime.fromisoformat(api_call_time_str)
                            if api_call_time.tzinfo is None:
                                api_call_time = api_call_time.replace(tzinfo=timezone.utc)
                            age_days = (datetime.now(timezone.utc) - api_call_time).days
                            needs_refresh = age_days >= refresh_days

                if not needs_refresh:
                    return jsonify({
                        "phone_number": phone,
                        "sync.first_name": db_result.get("first_name", ""),
                        "sync.last_name": db_result.get("last_name", ""),
                        "sync.api_call_time": db_result.get("api_call_time", ""),
                        "from_cache": True
                    })

        # If noapi mode, return cached data or empty
        if noapi:
            if use_cache and db_result:
                return jsonify({
                    "phone_number": phone,
                    "sync.first_name": db_result.get("first_name", ""),
                    "sync.last_name": db_result.get("last_name", ""),
                    "sync.api_call_time": db_result.get("api_call_time", ""),
                    "from_cache": True
                })
            else:
                return jsonify({
                    "phone_number": phone,
                    "sync.first_name": "NOT IN CACHE",
                    "sync.last_name": "",
                    "sync.api_call_time": "",
                    "from_cache": False
                })

        # Call the SYNC API
        api_result = sync_call_api(phone, SYNC_API_URL, SYNC_API_TOKEN)

        if api_result is None:
            flattened_result = sync_flatten_user_data({}, prefix="sync")
        else:
            flattened_result = sync_flatten_user_data(api_result, prefix="sync")

        flattened_result["phone_number"] = phone
        flattened_result["sync.api_call_time"] = datetime.now(timezone.utc).isoformat()

        save_to_sync_db(db, phone, "", sync_flat_to_db_data(flattened_result))

        flattened_result["from_cache"] = False
        return jsonify(flattened_result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/translate", methods=["POST"])
def translate():
    """Transliterate names to Hebrew (auto-detects language)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    first = data.get("first", "")
    last = data.get("last", "")

    return jsonify({
        "first": transliterate_name(first),
        "last": transliterate_name(last)
    })


@api_bp.route("/nicknames", methods=["GET"])
def nicknames():
    """Get all nickname variants for a given name."""
    name = request.args.get("name", "")
    if not name:
        return jsonify({"error": "name parameter is required"}), 400

    variants = get_all_nicknames_for_name(get_db(), name)
    return jsonify({"names": variants})


@api_bp.route("/compare", methods=["POST"])
def compare():
    """Calculate similarity score between name sets."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    first = data.get("first", "")
    last = data.get("last", "")
    names = data.get("names", [])
    target_last = data.get("target_last", "")

    cal_name = ' '.join(names) + ' ' + target_last if target_last else ' '.join(names)

    engine = ScoreEngine(conn=get_db())
    result = engine.score_match(
        cal_name=cal_name.strip(),
        api_first=first,
        api_last=last,
    )

    return jsonify({
        "score": result["final_score"],
        "risk_tier": result["risk_tier"],
        "breakdown": result["breakdown"],
        "explanation": result["explanation"],
    })


@api_bp.route("/health", methods=["GET"])
@limiter.exempt
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})
