"""Boomplay transport. Two surfaces, both plain curl_cffi first (validated
2026-09-19):

APP API — https://android.boomplaymusic.com/BoomPlayer/<path>
  The Android app's own JSON endpoints, unsigned, no cookies, no anti-bot.
  Every catalogue read the app makes anonymously lives here (song info,
  album/playlist/artist collections via item/getMusics, charts, trending,
  genres, videos, podcasts, buzz, comments, song + user search). The API
  geolocates the caller from X-Forwarded-For, so `country` is honoured by
  sending refs.COUNTRY_IPS[country] — charts, trending, rankings and
  copyright availability all follow it; direct egress is enough.
  Error shape: HTTP 200 with a non-"0" `code` + `desc` ("invalid param",
  "Sorry, ... unavailable in your country ...", "Not found",
  "MUSIC_NOT_FOUND", "This post has been deleted."). Unknown ids and
  region-locked items produce the SAME copyright message, so app_json()
  raises BoomplayNotFound naming both causes.

WEBSITE — https://www.boomplay.com/<path>
  Server-rendered HTML, used only for what the app API does not serve
  anonymously (similar artists / songs, artist rankings + playlists, search
  tabs beyond songs/users, user profiles). Cloudflare's managed Turnstile
  challenge guards most paths PER PATH (charts, trending, videos, users are
  open): a request first goes out cookie-less; on a challenge the shared
  identity is minted ONCE on the browser box (browser_client.mint ->
  recipes/boomplay.py: a headed Chrome through the SAME sticky proxy
  port this pod's curl session replays on, so box and pod share the exit
  IP; cf_clearance is bound to IP + UA), validated over curl here, then its
  cookies + user-agent are replayed by every worker thread over curl_cffi.
  When that exit clears the real Chrome but rejects the same cookies from
  curl's TLS fingerprint, the identity is served in BROWSER mode: every
  web page is an in-page fetch on the box (browser_client.fetch ->
  recipes/boomplay_fetch.py, a kept browser keyed by the same proxy URL,
  closed after 300 s idle). A block on replay drops the identity and
  re-harvests on a fresh port. No browser runs on GKE (since 2026-10-22).

Failure taxonomy (scraper_errors bases -> HTTP in route_glue):
  BoomplayUpstreamError  transport failure / 5xx — retried
  BoomplayBlocked        Cloudflare challenge that survived a re-harvest
  BoomplayBadRequest     upstream rejected the params (HTTP 400)
  BoomplayNotFound       unknown id / region-locked / deleted
"""
import os
import sys
import threading
import time

# Allow direct execution (python boomplay/fetch.py): flat imports resolve
# like under the server. Idempotent when imported normally.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_client
import config
from urllib.parse import urlparse
import egress
from browser_client import BoxRefused, BoxUnavailable
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

from boomplay import refs
from scraper_utils import sessions

APP_BASE = "https://android.boomplaymusic.com/BoomPlayer/"
WEB_BASE = "https://www.boomplay.com"
STATIC_BASE = "https://source.boomplaymusic.com/"
IMPERSONATE = "chrome"
APP_TIMEOUT = 25
WEB_TIMEOUT = 30
BOX_SITE = "boomplay"              # recipes/boomplay.py (the mint)
BOX_FETCH = "boomplay-fetch"       # recipes/boomplay_fetch.py (browser mode)

# Cloudflare interstitial tells, checked against the first 6KB of a body.
CF_MARKERS = ("just a moment", "cf-chl", "challenge-platform", "cf_chl_opt",
              "performing security verification")
# A challenged path proves the identity end-to-end (the box mints on it too).
HARVEST_SEED_URL = f"{WEB_BASE}/artists/1182"


class BoomplayUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class BoomplayBlocked(BoomplayUpstreamError, Blocked):
    """Cloudflare challenge the identity could not clear."""


class BoomplayBadRequest(BadRequest):
    """Upstream rejected the params — never retried."""


class BoomplayNotFound(NotFound):
    """Unknown / region-locked / deleted item — never retried."""


# One curl session per cheroot worker thread per surface (a curl handle must
# not be shared across threads).
_local = threading.local()


