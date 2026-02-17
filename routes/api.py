"""REST API endpoints blueprint."""

from flask import Blueprint, request, jsonify
from db import get_db, get_all_nicknames_for_name
from config import limiter
from providers import get_provider
from lookup import lookup
from transliteration import transliterate_name
from scoring import ScoreEngine

api_bp = Blueprint("api", __name__)


@api_bp.route("/lookup/<provider_name>", methods=["POST"])
def lookup_api(provider_name):
    """Generic lookup endpoint for any registered provider.

    Input: {
        "phone": "972...",
        "cal_name": "...",            # optional
        "use_cache": true,            # optional, default true — check cache first
        "refresh_days": 7,            # optional — refresh if data older than N days (0 = always refresh)
        "noapi": false                # optional, default false — if true, only use cache
    }
    Output: { "phone_number": "...", "<provider>.<field>": "...", ..., "from_cache": bool }
    """
    provider = get_provider(provider_name)
    if not provider:
        return jsonify({"error": f"Unknown provider: {provider_name}"}), 404
    if not provider.is_configured:
        return jsonify({"error": f"{provider.display_name} API not configured"}), 501

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    phone = data.get("phone")
    cal_name = data.get("cal_name", "")
    use_cache = data.get("use_cache", True)
    refresh_days = data.get("refresh_days", 7)
    noapi = data.get("noapi", False)

    if not phone:
        return jsonify({"error": "phone is required"}), 400

    try:
        db = get_db()
        result, _api_called, from_cache = lookup(
            provider, db, phone, cal_name,
            refresh_days=refresh_days,
            cache_only=noapi,
            use_cache=use_cache,
        )
        result["from_cache"] = from_cache
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Backward compatibility aliases
@api_bp.route("/me", methods=["POST"])
def me_api():
    """ME API wrapper — alias for /lookup/me."""
    return lookup_api("me")


@api_bp.route("/sync", methods=["POST"])
def sync_api():
    """SYNC API wrapper — alias for /lookup/sync."""
    return lookup_api("sync")


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
