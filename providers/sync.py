"""SYNC API provider."""

import os
import requests
from datetime import datetime, timezone
from providers.base import BaseProvider


class SyncProvider(BaseProvider):
    name = "sync"
    display_name = "SYNC"

    SAVE_FIELDS = [
        "name", "first_name", "last_name", "is_potential_spam",
        "is_business", "job_hint", "company_hint", "website_domain", "company_domain",
    ]

    def __init__(self):
        self._api_url = os.environ.get("SYNC_API_URL", "").strip()
        self._token = os.environ.get("SYNC_API_TOKEN", "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self._api_url and self._token)

    def call_api(self, phone: str):
        phone = phone.lstrip('+')
        payload = {"access_token": self._token, "phone_number": phone}
        response = requests.post(self._api_url, json=payload)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        elif response.status_code == 400:
            raise ValueError(f"Invalid phone number: {phone}")
        elif response.status_code == 403:
            raise ValueError("API rate limit or request limit reached")
        else:
            raise ValueError(
                f"API call failed for phone number {phone} with status code {response.status_code}"
            )

    def flatten(self, api_result: dict) -> dict:
        def replace_none(value):
            return "" if value is None else value

        results = api_result.get("results", {}) or {}
        full_name = results.get("name", "") or ""

        name_parts = full_name.strip().split(maxsplit=1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        return {
            "sync.name": replace_none(full_name),
            "sync.first_name": replace_none(first_name),
            "sync.last_name": replace_none(last_name),
            "sync.is_potential_spam": replace_none(results.get("is_potential_spam", "")),
            "sync.is_business": replace_none(results.get("is_business", "")),
            "sync.job_hint": replace_none(results.get("job_hint", "")),
            "sync.company_hint": replace_none(results.get("company_hint", "")),
            "sync.website_domain": replace_none(results.get("website_domain", "")),
            "sync.company_domain": replace_none(results.get("company_domain", "")),
            "sync.api_call_time": "",
        }

    def init_table(self, conn):
        cursor = conn.cursor()

        # Migrate: drop old schema if missing first_name column
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_data'"
        )
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(sync_data)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'first_name' not in columns:
                cursor.execute("DROP TABLE sync_data")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_data (
                phone_number TEXT PRIMARY KEY DEFAULT '',
                cal_name TEXT DEFAULT '',
                name TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT '',
                is_potential_spam TEXT DEFAULT '',
                is_business TEXT DEFAULT '',
                job_hint TEXT DEFAULT '',
                company_hint TEXT DEFAULT '',
                website_domain TEXT DEFAULT '',
                company_domain TEXT DEFAULT '',
                api_call_time TEXT DEFAULT ''
            )
        """)
        conn.commit()

    def get_from_cache(self, db, phone: str):
        cursor = db.cursor()
        cursor.execute("SELECT * FROM sync_data WHERE phone_number = ?", (phone,))
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
        return None

    def save_to_cache(self, db, phone: str, cal_name: str, flat_data: dict):
        db_data = {field: flat_data.get(f"sync.{field}", "") for field in self.SAVE_FIELDS}
        api_call_time = flat_data.get("sync.api_call_time", datetime.now(timezone.utc).isoformat())
        cursor = db.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sync_data (
                phone_number, cal_name, name, first_name, last_name, is_potential_spam,
                is_business, job_hint, company_hint, website_domain, company_domain, api_call_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            phone, cal_name,
            db_data.get("name", ""),
            db_data.get("first_name", ""),
            db_data.get("last_name", ""),
            str(db_data.get("is_potential_spam", "")),
            str(db_data.get("is_business", "")),
            db_data.get("job_hint", ""),
            db_data.get("company_hint", ""),
            db_data.get("website_domain", ""),
            db_data.get("company_domain", ""),
            api_call_time,
        ])
        db.commit()

    def cache_to_result(self, db_result: dict) -> dict:
        return {
            "sync.first_name": db_result.get("first_name", ""),
            "sync.last_name": db_result.get("last_name", ""),
            "sync.api_call_time": db_result.get("api_call_time", ""),
        }

    def empty_result(self) -> dict:
        return self.flatten({})

    def get_name_fields(self, result: dict) -> dict:
        return {
            "first": result.get("sync.first_name", ""),
            "last": result.get("sync.last_name", ""),
        }

    def set_name_fields(self, result: dict, first: str, last: str, common_name: str = ""):
        result["sync.first_name"] = first
        result["sync.last_name"] = last

    def get_primary_name_key(self) -> str:
        return "sync.first_name"

    @property
    def excel_columns(self) -> list:
        return [
            "sync.first_name", "sync.last_name", "sync.matching", "sync.risk_tier",
            "sync.translated", "sync.source", "sync.api_call_time",
        ]
