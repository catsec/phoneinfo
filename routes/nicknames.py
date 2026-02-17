"""Nicknames management routes blueprint."""

import json
import os
import tempfile

import pandas as pd
from flask import Blueprint, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename
from db import get_db
from config import allowed_file
from input_validator import validate_nicknames_data, validate_file_size, ValidationError

nicknames_bp = Blueprint("nicknames", __name__)


@nicknames_bp.route("/web/nicknames")
def web_nicknames_page():
    """Serve the nicknames management page."""
    return render_template("nicknames.html")


@nicknames_bp.route("/web/nicknames/list")
def web_nicknames_list():
    """Return list of all nicknames."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT formal_name, all_names FROM nicknames ORDER BY formal_name")
    rows = cursor.fetchall()

    nicknames = []
    total_nicknames = 0
    for row in rows:
        formal_name, all_names = row
        nicknames.append({
            "formal_name": formal_name,
            "all_names": all_names
        })
        if all_names:
            total_nicknames += len(all_names.split(','))

    return jsonify({
        "nicknames": nicknames,
        "total_names": len(nicknames),
        "total_nicknames": total_nicknames
    })


@nicknames_bp.route("/web/nicknames/upload", methods=["POST"])
def web_nicknames_upload():
    """Upload and import nicknames from file (JSON, Excel, or CSV)."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "לא הועלה קובץ"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "לא נבחר קובץ"})

    filename = secure_filename(file.filename)
    filename_lower = filename.lower()

    if not (filename_lower.endswith('.json') or allowed_file(filename)):
        return jsonify({"success": False, "error": "סוג קובץ לא חוקי. רק קבצי .json, .xlsx ו-.csv מותרים"}), 400

    mode = request.form.get('mode', 'add')

    try:
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        validate_file_size(file_size)

        if filename_lower.endswith('.json'):
            content = file.read().decode('utf-8')
            nicknames_list = json.loads(content)
            nicknames_list = validate_nicknames_data(nicknames_list)
            df = pd.DataFrame(nicknames_list)

        elif filename_lower.endswith('.csv'):
            df = pd.read_csv(file, dtype=str)
        elif filename_lower.endswith('.xlsx'):
            df = pd.read_excel(file, dtype=str)
        else:
            return jsonify({"success": False, "error": "פורמט קובץ לא נתמך. השתמש ב-.json, .xlsx או .csv"})

        if df.shape[1] < 2 or 'formal_name' not in df.columns or 'all_names' not in df.columns:
            return jsonify({"success": False, "error": "הקובץ חייב להכיל עמודות formal_name ו-all_names"})

        if not filename_lower.endswith('.json'):
            df.columns = ['formal_name', 'all_names'] + list(df.columns[2:])
            data_list = df.to_dict('records')
            data_list = validate_nicknames_data(data_list)
            df = pd.DataFrame(data_list)

        db = get_db()
        cursor = db.cursor()

        added = 0
        updated = 0
        skipped = 0

        for _, row in df.iterrows():
            formal_name = str(row['formal_name']).strip() if pd.notna(row['formal_name']) else ""
            all_names = str(row['all_names']).strip() if pd.notna(row['all_names']) else ""

            if not formal_name or not all_names:
                skipped += 1
                continue

            cursor.execute("SELECT all_names FROM nicknames WHERE formal_name = ?", (formal_name,))
            existing = cursor.fetchone()

            if existing:
                if mode == 'overwrite':
                    cursor.execute(
                        "UPDATE nicknames SET all_names = ? WHERE formal_name = ?",
                        (all_names, formal_name)
                    )
                    updated += 1
                else:
                    existing_names = set(n.strip() for n in existing[0].split(',') if n.strip())
                    new_names = set(n.strip() for n in all_names.split(',') if n.strip())
                    merged = existing_names | new_names
                    merged_str = ','.join(sorted(merged))
                    cursor.execute(
                        "UPDATE nicknames SET all_names = ? WHERE formal_name = ?",
                        (merged_str, formal_name)
                    )
                    if new_names - existing_names:
                        updated += 1
                    else:
                        skipped += 1
            else:
                cursor.execute(
                    "INSERT INTO nicknames (formal_name, all_names) VALUES (?, ?)",
                    (formal_name, all_names)
                )
                added += 1

        db.commit()

        return jsonify({
            "success": True,
            "added": added,
            "updated": updated,
            "skipped": skipped
        })

    except ValidationError as e:
        return jsonify({"success": False, "error": f"Validation error: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@nicknames_bp.route("/web/nicknames/download")
def web_nicknames_download():
    """Download current nicknames as JSON file."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT formal_name, all_names FROM nicknames ORDER BY formal_name")
    rows = cursor.fetchall()

    nicknames_data = []
    for row in rows:
        nicknames_data.append({
            'formal_name': row[0],
            'all_names': row[1]
        })

    temp_path = os.path.join(tempfile.gettempdir(), "nicknames_export.json")
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(nicknames_data, f, ensure_ascii=False, indent=2)

    return send_file(
        temp_path,
        as_attachment=True,
        download_name="nicknames.json",
        mimetype="application/json"
    )


@nicknames_bp.route("/web/nicknames/backup", methods=["POST"])
def web_nicknames_backup():
    """Backup nicknames to local nicknames.xlsx file."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT formal_name, all_names FROM nicknames ORDER BY formal_name")
        rows = cursor.fetchall()

        df = pd.DataFrame(rows, columns=['formal_name', 'all_names'])

        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(script_dir)
        backup_path = os.path.join(project_dir, "nicknames.xlsx")
        df.to_excel(backup_path, index=False, engine="openpyxl")

        return jsonify({
            "success": True,
            "message": f"גיבוי נשמר בהצלחה",
            "count": len(rows)
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@nicknames_bp.route("/web/nicknames/restore", methods=["POST"])
def web_nicknames_restore():
    """Restore nicknames from local nicknames.xlsx file."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(script_dir)
        backup_path = os.path.join(project_dir, "nicknames.xlsx")

        if not os.path.exists(backup_path):
            return jsonify({"success": False, "error": "קובץ nicknames.xlsx לא נמצא"})

        df = pd.read_excel(backup_path, dtype=str)

        if df.shape[1] < 2:
            return jsonify({"success": False, "error": "פורמט קובץ לא תקין"})

        df.columns = ['formal_name', 'all_names'] + list(df.columns[2:])

        db = get_db()
        cursor = db.cursor()

        cursor.execute("DELETE FROM nicknames")

        count = 0
        for _, row in df.iterrows():
            formal_name = str(row['formal_name']).strip() if pd.notna(row['formal_name']) else ""
            all_names = str(row['all_names']).strip() if pd.notna(row['all_names']) else ""

            if formal_name and all_names:
                cursor.execute(
                    "INSERT INTO nicknames (formal_name, all_names) VALUES (?, ?)",
                    (formal_name, all_names)
                )
                count += 1

        db.commit()

        return jsonify({
            "success": True,
            "message": "שחזור בוצע בהצלחה",
            "count": count
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@nicknames_bp.route("/web/nicknames/edit")
def web_nicknames_edit_page():
    """Serve the nickname edit page."""
    return render_template("nickname_edit.html")


@nicknames_bp.route("/web/nicknames/get")
def web_nicknames_get():
    """Get nicknames for a specific formal name."""
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"found": False, "error": "שם נדרש"})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT all_names FROM nicknames WHERE formal_name = ?", (name,))
    row = cursor.fetchone()

    if row:
        return jsonify({
            "found": True,
            "formal_name": name,
            "all_names": row[0]
        })
    else:
        return jsonify({
            "found": False,
            "formal_name": name
        })


@nicknames_bp.route("/web/nicknames/save", methods=["POST"])
def web_nicknames_save():
    """Save or update nicknames for a formal name."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON body required"})

    formal_name = data.get("formal_name", "").strip()
    all_names = data.get("all_names", "").strip()

    if not formal_name:
        return jsonify({"success": False, "error": "שם רשמי נדרש"})

    if not all_names:
        return jsonify({"success": False, "error": "כינויים נדרשים"})

    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT id FROM nicknames WHERE formal_name = ?", (formal_name,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                "UPDATE nicknames SET all_names = ? WHERE formal_name = ?",
                (all_names, formal_name)
            )
        else:
            cursor.execute(
                "INSERT INTO nicknames (formal_name, all_names) VALUES (?, ?)",
                (formal_name, all_names)
            )

        db.commit()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@nicknames_bp.route("/web/nicknames/delete", methods=["POST"])
def web_nicknames_delete():
    """Delete nicknames for a formal name."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON body required"})

    formal_name = data.get("formal_name", "").strip()

    if not formal_name:
        return jsonify({"success": False, "error": "שם רשמי נדרש"})

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM nicknames WHERE formal_name = ?", (formal_name,))
        db.commit()

        if cursor.rowcount > 0:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "שם לא נמצא"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
