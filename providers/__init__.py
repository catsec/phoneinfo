"""API provider registry.

To add a new provider:
1. Create providers/yourapi.py with a class inheriting BaseProvider
2. Import and register it here
"""

from providers.me import MEProvider
from providers.sync import SyncProvider

_PROVIDERS = {}


def _register(cls):
    provider = cls()
    _PROVIDERS[provider.name] = provider


_register(MEProvider)
_register(SyncProvider)


def get_provider(name: str):
    """Get a provider by name (e.g., 'me', 'sync')."""
    return _PROVIDERS.get(name)


def get_all_providers():
    """Get all registered providers."""
    return list(_PROVIDERS.values())


def get_configured_providers():
    """Get only providers that have valid credentials configured."""
    return [p for p in _PROVIDERS.values() if p.is_configured]
