"""ME API provider."""

import os
import requests
from datetime import datetime, timezone
from providers.base import BaseProvider


class MEProvider(BaseProvider):
    name = "me"
    display_name = "ME"

    # Mapping: flattened key -> DB column name
    FLAT_TO_DB = {
        "me.common_name": "common_name",
        "me.profile_name": "me_profile_name",
        "me.result_strength": "result_strength",
        "me.first_name": "user_first_name",
        "me.last_name": "user_last_name",
        "me.email": "user_email",
        "me.email_confirmed": "user_email_confirmed",
        "me.profile_picture": "user_profile_picture",
        "me.gender": "user_gender",
        "me.is_verified": "user_is_verified",
        "me.slogan": "user_slogan",
        "me.social.facebook": "social_facebook",
        "me.social.twitter": "social_twitter",
        "me.social.spotify": "social_spotify",
        "me.social.instagram": "social_instagram",
        "me.social.linkedin": "social_linkedin",
        "me.social.pinterest": "social_pinterest",
        "me.social.tiktok": "social_tiktok",
        "me.whitelist": "whitelist",
    }

    # Reverse mapping: DB column -> flattened key
    DB_TO_FLAT = {v: k for k, v in FLAT_TO_DB.items()}
    DB_TO_FLAT["api_call_time"] = "me.api_call_time"

    def __init__(self):
        self._api_url = os.environ.get("ME_API_URL", "").strip()
        self._sid = os.environ.get("ME_API_SID", "").strip()
        self._token = os.environ.get("ME_API_TOKEN", "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self._api_url and self._sid and self._token)

    def call_api(self, phone: str):
        url = f"{self._api_url}?phone_number={phone}&sid={self._sid}&token={self._token}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            raise ValueError(
                f"API call failed for phone number {phone} with status code {response.status_code}"
            )

    def flatten(self, api_result: dict) -> dict:
        def replace_none(value):
            return "" if value is None else value

        user_data = api_result.get("user", {}) or {}
        social_profiles = user_data.get("social_profiles", {}) or {}
        user_keys = [
            "profile_picture", "first_name", "last_name", "email",
            "email_confirmed", "gender", "is_verified", "slogan",
        ]
        social_keys = [
            "facebook", "twitter", "spotify", "instagram",
            "linkedin", "pinterest", "tiktok",
        ]

        return {
            "me.common_name": replace_none(api_result.get("common_name", "")),
            "me.profile_name": replace_none(api_result.get("me_profile_name", "")),
            "me.result_strength": replace_none(api_result.get("result_strength", "")),
            **{f"me.{k}": replace_none(user_data.get(k, "")) for k in user_keys},
            **{f"me.social.{k}": replace_none(social_profiles.get(k, "")) for k in social_keys},
            "me.whitelist": replace_none(api_result.get("whitelist", "")),
            "me.api_call_time": "",
        }

    def init_table(self, conn):
        cursor = conn.cursor()

        # Migrate old api_data table to me_data if it exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_data'"
        )
        if cursor.fetchone():
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='me_data'"
            )
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE api_data RENAME TO me_data")
                conn.commit()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS me_data (
                phone_number TEXT PRIMARY KEY DEFAULT '',
                cal_name TEXT DEFAULT '',
                user_email TEXT DEFAULT '',
                user_email_confirmed BOOLEAN DEFAULT FALSE,
                user_profile_picture TEXT DEFAULT '',
                user_first_name TEXT DEFAULT '',
                user_last_name TEXT DEFAULT '',
                user_gender TEXT DEFAULT '',
                user_is_verified BOOLEAN DEFAULT FALSE,
                user_slogan TEXT DEFAULT '',
                social_facebook TEXT DEFAULT '',
                social_twitter TEXT DEFAULT '',
                social_spotify TEXT DEFAULT '',
                social_instagram TEXT DEFAULT '',
                social_linkedin TEXT DEFAULT '',
                social_pinterest TEXT DEFAULT '',
                social_tiktok TEXT DEFAULT '',
                common_name TEXT DEFAULT '',
                me_profile_name TEXT DEFAULT '',
                result_strength TEXT DEFAULT '',
                whitelist TEXT DEFAULT '',
                api_call_time TEXT DEFAULT ''
            )
        """)
        conn.commit()

    def get_from_cache(self, db, phone: str):
        cursor = db.cursor()
        cursor.execute("SELECT * FROM me_data WHERE phone_number = ?", (phone,))
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
        return None

    def save_to_cache(self, db, phone: str, cal_name: str, flat_data: dict):
        db_data = {
            db_col: flat_data.get(flat_key, "")
            for flat_key, db_col in self.FLAT_TO_DB.items()
        }
        api_call_time = flat_data.get("me.api_call_time", datetime.now(timezone.utc).isoformat())
        cursor = db.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO me_data (
                phone_number, cal_name, user_email, user_email_confirmed, user_profile_picture,
                user_first_name, user_last_name, user_gender, user_is_verified, user_slogan,
                social_facebook, social_twitter, social_spotify, social_instagram, social_linkedin,
                social_pinterest, social_tiktok, common_name, me_profile_name, result_strength,
                whitelist, api_call_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            phone, cal_name,
            db_data.get("user_email", ""),
            db_data.get("user_email_confirmed", ""),
            db_data.get("user_profile_picture", ""),
            db_data.get("user_first_name", ""),
            db_data.get("user_last_name", ""),
            db_data.get("user_gender", ""),
            db_data.get("user_is_verified", ""),
            db_data.get("user_slogan", ""),
            db_data.get("social_facebook", ""),
            db_data.get("social_twitter", ""),
            db_data.get("social_spotify", ""),
            db_data.get("social_instagram", ""),
            db_data.get("social_linkedin", ""),
            db_data.get("social_pinterest", ""),
            db_data.get("social_tiktok", ""),
            db_data.get("common_name", ""),
            db_data.get("me_profile_name", ""),
            db_data.get("result_strength", ""),
            db_data.get("whitelist", ""),
            api_call_time,
        ])
        db.commit()

    def cache_to_result(self, db_result: dict) -> dict:
        result = {
            "phone_number": db_result.get("phone_number", ""),
            "cal_name": db_result.get("cal_name", ""),
        }
        for db_col, flat_key in self.DB_TO_FLAT.items():
            result[flat_key] = db_result.get(db_col, "")
        return result

    def empty_result(self) -> dict:
        return self.flatten({})

    def get_name_fields(self, result: dict) -> dict:
        return {
            "first": result.get("me.first_name", ""),
            "last": result.get("me.last_name", ""),
            "common_name": result.get("me.common_name", ""),
        }

    def set_name_fields(self, result: dict, first: str, last: str, common_name: str = ""):
        result["me.first_name"] = first
        result["me.last_name"] = last
        result["me.common_name"] = common_name

    def get_primary_name_key(self) -> str:
        return "me.common_name"

    @property
    def excel_columns(self) -> list:
        return [
            "me.common_name", "me.matching", "me.risk_tier", "me.translated",
            "me.result_strength", "me.profile_name",
            "me.first_name", "me.last_name", "me.email", "me.email_confirmed",
            "me.profile_picture", "me.gender", "me.is_verified", "me.slogan",
            "me.social.facebook", "me.social.twitter", "me.social.spotify",
            "me.social.instagram", "me.social.linkedin", "me.social.pinterest",
            "me.social.tiktok", "me.whitelist", "me.source", "me.api_call_time",
        ]
