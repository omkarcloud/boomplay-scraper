"""/boomplay/playlists/* — playlist details + tracks, recommendations,
genre browse and comments.

App API: item/getMusics?colID=<playlist> (detailCol: owner, description,
counts; every track in one call, up to the playlist's 100-song chart size),
item/getRecommendCols, item/getPlaylists (+ item/getCatalog?type=PLAYLIST
for the genre list).
"""
from boomplay import comments, fetch, parsers, shared

BROWSE_PAGE_SIZE = 20


def get_details(playlist, country=None):
    country = shared.country_of(country)
    payload = shared.collection(playlist, country, col_type=1, page_size=100, what="playlist")
    detail = payload["detailCol"]
    shared.expect_type(detail, "playlist", "playlist")
    return {"playlist": parsers.parse_playlist(detail),
            "tracks": parsers.parse_songs(payload.get("musics"))}


def get_recommendations(playlist, country=None):
    country = shared.country_of(country)
    ident = shared.collection_ids(playlist, country, "playlist")[0]
    payload = fetch.app_json("item/getRecommendCols", {"colID": ident, "pageIndex": 0, "pageSize": 20},
                             country, what="playlist")
    return {"recommendations": parsers.parse_collections(payload.get("cols"))}


def get_genres(country=None):
    """Genres the playlist browser filters on (id 0 = all)."""
    payload = fetch.app_json("item/getCatalog", {"type": "PLAYLIST"}, shared.country_of(country))
    return {"genres": [{"id": parsers._int(c.get("categoryID")), "name": parsers._str(c.get("name"))}
                       for c in payload.get("categorys") or [] if isinstance(c, dict)]}


def browse(genre=None, page=1, country=None):
    country = shared.country_of(country)
    params = {"categoryID": genre} if genre else {}
    raw = shared.list_page("item/getPlaylists", params, "playlists", page, BROWSE_PAGE_SIZE, country)
    items = [p for p in (parsers.parse_playlist(c) for c in raw) if p]
    return {"playlists": items, "pagination": shared.paged(items, page, BROWSE_PAGE_SIZE)}


def get_comments(playlist, page=1, sort="newest", country=None):
    return comments.get_comments("playlist", playlist, page, sort, country)
