"""Boomplay browser mode (boomplay/fetch.py): on some residential exits
Cloudflare clears the real Chrome but rejects the same cookies from curl's
TLS fingerprint, so GKE serves every www.boomplay.com page as an in-page
fetch from a kept browser on that exit. One browser per proxy session,
warmed on the challenged seed page, parked on robots.txt, closed after
300 s idle; a 403/429 or an interstitial body fails the lease and GKE
re-harvests on a fresh exit."""
from recipes._cloudflare import CloudflareInPage
from recipes.boomplay import SEED_URL, WEB_BASE


class BoomplayFetch(CloudflareInPage):
    name = "boomplay-fetch"
    variants = {"": SEED_URL}
    home = WEB_BASE + "/"
    park_url = WEB_BASE + "/robots.txt"


RECIPE = BoomplayFetch
