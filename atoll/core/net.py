"""Polling limits for remote APIs."""
import urllib.error

FETCH_EVERY, BACKOFF = 90, 300  # seconds between Claude usage fetches, and after an error


def backoff_seconds(err):
    """Honor Retry-After on 429s, never retrying sooner than BACKOFF."""
    if isinstance(err, urllib.error.HTTPError) and err.headers:
        try:
            return max(BACKOFF, int(err.headers.get("Retry-After") or 0))
        except ValueError:
            pass
    return BACKOFF
