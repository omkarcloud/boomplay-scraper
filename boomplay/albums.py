"""/boomplay/albums/* — album details with the full tracklist,
recommendations and comments.

App API: item/getMusics?colID=<album>&colType=5 returns `detailCol` (the
album: type, year, description, artist, play / favourite / share / comment /
download counts, song count) plus every track in one call — the upstream
ignores paging for albums. item/getRecommendCols -> related collections.
"""
from boomplay import comments, fetch, parsers, shared


def get_details(album, country=None):
    country = shared.country_of(country)
    payload = shared.collection(album, country, col_type=5, page_size=100, what="album")
    detail = payload["detailCol"]
    shared.expect_type(detail, "album", "album")
    return {"album": parsers.parse_album(detail), "tracks": parsers.parse_songs(payload.get("musics"))}


def get_recommendations(album, country=None):
    country = shared.country_of(country)
    ident = shared.collection_ids(album, country, "album")[0]
    payload = fetch.app_json("item/getRecommendCols", {"colID": ident, "pageIndex": 0, "pageSize": 20},
                             country, what="album")
    return {"recommendations": parsers.parse_collections(payload.get("cols"))}


def get_comments(album, page=1, sort="newest", country=None):
    return comments.get_comments("album", album, page, sort, country)
