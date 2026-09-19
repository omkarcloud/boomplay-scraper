"""/boomplay/songs/* — song details, lyrics, playlists featuring a song,
similar songs and comments.

App API: item/getMusicInfo (metadata, artist, album, label, year),
item/getMusicMutableData (live favourite / comment counts),
content/music/getArtistInfo (every credited artist + the EQ web id),
item/getLyricID (+ the .lrc file on the CDN), music/getPlaylistsByMusicID.
ai/getRecommendSongs for similar songs (with play counts).
"""
from concurrent.futures import ThreadPoolExecutor

from boomplay import comments, fetch, parsers, refs, shared


def _info(song, country):
    return fetch.app_json("item/getMusicInfo", {"musicID": song}, country, what="song")


def _mutable(song, country):
    try:
        return fetch.app_json("item/getMusicMutableData", {"musicID": song}, country, what="song")
    except fetch.BoomplayNotFound:
        return {}


def _credits(song, country):
    """Credited artists + EQ web id (this endpoint only takes numeric ids)."""
    try:
        if refs.is_web_id(song):
            song = shared.song_ids(song, country)[0]
        return fetch.app_json("content/music/getArtistInfo", {"musicID": song}, country,
                              what="song").get("data") or {}
    except fetch.BoomplayNotFound:
        return {}


def get_details(song, country=None):
    country = shared.country_of(country)
    with ThreadPoolExecutor(3) as pool:
        f_info = pool.submit(_info, song, country)
        f_mut = pool.submit(_mutable, song, country)
        f_cred = pool.submit(_credits, song, country)
        info, mutable, credits = f_info.result(), f_mut.result(), f_cred.result()
    web_id = parsers._str((credits.get("music") or {}).get("musicMid")) or \
        (song if refs.is_web_id(song) else None)
    out = parsers.parse_song({**info, **{k: v for k, v in mutable.items()
                                         if k in ("collectCount", "commentCount")}}, web_id=web_id)
    if out is None:
        raise fetch.BoomplayNotFound("song not found")
    artists = []
    for a in credits.get("artists") or []:
        if not isinstance(a, dict):
            continue
        ident = parsers._int(a.get("colID"))
        artists.append({"id": ident, "name": parsers._str(a.get("name")),
                        "link": parsers.entity_link("artist", ident),
                        "profile_user_id": parsers._int(a.get("afid"))})
    out["artists"] = artists or ([{k: out["artist"][k] for k in ("id", "name", "link")}]
                                 if out.get("artist") else [])
    out["lyrics_link"] = parsers.entity_link("lyrics", web_id) if web_id and out.get("has_lyrics") else None
    out.pop("position", None)
    out.pop("rank", None)
    out.pop("rank_change", None)
    return {"song": parsers.ordered(out, ("id", "web_id", "name", "link"),
                                    ("artist", "artists", "album", "images"))}


def get_lyrics(song, country=None):
    country = shared.country_of(country)
    meta = fetch.app_raw("item/getLyricID", {"musicID": song}, country)
    lyric_path = parsers._str((meta or {}).get("lyricID"))
    if not lyric_path:
        # getLyricID answers {} for unknown ids AND for songs without lyrics.
        info = _info(song, country)
        raise fetch.BoomplayNotFound(f"no lyrics for song {parsers._str(info.get('name')) or song}")
    text = fetch.fetch_text(parsers.media_url(lyric_path))
    if not text:
        raise fetch.BoomplayNotFound("lyrics file is missing on the Boomplay CDN")
    lyrics = parsers.parse_lrc(text)
    return {
        "song_id": parsers._int(meta.get("musicID")),
        "is_synced": lyrics["is_synced"] and parsers._int(meta.get("syncStatus")) != 0,
        "title": lyrics["title"],
        "artist": lyrics["artist"],
        "album": lyrics["album"],
        "text": lyrics["text"],
        "lines": lyrics["lines"],
    }


def get_playlists(song, country=None):
    """Playlists featuring the song (the upstream returns one fixed page)."""
    country = shared.country_of(country)
    payload = fetch.app_json("music/getPlaylistsByMusicID",
                             {"musicID": song, "pageIndex": 0, "pageSize": 20}, country, what="song")
    items = [p for p in (parsers.parse_playlist(c) for c in (payload.get("data") or {}).get("cols") or []) if p]
    return {"playlists": items}


def get_similar(song, country=None):
    """Songs similar to a song: the app's own recommendation call
    (ai/getRecommendSongs — 20 song-specific picks, stable across calls,
    each with play / favorite / share / comment counts). Replaced the
    website's "Similar Songs" shelf, which only renders ~half the time and
    only where the song is licensed for the web egress."""
    country = shared.country_of(country)
    info = _info(song, country)
    payload = fetch.app_json("ai/getRecommendSongs", {"musicID": info.get("musicID") or song}, country,
                             what="song")
    ident = parsers._int(info.get("musicID"))
    return {
        "song": {"id": ident, "name": parsers._str(info.get("name")),
                 "link": parsers.entity_link("song", song if refs.is_web_id(song) else ident)},
        "similar_songs": parsers.parse_songs(payload.get("musics")),
    }


def get_comments(song, page=1, sort="newest", country=None):
    return comments.get_comments("song", song, page, sort, country)
