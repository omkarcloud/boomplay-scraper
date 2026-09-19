"""Helpers every /boomplay/* endpoint module shares: 1-based page -> the app's
0-based pageIndex, `country` defaults, and resolving a ref (numeric id OR
EQ web id) to the numeric id + web id pair the comment / web surfaces need.
"""
from boomplay import fetch, parsers, refs

DEFAULT_PAGE_SIZE = 20


def country_of(country):
    return (country or refs.DEFAULT_COUNTRY).upper()


def page_params(page, page_size):
    return {"pageIndex": max(int(page or 1), 1) - 1, "pageSize": int(page_size)}


def collection(ref, country, col_type=None, page=1, page_size=10, what="item"):
    """item/getMusics for an album (5) / playlist (1) / artist (2) ref ->
    the raw payload (tracks + detailCol [+ albums/videos for artists])."""
    params = {"colID": ref, **page_params(page, page_size)}
    if col_type:
        params["colType"] = col_type
    payload = fetch.app_json("item/getMusics", params, country, what=what)
    if not isinstance(payload.get("detailCol"), dict):
        raise fetch.BoomplayNotFound(f"{what} not found")
    return payload


def expect_type(detail, kind, what):
    """The same colID space holds albums, playlists and artists — refuse a
    playlist id on an album route (and so on) instead of mis-parsing it."""
    actual = parsers.COL_TYPES.get(parsers._int(detail.get("colType")))
    if actual and actual != kind:
        raise fetch.BoomplayNotFound(f"{what} not found (that id is a {actual}, not a {kind})")


def song_ids(ref, country):
    """song ref -> (numeric musicID, EQ web id). getMusicInfo decodes an EQ
    id; content/music/getArtistInfo (numeric only) carries the EQ id."""
    if refs.is_web_id(ref):
        info = fetch.app_json("item/getMusicInfo", {"musicID": ref}, country, what="song")
        ident = parsers._int(info.get("musicID"))
        if not ident:
            raise fetch.BoomplayNotFound("song not found")
        return ident, ref
    payload = fetch.app_json("content/music/getArtistInfo", {"musicID": ref}, country, what="song")
    music = ((payload.get("data") or {}).get("music") or {})
    ident = parsers._int(music.get("musicID"))
    if not ident:
        raise fetch.BoomplayNotFound("song not found")
    return ident, parsers._str(music.get("musicMid"))


def collection_ids(ref, country, kind):
    """album / playlist / artist ref -> (numeric colID, EQ web id)."""
    col_type = {"album": 5, "playlist": 1, "artist": 2}[kind]
    if not refs.is_web_id(ref):
        return int(ref), None
    detail = collection(ref, country, col_type, page_size=1, what=kind)["detailCol"]
    expect_type(detail, kind, kind)
    return parsers._int(detail.get("colID")), parsers._str(detail.get("colMid"))


def paged(items, page, page_size, total=None):
    """Attach the scraper pagination block to an item list."""
    return parsers.page_block(page, page_size, len(items), total)


def slice_page(items, page, page_size):
    """Local pagination over a full upstream list."""
    start = (page - 1) * page_size
    return items[start:start + page_size], parsers.page_block(page, page_size, 0, len(items))


def list_page(path, params, list_key, page, page_size, country):
    """One browse page from a pageIndex/pageSize list endpoint. The app API
    has poisoned cache entries for some (country, filter, pageSize) keys that
    answer an empty list (seen 2026-09-19: item/getPlaylists NG + genre 42 +
    pageSize 20 -> [], same query at pageSize 10/21 or GH/KE -> full). An
    empty page is re-read as two aligned half pages, which cover exactly the
    same offsets."""
    items = fetch.app_json(path, {**params, **page_params(page, page_size)}, country).get(list_key) or []
    if items or page_size % 2:
        return items
    half = page_size // 2
    out = []
    for index in (2 * (page - 1), 2 * (page - 1) + 1):
        chunk = fetch.app_json(path, {**params, "pageIndex": index, "pageSize": half}, country).get(list_key) or []
        out.extend(chunk)
        if len(chunk) < half:
            break
    return out
