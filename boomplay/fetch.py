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
  identity is minted ONCE by a headed patchright Chrome (real mouse click on
  the Turnstile checkbox when it renders), validated over curl, then its
  cookies + user-agent are replayed by every worker thread over curl_cffi on
  the SAME egress (cf_clearance is bound to IP + UA). A block on replay
  drops the identity and re-harvests.

Failure taxonomy (scraper_errors bases -> HTTP in route_glue):
  BoomplayUpstreamError  transport failure / 5xx — retried
  BoomplayBlocked        Cloudflare challenge that survived a re-harvest
  BoomplayBadRequest     upstream rejected the params (HTTP 400)
  BoomplayNotFound       unknown id / region-locked / deleted
"""
import os
import random
import sys
import threading
import time

# Allow direct execution (python boomplay/fetch.py): flat imports resolve
# like under the server. Idempotent when imported normally.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

from boomplay import refs

APP_BASE = "https://android.boomplaymusic.com/BoomPlayer/"
WEB_BASE = "https://www.boomplay.com"
STATIC_BASE = "https://source.boomplaymusic.com/"
IMPERSONATE = "chrome"
APP_TIMEOUT = 25
WEB_TIMEOUT = 30

# Cloudflare interstitial tells, checked against the first 6KB of a body.
CF_MARKERS = ("just a moment", "cf-chl", "challenge-platform", "cf_chl_opt",
              "performing security verification")
# A challenged path proves the identity end-to-end.
HARVEST_SEED_URL = f"{WEB_BASE}/artists/1182"
HARVEST_CLEAR_TIMEOUT = 100    # seconds for the challenge to clear (residential exits: 30-80 s)
HARVEST_POLL = 1.0
CLICK_EVERY = 15               # re-click a re-presented checkbox after N s
MAX_CLICKS = 3


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
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


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

_identity = None           # {"cookies": dict, "ua": str, "proxy": str|None}
_identity_lock = threading.Lock()
_harvest_blocked_until = 0.0   # monotonic; set when every harvest attempt failed
_web_proxy_value = None    # the egress the identity (and every replay) uses


def _web_proxy():
    return _web_proxy_value


def looks_blocked(text):
    low = (text or "")[:6000].lower()
    return any(m in low for m in CF_MARKERS)


def _click_turnstile(page):
    """Real mouse click on the Turnstile checkbox: the widget iframe's
    bounding box, x at 1/9 of the width (the checkbox), y at the middle.
    Returns True when a challenge frame was found and clicked."""
    for frame in page.frames:
        if not frame.url.startswith("https://challenges.cloudflare.com"):
            continue
        try:
            box = frame.frame_element().bounding_box()
        except Exception:
            box = None
        if not box or box.get("width", 0) < 50:
            continue
        x = box["x"] + box["width"] / 9 + random.uniform(-5, 5)
        y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)
        page.mouse.move(x, y, steps=random.randint(10, 25))
        page.wait_for_timeout(random.randint(100, 300))
        page.mouse.down()
        page.wait_for_timeout(random.randint(50, 150))
        page.mouse.up()
        return True
    return False


def _harvest_identity(proxy):
    """One throwaway headed patchright Chrome clears the challenge on the
    seed page; returns {cookies, ua, proxy}. Raises on failure (the caller
    retries on a fresh exit). The identity is validated end-to-end over curl
    before it is handed out."""
    from curl_cffi import requests as curl_requests
    from chrome_manager import create_scope
    from patchright_driver import PatchrightDriver

    print(f"boomplay: harvesting web identity via patchright "
          f"(proxy={'direct' if not proxy else proxy.rsplit('@', 1)[-1]})...")
    with create_scope():
        driver = PatchrightDriver(proxy_url=proxy, headless=False)
    try:
        try:
            driver.goto(HARVEST_SEED_URL, referer="https://www.google.com/")
        except Exception as e:
            raise RuntimeError(f"seed navigation failed: {e}")
        start = time.monotonic()
        clicks, last_click = 0, None
        while True:
            # Cloudflare's interstitial is itself titled "www.boomplay.com",
            # so a title merely containing "boomplay" proves nothing — the
            # real pages end in "| Boomplay" / "| Boomplay Music".
            title = (driver.title() or "").lower()
            if "| boomplay" in title and "just a moment" not in title:
                break
            elapsed = time.monotonic() - start
            if elapsed > HARVEST_CLEAR_TIMEOUT:
                raise RuntimeError(f"Cloudflare challenge did not clear (clicks={clicks})")
            due = (last_click is None and elapsed >= 3) or \
                  (last_click is not None and time.monotonic() - last_click >= CLICK_EVERY)
            if due and clicks < MAX_CLICKS and driver.call(_click_turnstile):
                clicks += 1
                last_click = time.monotonic()
            time.sleep(HARVEST_POLL)
        # The title flips to the real page while Cloudflare's redirect is
        # still loading; reading the page then dies with "Execution context
        # was destroyed". Let the navigation settle and retry the read.
        ua = None
        for _ in range(10):
            try:
                driver.call(lambda page: page.wait_for_load_state("domcontentloaded", timeout=15000))
                ua = driver.evaluate("navigator.userAgent")
                break
            except Exception:
                time.sleep(1)
        if not ua:
            raise RuntimeError("page never settled after the challenge cleared")
        cookies = {c["name"]: c["value"]
                   for c in driver.call(lambda page: page.context.cookies(WEB_BASE))}
    except BaseException:
        driver.close()
        raise

    # Fast path: the cookies replay over curl (direct egress, most exits).
    with curl_requests.Session(impersonate=IMPERSONATE) as sess:
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        resp = sess.get(HARVEST_SEED_URL, headers={"user-agent": ua}, cookies=cookies,
                        timeout=WEB_TIMEOUT)
    if resp.status_code == 200 and not looks_blocked(resp.text):
        driver.close()
        print(f"boomplay: web identity ready ({len(cookies)} cookies, clicks={clicks})")
        return {"cookies": cookies, "ua": ua, "proxy": proxy, "driver": None}

    # On some residential exits Cloudflare clears the real Chrome but rejects
    # the same cookies from curl's TLS fingerprint (same exit IP, verified).
    # Keep that Chrome and serve pages by in-page fetch instead — it carries
    # the browser's own clearance and fingerprint.
    try:
        probe = driver.get(HARVEST_SEED_URL, referrer=WEB_BASE + "/")
        if probe.status_code != 200 or looks_blocked(probe.text):
            raise RuntimeError(f"in-browser fetch blocked too: HTTP {probe.status_code}")
    except BaseException:
        driver.close()
        raise
    print(f"boomplay: web identity ready in BROWSER mode (curl replay got HTTP "
          f"{resp.status_code}; clicks={clicks})")
    return {"cookies": cookies, "ua": ua, "proxy": proxy, "driver": driver}


def _get_identity():
    global _identity, _web_proxy_value, _harvest_blocked_until
    with _identity_lock:
        if _identity is not None:
            return _identity
        # After a full round of failed harvests, fail fast for a while instead
        # of making every queued request relaunch browsers (minutes each).
        wait = _harvest_blocked_until - time.monotonic()
        if wait > 0:
            raise BoomplayBlocked(f"Cloudflare clearance failed recently; retrying in {int(wait)} s")
        last = None
        for attempt in range(1, config.BOOMPLAY_HARVEST_ATTEMPTS + 1):
            proxy = config.boomplay_web_proxy()
            try:
                identity = _harvest_identity(proxy)
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
    global _identity
    with _identity_lock:
        if _identity is stale:
            _identity = None
            driver = (stale or {}).get("driver")
            if driver is not None:
                try:
                    driver.close()
                except Exception:
                    pass


def _browser_once(path, identity):
    """One page through the identity's kept Chrome (in-page fetch)."""
    try:
        resp = identity["driver"].get(WEB_BASE + path, referrer=WEB_BASE + "/")
    except Exception as e:
        _invalidate_identity(identity)
        raise BoomplayUpstreamError(f"browser fetch failed: {type(e).__name__}: {e}")
    if resp.error and not resp.status_code:
        raise BoomplayUpstreamError(f"browser fetch failed: {resp.error}")
    if resp.status_code in (403, 429) or looks_blocked(resp.text):
        return None
    if resp.status_code == 404:
        raise BoomplayNotFound(f"page not found: {path}")
    if resp.status_code != 200:
        raise BoomplayUpstreamError(f"HTTP {resp.status_code} for {path}")
    return resp.text


def _web_once(path, identity):
    if identity and identity.get("driver") is not None:
        return _browser_once(path, identity)
    sess = _session("web")
    if getattr(sess, "web_proxy", None) != _web_proxy():
        _drop_session("web")
        sess = _session("web")
    headers = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
               "accept-language": "en-US,en;q=0.9",
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


def warm_identity():
    """Optional startup hook: harvest before the first web request needs it."""
    _get_identity()
