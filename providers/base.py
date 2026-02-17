"""Base class for API providers."""

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Abstract base class that all API providers must implement.

    To add a new provider:
    1. Create providers/yourapi.py with a class inheriting BaseProvider
    2. Implement all abstract methods
    3. Register in providers/__init__.py
    """

    name = ""           # e.g., "me", "sync" — used as prefix and dict key
    display_name = ""   # e.g., "ME", "SYNC" — for UI display

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has valid credentials configured."""

    @abstractmethod
    def call_api(self, phone: str):
        """Call external API for a phone number.

        Returns: raw API response dict, or None if not found.
        Raises: ValueError on API errors.
        """

    @abstractmethod
    def flatten(self, api_result: dict) -> dict:
        """Flatten API result to prefixed dict (e.g., me.common_name).

        Should handle empty dict (no result) gracefully.
        """

    @abstractmethod
    def init_table(self, conn):
        """Create/migrate DB table for this provider."""

    @abstractmethod
    def get_from_cache(self, db, phone: str):
        """Get cached result from DB.

        Returns: dict with DB column names, or None if not found.
        """

    @abstractmethod
    def save_to_cache(self, db, phone: str, cal_name: str, flat_data: dict):
        """Save flattened result to DB cache."""

    @abstractmethod
    def cache_to_result(self, db_result: dict) -> dict:
        """Convert DB record to prefixed response dict."""

    @abstractmethod
    def empty_result(self) -> dict:
        """Return empty/default result dict with all expected prefixed keys."""

    @abstractmethod
    def get_name_fields(self, result: dict) -> dict:
        """Extract name fields for scoring.

        Returns: dict with keys 'first', 'last', and optionally 'common_name'.
        """

    @abstractmethod
    def set_name_fields(self, result: dict, first: str, last: str, common_name: str = ""):
        """Write cleaned name fields back into the result dict."""

    @abstractmethod
    def get_primary_name_key(self) -> str:
        """Key used to check for errors/not-in-cache.

        e.g., 'me.common_name' or 'sync.first_name'
        """

    @property
    @abstractmethod
    def excel_columns(self) -> list:
        """Ordered list of column keys for Excel output."""
