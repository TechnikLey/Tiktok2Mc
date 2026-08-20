"""Shared API key store — avoids circular imports between server.py and routes."""

_api_key: str = ""


def get_api_key() -> str:
    """Return the configured API key (empty string = auth disabled)."""
    return _api_key


def set_api_key(key: str) -> None:
    """Store the API key at startup."""
    global _api_key
    _api_key = key
