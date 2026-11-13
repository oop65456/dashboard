"""One place for all web requests: a timeout, polite retries, and key-safe errors."""
import time

import requests

from . import env

USER_AGENT = "signal-dashboard/0.1 (personal, read-only)"


class FetchError(Exception):
    """A request failed. The message never contains an API key."""


def get_json(url, params=None, headers=None, timeout=20, retries=2):
    """GET a URL and return the decoded JSON.

    - 429 (too many requests) or a 5xx server error: wait and try again, up to `retries` times.
    - Anything else that fails: raise FetchError with the key values scrubbed out.
    """
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    wait = 2
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(wait)
                wait *= 2
                continue
            raise FetchError(env.scrub(f"network error: {e}")) from None
        if r.status_code == 429 or r.status_code >= 500:
            if attempt < retries:
                # Respect the server's Retry-After header if it sends one (in seconds).
                time.sleep(float(r.headers.get("Retry-After", wait)))
                wait *= 2
                continue
        if r.status_code == 400 and "No data is available" in r.text:
            return r.json()
        if r.status_code != 200:
            raise FetchError(env.scrub(f"HTTP {r.status_code}: {r.text[:200]}"))
        try:
            return r.json()
        except ValueError:
            raise FetchError(env.scrub(f"not JSON: {r.text[:200]}")) from None
    raise FetchError("gave up after retries")
