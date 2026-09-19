"""/boomplay/artists/* — artist details, songs / albums / videos (paged),
similar artists + web rankings, playlists, comments, browse and rankings.

App API: item/getMusics?colID=<artist>&colType=2 returns `detailCol` (bio,
gender, country, follower / play / favourite / share / comment / download
counts, song / album / video / playlist counts) and pages songs, albums AND
videos together with pageIndex/pageSize. item/getArtists browses by genre /
gender / region / first letter; artist/getArtistRankList ranks artists by
period (the ranking follows `country`).
Website: /artists/<id> for the current + all-time rank, similar artists and
the playlists shelf (not exposed anonymously by the app).
"""
from boomplay import comments, fetch, parsers, refs, shared, web

PAGE_SIZE = 20
PREVIEW_SIZE = 10


def _artist_payload(artist, country, page, page_size):
    payload = shared.collection(artist, country, col_type=2, page=page, page_size=page_size,
                                what="artist")
    shared.expect_type(payload["detailCol"], "artist", "artist")
    return payload


def get_details(artist, country=None):
    country = shared.country_of(country)
    payload = _artist_payload(artist, country, 1, PREVIEW_SIZE)
    return {
        "artist": parsers.parse_artist(payload["detailCol"]),
        "top_songs": parsers.parse_songs(payload.get("musics")),
        "albums": [a for a in (parsers.parse_album(x) for x in payload.get("albums") or []) if a],
        "videos": [v for v in (parsers.parse_video(x) for x in payload.get("videos") or []) if v],
    }


def _paged_part(artist, page, country, key, parse, total_key):
    country = shared.country_of(country)
    payload = _artist_payload(artist, country, page, PAGE_SIZE)
    items = [x for x in (parse(i) for i in payload.get(key) or []) if x]
    total = payload["detailCol"].get(total_key)
    return items, parsers.page_block(page, PAGE_SIZE, len(items), total)


def get_songs(artist, page=1, country=None):
    items, pagination = _paged_part(artist, page, country, "musics", parsers.parse_song, "songCount")
    return {"songs": items, "pagination": pagination}


def get_albums(artist, page=1, country=None):
    items, pagination = _paged_part(artist, page, country, "albums", parsers.parse_album, "albumCount")
    return {"albums": items, "pagination": pagination}


def get_videos(artist, page=1, country=None):
    items, pagination = _paged_part(artist, page, country, "videos", parsers.parse_video, "videoCount")
    return {"videos": items, "pagination": pagination}


def _artist_page(artist, country):
    # /artists/<numeric id> renders the full page; an EQ id works as-is too.
    page = web.parse_artist_page(fetch.web_get(f"/artists/{artist}"))
    if not page.get("name"):
        raise fetch.BoomplayNotFound("artist not found")
    return page


def get_similar(artist, country=None):
    page = _artist_page(artist, shared.country_of(country))
    return {
        "artist": {"id": page["id"], "web_id": page["web_id"], "name": page["name"],
                   "link": parsers.entity_link("artist", page["web_id"] or page["id"]),
                   "country": page["country"], "rankings": page["rankings"]},
        "similar_artists": page["similar_artists"],
    }


def get_playlists(artist, country=None):
    page = _artist_page(artist, shared.country_of(country))
    return {"playlist_count": page["playlist_count"], "playlists": page["playlists"]}


def get_comments(artist, page=1, sort="newest", country=None):
    return comments.get_comments("artist", artist, page, sort, country)


def get_filters(country=None):
    """Genre ids for /artists/browse (item/getCatalog?type=ARTIST)."""
    payload = fetch.app_json("item/getCatalog", {"type": "ARTIST"}, shared.country_of(country))
    return {
        "genres": [{"id": parsers._int(c.get("categoryID")), "name": parsers._str(c.get("name"))}
                   for c in payload.get("categorys") or [] if isinstance(c, dict)],
        "genders": list(refs.ARTIST_GENDERS),
        "regions": list(refs.ARTIST_REGIONS),
        "letters": [parsers._str(a.get("firstAlphaID")) or "all" for a in payload.get("firstAlpha") or []],
    }


def browse(genre=None, gender="all", region="all", letter=None, page=1, country=None):
    country = shared.country_of(country)
    params = {}
    if genre:
        params["categoryID"] = genre
    if refs.ARTIST_GENDERS.get(gender):
        params["sex"] = refs.ARTIST_GENDERS[gender]
    if refs.ARTIST_REGIONS.get(region):
        params["countryCode"] = refs.ARTIST_REGIONS[region]
    if letter:
        params["firstAlpha"] = letter
    raw = shared.list_page("item/getArtists", params, "artists", page, PAGE_SIZE, country)
    items = [a for a in (parsers.parse_artist(x) for x in raw) if a]
    return {"artists": items, "pagination": shared.paged(items, page, PAGE_SIZE)}


def get_rankings(period="week", page=1, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("artist/getArtistRankList",
                             {"time": refs.RANKING_PERIODS[period], **shared.page_params(page, PAGE_SIZE)},
                             country)
    items = [a for a in (parsers.parse_artist(x) for x in payload.get("data") or []) if a]
    return {"period": period, "country": country, "artists": items,
            "pagination": shared.paged(items, page, PAGE_SIZE)}
