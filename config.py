"""Configuration for the Boomplay Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT             port the API listens on (default 8000)
    BOOMPLAY_PROXY   proxy URL for the boomplay.com website requests, e.g.
                     http://user:pass@host:port (default: none — direct).
                     Most endpoints read Boomplay's app API, which needs no
                     proxy at all — the `country` param picks the market.
                     A handful (similar songs/artists, artist playlists,
                     website search tabs, user profiles) read boomplay.com,
                     where a real Chrome clears Cloudflare once. Direct egress
                     clears fastest; set a proxy only to read the website from
                     another country (a song's web page only renders where the
                     song is licensed).

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# Browser attempts to clear Cloudflare on boomplay.com before giving up.
BOOMPLAY_HARVEST_ATTEMPTS = 3

BOOMPLAY_PROXY = os.environ.get("BOOMPLAY_PROXY") or None
BOOMPLAY_WEB_PROXY_COUNTRY = None


def boomplay_web_proxy():
    """The proxy the website requests go through (None = direct)."""
    return os.environ.get("BOOMPLAY_PROXY") or None


# ---- added by the sync: defaults for a direct run ----
INPAGE_BROWSER_SLOTS = 1
def burst_slots(share):
    return share


def exit_geo(proxy, timeout=12):
    """Geo of a proxy's exit IP, looked up THROUGH the proxy (ip-api.com, free
    tier, keyed per exit IP so the quota is never shared). Returns the dict
    {countryCode, regionName, city, timezone, query} or None on any failure —
    callers keep their configured/system timezone then."""
    try:
        import requests
        r = requests.get(
            "http://ip-api.com/json/?fields=status,countryCode,regionName,city,timezone,query",
            proxies={"http": proxy, "https": proxy}, timeout=timeout)
        d = r.json()
        if d.get("status") == "success" and d.get("timezone"):
            return d
    except Exception:
        pass
    return None

