"""/boomplay/genres — genre list and one genre's artists / albums /
playlists (item/getGenres, item/getGenresDetail; both page with
pageIndex/pageSize)."""
from boomplay import fetch, parsers, shared

PAGE_SIZE = 20


def get_list(country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("item/getGenres", {"pageIndex": 0, "pageSize": 100}, country)
    return {"genres": [g for g in (parsers.parse_genre(x) for x in payload.get("genres") or []) if g]}


def get_details(genre, page=1, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("item/getGenresDetail",
                             {"categoryID": genre, **shared.page_params(page, PAGE_SIZE)}, country,
                             what="genre")
    info = parsers.parse_genre(payload.get("category"))
    if info is None:
        # getGenresDetail only carries `category` on the first page.
        info = next((g for g in get_list(country)["genres"] if str(g["id"]) == str(genre)), None)
    artists = [a for a in (parsers.parse_artist(x) for x in payload.get("artists") or []) if a]
    albums = [a for a in (parsers.parse_album(x) for x in payload.get("albums") or []) if a]
    playlists = [p for p in (parsers.parse_playlist(x) for x in payload.get("playlists") or []) if p]
    if info is None and page == 1 and not (artists or albums or playlists):
        raise fetch.BoomplayNotFound("genre not found")
    returned = max(len(artists), len(albums), len(playlists))
    return {"genre": info, "artists": artists, "albums": albums, "playlists": playlists,
            "pagination": parsers.page_block(page, PAGE_SIZE, returned)}
