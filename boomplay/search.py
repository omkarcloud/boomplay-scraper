"""/boomplay/search/* — search.

App API (fast, `country`-aware): item/searchMusics (songs),
item/searchUser (users), item/searchAssociate (autocomplete),
search/topMusics + search/topArtists (popular on search),
search/getBarKeyWordsList + item/getKeywords (trending searches).
Website (/search/<tab>/<query>?page=N, 12 per page, Cloudflare identity):
artists / albums / playlists / videos / podcasts — the app has no anonymous
search for those.
"""
from urllib.parse import quote

from boomplay import fetch, parsers, refs, shared, web

PAGE_SIZE = 20
WEB_PAGE_SIZE = 12


def search_songs(query, page=1, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("item/searchMusics",
                             {"content": query, **shared.page_params(page, PAGE_SIZE)}, country)
    items = parsers.parse_songs(payload.get("musics"))
    return {"query": query, "songs": items, "pagination": shared.paged(items, page, PAGE_SIZE)}


def search_users(query, page=1, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("item/searchUser",
                             {"content": query, **shared.page_params(page, PAGE_SIZE)}, country)
    items = [u for u in (parsers.user_ref(x) for x in payload.get("users") or []) if u]
    return {"query": query, "users": items, "pagination": shared.paged(items, page, PAGE_SIZE)}


_SUGGEST_TYPES = {"ARTIST": "artist", "ALBUM": "album", "MUSIC": "song", "PLAYLIST": "playlist",
                  "VIDEO": "video", "USER": "user", "SHOW": "podcast", "EPISODE": "episode"}


def suggestions(query, country=None):
    payload = fetch.app_json("item/searchAssociate", {"content": query}, shared.country_of(country))
    out = []
    for k in payload.get("keywords") or []:
        if not isinstance(k, dict) or not parsers._str(k.get("item")):
            continue
        out.append({"text": parsers._str(k.get("item")),
                    "type": _SUGGEST_TYPES.get(str(k.get("itemType") or "").upper()),
                    "artist_name": parsers._str(k.get("artistName")),
                    "is_new_release": k.get("newRelease") if isinstance(k.get("newRelease"), bool) else None})
    return {"query": query, "suggestions": out}


def popular_songs(country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("search/topMusics", {}, country)
    return {"country": country, "songs": parsers.parse_songs((payload.get("data") or {}).get("musics"))}


def popular_artists(country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("search/topArtists", {}, country)
    items = [a for a in (parsers.parse_artist(x) for x in (payload.get("data") or {}).get("artists") or []) if a]
    return {"country": country, "artists": items}


def trending_keywords(country=None):
    country = shared.country_of(country)
    bar = fetch.app_json("search/getBarKeyWordsList", {}, country)
    out, seen = [], set()
    for k in bar.get("barKeyWordsList") or []:
        if not isinstance(k, dict) or not parsers._str(k.get("keyword")):
            continue
        args = ((k.get("deeplinkData") or {}).get("actionArgs") or {})
        kind = _SUGGEST_TYPES.get(str(k.get("type") or "").upper())
        # collection shortcuts carry colID, song shortcuts musicID
        target = parsers._int(args.get("colID") or args.get("musicID"))
        link_kind = kind if kind in ("album", "playlist", "artist", "song") else None
        out.append({"keyword": parsers._str(k.get("keyword")), "type": kind,
                    "target": {"id": target, "name": parsers._str(args.get("name")),
                               "link": parsers.entity_link(link_kind, target) if link_kind else None}
                    if target else None})
        seen.add(parsers._str(k.get("keyword")))
    try:
        extra = fetch.app_json("item/getKeywords", {}, country)
    except fetch.BoomplayNotFound:
        extra = {}
    for k in extra.get("keywords") or []:
        word = parsers._str((k or {}).get("keyword"))
        if word and word not in seen:
            out.append({"keyword": word, "type": _SUGGEST_TYPES.get(str(k.get("itemType") or "").upper()),
                        "target": None})
    return {"country": country, "keywords": out}


def _web_search(tab, query, page):
    path = f"/search/{tab}/{quote(query, safe='')}"
    if page > 1:
        path += f"?page={page}"
    return fetch.web_get(path)


def search_web(kind, query, page=1):
    """artists / albums / playlists / videos via the website search tabs."""
    tab = refs.WEB_SEARCH_TABS[kind]
    html = _web_search(tab, query, page)
    items = web.parse_search_cards(html, tab)
    pagination = parsers.page_block(page, WEB_PAGE_SIZE, len(items))
    if not web.has_more(html) and len(items) < WEB_PAGE_SIZE:
        pagination["total_pages"] = page
    return {"query": query, kind: items, "pagination": pagination}


def search_artists(query, page=1):
    return search_web("artists", query, page)


def search_albums(query, page=1):
    return search_web("albums", query, page)


def search_playlists(query, page=1):
    return search_web("playlists", query, page)


def search_videos(query, page=1):
    return search_web("videos", query, page)


def search_podcasts(query, page=1):
    html = _web_search("podcast", query, page)
    found = web.parse_search_podcasts(html)
    returned = max(len(found["podcasts"]), len(found["episodes"]))
    return {"query": query, **found, "pagination": parsers.page_block(page, WEB_PAGE_SIZE, returned)}
