"""Web UI routes blueprint."""

import os
import uuid
import tempfile

import pandas as pd
from io import BytesIO
from flask import Blueprint, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
from db import get_db
from config import (
    API_URL, SID, TOKEN, SYNC_API_URL, SYNC_API_TOKEN,
    PROCESSED_FILES, allowed_file, get_cf_user,
)
from phone import validate_phone_numbers, convert_to_international
from transliteration import is_hebrew
from lookup import lookup_me, lookup_sync, translate_and_score_me, translate_and_score_sync
from app_logger import log_event
from input_validator import validate_file_size

web_bp = Blueprint("web", __name__)


@web_bp.route("/web/apis", methods=["GET"])
def web_apis():
    """Return list of available APIs."""
    apis = [
        {"name": "ME", "available": bool(API_URL and SID and TOKEN)},
        {"name": "SYNC", "available": bool(SYNC_API_URL and SYNC_API_TOKEN)},
    ]
    return jsonify({"apis": apis})


@web_bp.route("/")
@web_bp.route("/web")
def web_index():
    """Serve the web interface."""
    return render_template("index.html")


@web_bp.route("/web/query")
def web_query_page():
    """Serve the single query interface."""
    return render_template("query.html")


@web_bp.route("/web/query", methods=["POST"])
def web_query():
    """Process single phone query."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON body required"})

    phone = data.get("phone", "").strip()
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    refresh_days = data.get("refresh_days", 7)
    me_cache_only = data.get("me_cache_only", False)
    sync_cache_only = data.get("sync_cache_only", False)
    apis_str = data.get("apis", "me")
    selected_apis = [a.strip().lower() for a in apis_str.split(',') if a.strip()]
    use_me = 'me' in selected_apis
    use_sync = 'sync' in selected_apis

    if not phone:
        return jsonify({"success": False, "error": "מספר טלפון נדרש"})

    phone_list = convert_to_international([phone])
    phone = phone_list[0]

    if not validate_phone_numbers([phone]):
        return jsonify({"success": False, "error": "מספר טלפון לא תקין"})

    cal_name = f"{first_name} {last_name}".strip()

    if not cal_name:
        return jsonify({"success": False, "error": "שם איש קשר נדרש"})

    if not is_hebrew(cal_name):
        return jsonify({"success": False, "error": "שם איש קשר חייב להיות בעברית"})

    try:
        db = get_db()
        me_api_called = False
        me_result_ok = ""
        sync_api_called = False
        sync_from_cache = False
        sync_result_ok = ""
        from_cache = False

        result = {"phone_number": phone, "cal_name": cal_name}

        # ME lookup
        if use_me:
            me_data, me_api_called, from_cache = lookup_me(
                db, phone, cal_name, refresh_days, me_cache_only, API_URL, SID, TOKEN
            )
            if me_api_called:
                me_result_ok = "success" if me_data.get("me.common_name") else "fail"
            result.update(me_data)
            result["phone_number"] = phone
            result["cal_name"] = cal_name

        # ME translate & score
        if use_me:
            translate_and_score_me(result, cal_name, db)

        # SYNC lookup
        if use_sync and SYNC_API_URL and SYNC_API_TOKEN:
            try:
                sync_data, sync_api_called, sync_from_cache = lookup_sync(
                    db, phone, cal_name, refresh_days, sync_cache_only, SYNC_API_URL, SYNC_API_TOKEN
                )
                if sync_api_called:
                    sync_result_ok = "success" if sync_data.get("sync.first_name") else "fail"
                result.update(sync_data)

                # SYNC translate & score
                translate_and_score_sync(result, cal_name, db)
            except Exception as sync_error:
                result["sync.first_name"] = f"ERROR: {sync_error}"
                result["sync.last_name"] = ""
                result["sync.matching"] = 0

        # Log
        log_event(
            user=get_cf_user() or "",
            action="query",
            phone=phone,
            me_api_call=me_api_called,
            sync_api_call=sync_api_called,
            me_cache=from_cache,
            sync_cache=sync_from_cache,
            me_result=me_result_ok,
            sync_result=sync_result_ok,
            datetime_str=datetime.now(timezone.utc).isoformat(),
        )

        return jsonify({
            "success": True,
            "result": result,
            "from_cache": not me_api_called and not sync_api_called
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@web_bp.route("/web/process", methods=["POST"])
def web_process():
    """Process uploaded file via web interface."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Invalid file type. Only .xlsx and .csv files are allowed"}), 400

    original_filename = file.filename

    try:
        refresh_days = int(request.form.get('refresh_days', 7))
    except ValueError:
        refresh_days = 7

    me_cache_only = request.form.get('me_cache_only', '').lower() == 'true'
    sync_cache_only = request.form.get('sync_cache_only', '').lower() == 'true'

    apis_str = request.form.get('apis', 'me')
    selected_apis = [a.strip().lower() for a in apis_str.split(',') if a.strip()]
    if not selected_apis:
        selected_apis = ['me']

    use_me = 'me' in selected_apis
    use_sync = 'sync' in selected_apis and SYNC_API_URL and SYNC_API_TOKEN

    if use_me and use_sync:
        file_suffix = "_me_sync"
    elif use_sync:
        file_suffix = "_sync"
    else:
        file_suffix = "_me"

    try:
        # Validate file size
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        validate_file_size(file_size)

        # Read file
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            data = pd.read_csv(file, dtype=str, header=None)
        elif filename.endswith('.xlsx'):
            data = pd.read_excel(file, dtype=str, header=None)
        else:
            return jsonify({"success": False, "error": "פורמט קובץ לא נתמך. השתמש ב-.xlsx או .csv"})

        if len(data) > 100000:
            return jsonify({"success": False, "error": f"File too large: {len(data)} rows (max 100,000)"}), 400

        if data.shape[1] != 3:
            return jsonify({"success": False, "error": f"הקובץ חייב להכיל בדיוק 3 עמודות (טלפון, שם פרטי, שם משפחה). נמצאו {data.shape[1]} עמודות"})

        if len(data) == 0:
            return jsonify({"success": False, "error": "הקובץ ריק"})

        # Detect and remove header row
        first_row = data.iloc[0]
        header_indicators = ['phone', 'טלפון', 'מספר', 'first', 'last', 'שם', 'name', 'פרטי', 'משפחה']
        is_header = False
        for cell in first_row:
            cell_str = str(cell).lower().strip() if pd.notna(cell) else ""
            if any(indicator in cell_str for indicator in header_indicators):
                is_header = True
                break
            if cell_str and not cell_str.replace('+', '').replace('-', '').replace(' ', '').isdigit():
                is_header = True
                break

        start_row = 1 if is_header else 0
        data = data.iloc[start_row:].reset_index(drop=True)

        if len(data) == 0:
            return jsonify({"success": False, "error": "הקובץ ריק (רק שורת כותרת)"})

        # Validate rows
        errors = []
        valid_rows = []

        def clean_name(name):
            if not name:
                return ""
            return name.replace("'", "").replace("\u2019", "").replace("`", "").strip()

        def is_valid_phone(phone):
            if not phone:
                return False
            phone = str(phone).strip().replace('-', '').replace(' ', '').replace('+', '')
            if phone.startswith('05') or phone.startswith('07'):
                return len(phone) >= 9 and len(phone) <= 10 and phone.isdigit()
            if phone.startswith('972'):
                return len(phone) >= 11 and len(phone) <= 12 and phone.isdigit()
            return False

        for idx, row in data.iterrows():
            excel_row = idx + 2 if is_header else idx + 1
            row_errors = []

            phone = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
            first_name = clean_name(str(row.iloc[1])) if pd.notna(row.iloc[1]) else ""
            last_name = clean_name(str(row.iloc[2])) if pd.notna(row.iloc[2]) else ""

            if not phone:
                row_errors.append(f"שורה {excel_row}, עמודה A: טלפון ריק")
            elif not is_valid_phone(phone):
                row_errors.append(f"שורה {excel_row}, עמודה A: טלפון לא תקין '{phone}'")

            if not first_name:
                row_errors.append(f"שורה {excel_row}, עמודה B: שם פרטי ריק")
            elif not is_hebrew(first_name):
                row_errors.append(f"שורה {excel_row}, עמודה B: שם פרטי חייב להיות בעברית '{first_name}'")

            if not last_name:
                row_errors.append(f"שורה {excel_row}, עמודה C: שם משפחה ריק")
            elif not is_hebrew(last_name):
                row_errors.append(f"שורה {excel_row}, עמודה C: שם משפחה חייב להיות בעברית '{last_name}'")

            if row_errors:
                errors.extend(row_errors)
            else:
                valid_rows.append({
                    "phone": phone,
                    "first_name": first_name,
                    "last_name": last_name,
                    "cal_name": f"{first_name} {last_name}"
                })

        if errors:
            error_list = "\n".join(errors[:20])
            if len(errors) > 20:
                error_list += f"\n... ועוד {len(errors) - 20} שגיאות"
            return jsonify({"success": False, "error": f"שגיאות בקובץ:\n{error_list}"})

        if not valid_rows:
            return jsonify({"success": False, "error": "לא נמצאו שורות תקינות בקובץ"})

        # Convert phones to international format
        for row in valid_rows:
            converted = convert_to_international([row["phone"]])
            row["phone"] = converted[0]

        results = []
        me_from_cache_count = 0
        me_api_calls_count = 0
        sync_from_cache_count = 0
        sync_api_calls_count = 0

        db = get_db()
        log_username = get_cf_user() or ""

        # Process each row
        for row_data in valid_rows:
            phone = row_data["phone"]
            cal_name = row_data["cal_name"]
            row_me_api_called = False
            row_me_result = ""
            row_sync_api_called = False
            row_sync_from_cache = False
            row_sync_result = ""
            me_from_cache = False

            result = {"phone_number": phone, "cal_name": cal_name}

            try:
                # ME lookup
                if use_me:
                    me_data, row_me_api_called, me_from_cache = lookup_me(
                        db, phone, cal_name, refresh_days, me_cache_only, API_URL, SID, TOKEN
                    )
                    if row_me_api_called:
                        me_api_calls_count += 1
                        row_me_result = "success" if me_data.get("me.common_name") else "fail"
                    elif me_from_cache:
                        me_from_cache_count += 1

                    for key, value in me_data.items():
                        result[key] = value
                    result["phone_number"] = phone
                    result["cal_name"] = cal_name

                # ME source indicator
                if use_me:
                    if row_me_api_called:
                        result["me.source"] = "API"
                    elif me_from_cache:
                        result["me.source"] = "cache"
                    else:
                        result["me.source"] = "cache-only"

                # SYNC lookup
                if use_sync:
                    sync_data, row_sync_api_called, row_sync_from_cache = lookup_sync(
                        db, phone, cal_name, refresh_days, sync_cache_only, SYNC_API_URL, SYNC_API_TOKEN
                    )
                    if row_sync_api_called:
                        sync_api_calls_count += 1
                        row_sync_result = "success" if sync_data.get("sync.first_name") else "fail"
                    elif row_sync_from_cache:
                        sync_from_cache_count += 1

                    result.update(sync_data)

                # SYNC source indicator
                if use_sync:
                    if row_sync_api_called:
                        result["sync.source"] = "API"
                    elif row_sync_from_cache:
                        result["sync.source"] = "cache"
                    else:
                        result["sync.source"] = "cache-only"

                results.append(result)

                log_event(
                    user=log_username,
                    action="process_file",
                    phone=phone,
                    filename=original_filename,
                    me_api_call=row_me_api_called,
                    sync_api_call=row_sync_api_called,
                    me_cache=me_from_cache,
                    sync_cache=row_sync_from_cache,
                    me_result=row_me_result,
                    sync_result=row_sync_result,
                    datetime_str=datetime.now(timezone.utc).isoformat(),
                )

            except Exception as e:
                result["me.common_name"] = f"ERROR: {e}" if use_me else ""
                result["sync.first_name"] = f"ERROR: {e}" if use_sync else ""
                results.append(result)

        # Post-process: translations and matching scores
        for result in results:
            cal_name = str(result.get("cal_name", "") or "")

            if use_me:
                translate_and_score_me(result, cal_name, db)

            if use_sync:
                translate_and_score_sync(result, cal_name, db)

        # Create DataFrame and Excel
        result_df = pd.DataFrame(results).astype(str)

        desired_order = ["phone_number", "cal_name"]

        if use_me:
            desired_order.extend([
                "me.common_name", "me.matching", "me.risk_tier", "me.translated",
                "me.result_strength", "me.profile_name",
                "me.first_name", "me.last_name", "me.email", "me.email_confirmed",
                "me.profile_picture", "me.gender", "me.is_verified", "me.slogan",
                "me.social.facebook", "me.social.twitter", "me.social.spotify",
                "me.social.instagram", "me.social.linkedin", "me.social.pinterest",
                "me.social.tiktok", "me.whitelist", "me.source", "me.api_call_time"
            ])

        if use_sync:
            desired_order.extend([
                "sync.first_name", "sync.last_name", "sync.matching", "sync.risk_tier", "sync.translated",
                "sync.source", "sync.api_call_time"
            ])

        existing_columns = [col for col in desired_order if col in result_df.columns]
        result_df = result_df.reindex(columns=existing_columns)

        file_id = str(uuid.uuid4())
        temp_path = os.path.join(tempfile.gettempdir(), f"result_{file_id}.xlsx")
        result_df.to_excel(temp_path, index=False, engine="openpyxl")

        PROCESSED_FILES[file_id] = {
            "path": temp_path,
            "created": datetime.now(),
            "original_name": os.path.splitext(file.filename)[0] + file_suffix + ".xlsx"
        }

        total_from_cache = me_from_cache_count + sync_from_cache_count
        total_api_calls = me_api_calls_count + sync_api_calls_count

        return jsonify({
            "success": True,
            "file_id": file_id,
            "total": len(results),
            "from_cache": total_from_cache,
            "api_calls": total_api_calls
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@web_bp.route("/web/download/<file_id>")
def web_download(file_id):
    """Download processed file. File is deleted after download."""
    if file_id not in PROCESSED_FILES:
        return jsonify({"error": "File not found"}), 404

    file_info = PROCESSED_FILES.pop(file_id)
    file_path = file_info["path"]

    if not os.path.exists(file_path):
        return jsonify({"error": "File expired"}), 404

    with open(file_path, "rb") as f:
        data = BytesIO(f.read())
    try:
        os.remove(file_path)
    except OSError:
        pass

    return send_file(
        data,
        as_attachment=True,
        download_name=file_info["original_name"],
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