def _session(kind):
    sess = getattr(_local, kind, None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if kind == "web":
            proxy = _web_proxy()
            if proxy:
                sess.proxies = {"http": proxy, "https": proxy}
            sess.web_proxy = proxy
        setattr(_local, kind, sess)
    return sess


def _drop_session(kind):
    sess = getattr(_local, kind, None)
    setattr(_local, kind, None)
    sessions.close_quietly(sess)


def _retrying(fn, what):
    """Run fn() up to MAX_RETRIES times on BoomplayUpstreamError."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except BoomplayBlocked:
            raise          # already re-harvested inside fn(); don't relaunch browsers
        except BoomplayUpstreamError as e:
            last = e
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


# ---- app API -----------------------------------------------------------------

def forwarded_ip(country):
    return refs.COUNTRY_IPS.get((country or refs.DEFAULT_COUNTRY).upper(),
                                refs.COUNTRY_IPS[refs.DEFAULT_COUNTRY])


def _app_once(path, params, country):
    headers = {"X-Forwarded-For": forwarded_ip(country),
               "accept": "application/json, text/plain, */*"}
    try:
        resp = _session("app").get(APP_BASE + path, params=params, headers=headers,
                                   timeout=APP_TIMEOUT)
    except Exception as e:
        _drop_session("app")
        raise BoomplayUpstreamError(f"request failed: {type(e).__name__}: {e}")
    if resp.status_code == 400:
        raise BoomplayBadRequest(f"HTTP 400 for {path}")
    if resp.status_code == 404:
        raise BoomplayUpstreamError(f"HTTP 404 for app path {path} (endpoint moved?)")
    if resp.status_code != 200:
        raise BoomplayUpstreamError(f"HTTP {resp.status_code} for {path}")
    try:
        return resp.json()
    except Exception:
        raise BoomplayUpstreamError(f"non-JSON body for {path}: {resp.text[:120]!r}")


def app_raw(path, params=None, country=None):
    """GET one app endpoint -> parsed JSON (dict), no error-code handling."""
    params = {k: v for k, v in (params or {}).items() if v is not None}
    return _retrying(lambda: _app_once(path, params, country), path)


# `code` values that mean "worked" across the app's mixed conventions.
_OK_CODES = (None, 0, "0", 200, "200")


def app_json(path, params=None, country=None, what="item"):
    """app_raw() + the error envelope -> BoomplayNotFound / BadRequest.
    Returns the payload unchanged when `code` is absent or success."""
    payload = app_raw(path, params, country)
    if not isinstance(payload, dict):
        raise BoomplayUpstreamError(f"unexpected payload for {path}: {type(payload).__name__}")
    code = payload.get("code")
    if code in _OK_CODES:
        return payload
    desc = str(payload.get("desc") or payload.get("msg") or "").strip()
    low = desc.lower()
    if str(code) in ("500",) and "busy" in low:
        raise BoomplayUpstreamError(f"{path}: {desc}")
    if str(code) == "400" and "bad request" in low:
        raise BoomplayNotFound(f"{what} not found")
    where = (country or refs.DEFAULT_COUNTRY).upper()
    if "copyright" in low or "territory" in low or "unavailable" in low:
        raise BoomplayNotFound(f"{what} not found, or not available in country {where} "
                               f"(Boomplay: {desc})")
    if "deleted" in low:
        raise BoomplayNotFound(f"{what} was deleted")
    raise BoomplayNotFound(f"{what} not found (Boomplay: {desc or code})")


def fetch_text(url):
    """GET a static CDN file (lyrics .lrc) -> text, or None when absent."""
    def once():
        try:
            resp = _session("app").get(url, timeout=APP_TIMEOUT)
        except Exception as e:
            _drop_session("app")
            raise BoomplayUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code in (403, 404):
            return None
        if resp.status_code != 200:
            raise BoomplayUpstreamError(f"HTTP {resp.status_code} for {url}")
        return resp.content.decode("utf-8", "replace")
    return _retrying(once, url)


# ---- website: shared Cloudflare identity -------------------------------------
# An identity is {"cookies": dict, "ua": str, "proxy": str|None, "mode":
# "curl"|"browser"}. Minted on the browser box, validated here, kept until a
# replay is blocked (no TTL), one for the whole process.

_identity = None
_identity_lock = threading.Lock()
_harvest_blocked_until = 0.0   # monotonic; set when every harvest attempt failed
_web_proxy_value = None    # the egress the identity (and every replay) uses


def _web_proxy():
    return _web_proxy_value


def looks_blocked(text):
    low = (text or "")[:6000].lower()
    return any(m in low for m in CF_MARKERS)


def _egress(proxy):
    return "direct" if not proxy else proxy.rsplit("@", 1)[-1]


def _harvest_identity(proxy):
    """One mint on the browser box through `proxy` (recipes/boomplay.py: a
    throwaway headed Chrome clears the challenge on the seed page); returns
    {cookies, ua, proxy, mode}. Raises RuntimeError when the box could not
    clear this exit (the caller retries on a fresh one) and
    BoomplayUpstreamError when the box itself is down. The identity is
    validated end-to-end over curl before it is handed out."""
    from curl_cffi import requests as curl_requests

    print(f"boomplay: harvesting web identity on the browser box (proxy={_egress(proxy)})...")
    try:
        ident = browser_client.mint(BOX_SITE, proxy=proxy)
    except BoxRefused as e:
        raise RuntimeError(f"the box could not clear the challenge on this exit: {e}")
    except BoxUnavailable as e:
        raise BoomplayUpstreamError(f"browser box unavailable: {e}")
    cookies = {c["name"]: c["value"] for c in ident.get("cookies") or []}
    ua = ident.get("user_agent")
    if not ua:
        raise RuntimeError("the box answered without a user-agent")

    # Fast path: the cookies replay over curl (direct egress, most exits).
    with curl_requests.Session(impersonate=IMPERSONATE) as sess:
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        resp = sess.get(HARVEST_SEED_URL, headers={"user-agent": ua}, cookies=cookies,
                        timeout=WEB_TIMEOUT)
    if resp.status_code == 200 and not looks_blocked(resp.text):
        print(f"boomplay: web identity ready ({len(cookies)} cookies, cf_clearance="
              f"{'yes' if 'cf_clearance' in cookies else 'no'})")
        return {"cookies": cookies, "ua": ua, "proxy": proxy, "mode": "curl"}

    # On some residential exits Cloudflare clears the real Chrome but rejects
    # the same cookies from curl's TLS fingerprint (same exit IP, verified).
    # Serve pages by in-page fetch from a kept browser on the box on that
    # same exit instead — it carries the browser's own clearance and
    # fingerprint. The probe proves that browser can read a challenged page.
    try:
        probe = browser_client.fetch(BOX_FETCH, url=HARVEST_SEED_URL, proxy=proxy)
    except BoxRefused as e:
        raise RuntimeError(f"in-browser fetch blocked too: {e}")
    except BoxUnavailable as e:
        raise BoomplayUpstreamError(f"browser box unavailable: {e}")
    if int(probe.get("status") or 0) != 200 or looks_blocked(probe.get("body")):
        raise RuntimeError(f"in-browser fetch blocked too: HTTP {probe.get('status')}")
    print(f"boomplay: web identity ready in BROWSER mode (curl replay got HTTP {resp.status_code})")
    return {"cookies": cookies, "ua": ua, "proxy": proxy, "mode": "browser"}


def _get_identity():
    global _identity, _web_proxy_value, _harvest_blocked_until
    with _identity_lock:
        if _identity is not None:
            return _identity
        # After a full round of failed harvests, fail fast for a while instead
        # of making every queued request mint again (up to 100 s each).
        wait = _harvest_blocked_until - time.monotonic()
        if wait > 0:
            raise BoomplayBlocked(f"Cloudflare clearance failed recently; retrying in {int(wait)} s")
        last = None
        for attempt in range(1, config.BOOMPLAY_HARVEST_ATTEMPTS + 1):
            proxy = config.boomplay_web_proxy()
            try:
                identity = _harvest_identity(proxy)
            except BoomplayUpstreamError:
                raise                   # the box is down: an upstream error, not a block; no cooldown
            except Exception as e:
                last = e
                print(f"boomplay: harvest attempt {attempt}/{config.BOOMPLAY_HARVEST_ATTEMPTS} failed: {e}")
                continue
            if proxy != _web_proxy_value:
                _web_proxy_value = proxy
            _identity = identity
            return _identity
        _harvest_blocked_until = time.monotonic() + getattr(config, "BOOMPLAY_HARVEST_COOLDOWN", 180)
        raise BoomplayBlocked(f"web identity harvest failed after "
                              f"{config.BOOMPLAY_HARVEST_ATTEMPTS} attempts (last: {last})")


def _invalidate_identity(stale):
    """Drop the identity iff it is still the one that got blocked. A
    browser-mode identity's kept browser lives on the box: it is closed
    there after 300 s idle (the next harvest uses a fresh port anyway)."""
    global _identity
    with _identity_lock:
        if _identity is stale:
            _identity = None


def _box_candidates(identity):
    """The kept browsers the box may serve this call from: INPAGE_BROWSER_SLOTS
    x BROWSER_BURST_FACTOR sessions on the identity's exit (one browser per
    identity until 2026-11-04); each warms its own Cloudflare clearance on
    that exit. The box picks an idle one or opens another while it has
    headroom."""
    # the port is part of the session: the box matches candidates by key
    # only, so a session without it would keep serving from browsers left
    # on a burned exit after a re-harvest (like envato's host@pPORT#i)
    port = urlparse(identity["proxy"]).port if identity.get("proxy") else "direct"
    return [(identity["proxy"], f"boomplay@p{port}#{i}")
            for i in range(config.burst_slots(config.INPAGE_BROWSER_SLOTS))]


def _browser_once(path, identity):
    """One page as an in-page fetch from one of the identity's kept
    browsers on the box (recipes/boomplay_fetch.py, keyed by the identity's
    proxy and a slot)."""
    try:
        _i, resp = browser_client.fetch_any(BOX_FETCH, _box_candidates(identity), url=WEB_BASE + path)
    except BoxRefused:
        return None                 # 403/429/interstitial: the exit is burned, like a blocked curl reply
    except BoxUnavailable as e:
        raise BoomplayUpstreamError(f"browser fetch failed: {e}")
    status, text = int(resp.get("status") or 0), resp.get("body") or ""
    if status in (403, 429) or looks_blocked(text):
        return None
    if status == 404:
        raise BoomplayNotFound(f"page not found: {path}")
    if status != 200:
        raise BoomplayUpstreamError(f"HTTP {status} for {path}")
    return text


def _web_once(path, identity):
    if identity and identity.get("mode") == "browser":
        return _browser_once(path, identity)
    sess = _session("web")
    if getattr(sess, "web_proxy", None) != _web_proxy():
        _drop_session("web")
        sess = _session("web")
    headers = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
               "accept-language": egress.site_accept_language("boomplay"),
               "referer": WEB_BASE + "/"}
    cookies = None
    if identity:
        headers["user-agent"] = identity["ua"]
        cookies = identity["cookies"]
    try:
        resp = sess.get(WEB_BASE + path, headers=headers, cookies=cookies, timeout=WEB_TIMEOUT)
    except Exception as e:
        _drop_session("web")
        raise BoomplayUpstreamError(f"request failed: {type(e).__name__}: {e}")
    blocked = resp.status_code in (403, 429) and looks_blocked(resp.text) \
        or "cf-mitigated" in {k.lower() for k in resp.headers.keys()}
    if blocked:
        return None
    if resp.status_code == 404:
        raise BoomplayNotFound(f"page not found: {path}")
    if resp.status_code >= 500:
        raise BoomplayUpstreamError(f"HTTP {resp.status_code} for {path}")
    if resp.status_code != 200:
        raise BoomplayUpstreamError(f"HTTP {resp.status_code} for {path}")
    return resp.text


def web_get(path):
    """GET one www.boomplay.com page -> HTML. Cookie-less first (open paths
    need no identity); a Cloudflare challenge switches to the shared
    identity, and a block on the identity re-harvests it once."""
    def once():
        identity = _identity
        html = _web_once(path, identity)
        if html is not None:
            return html
        if identity is None:
            identity = _get_identity()
            html = _web_once(path, identity)
            if html is not None:
                return html
        _invalidate_identity(identity)
        identity = _get_identity()
        html = _web_once(path, identity)
        if html is not None:
            return html
        _invalidate_identity(identity)
        raise BoomplayBlocked(f"Cloudflare challenge on {path} after a fresh identity")
    return _retrying(once, path)
