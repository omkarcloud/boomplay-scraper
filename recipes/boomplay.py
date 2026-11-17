"""Boomplay website identity (boomplay/fetch.py): Cloudflare's managed
Turnstile challenge guards most www.boomplay.com paths per path. The mint
loads a challenged artist page through the sticky residential exit GKE
sends (the same proxy port its curl session replays on: cf_clearance
is bound to IP + UA) and returns the cookies + UA once the real page title
("... | Boomplay") shows; Cloudflare titles its own interstitial
"www.boomplay.com", so a plain "not an interstitial" check is not enough
here. GKE validates the identity over curl and, when that exit rejects
curl's TLS with the browser's cookies, serves every web page through
recipes/boomplay_fetch.py instead."""
from recipes._cloudflare import CloudflareMint

WEB_BASE = "https://www.boomplay.com"
SEED_URL = WEB_BASE + "/artists/1182"


class Boomplay(CloudflareMint):
    name = "boomplay"
    variants = {"": SEED_URL}
    real_title_marker = "| boomplay"
    timeout = 100                     # residential exits clear in 30-80 s (HARVEST_CLEAR_TIMEOUT before 2026-10-22)
    ttl_seconds = 24 * 3600           # advisory: GKE keeps the identity until a replay is blocked


RECIPE = Boomplay
