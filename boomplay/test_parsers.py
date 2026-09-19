"""Offline tests for the Boomplay scraper: refs, schemas, app-API parsers and
website parsers against fixtures captured 2026-09-19.

    python -m pytest boomplay/test_parsers.py -q
"""
import json
import os

import pytest

from boomplay import parsers, refs, schemas, shared, web
from schema_fields import load_query

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


# ---- refs ------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("211634092", "211634092"),
    ("EQsD775w8kQRIIrFPqf1GSIp", "EQsD775w8kQRIIrFPqf1GSIp"),
    ("https://www.boomplay.com/songs/EQsD775w8kQRIIrFPqf1GSIp?from=search", "EQsD775w8kQRIIrFPqf1GSIp"),
    ("www.boomplay.com/lyrics/EQsD775w8kQRIIrFPqf1GSIp", "EQsD775w8kQRIIrFPqf1GSIp"),
    ("https://www.boomplay.com/songs/13977", "13977"),
])
def test_resolve_song(value, expected):
    assert refs.resolve_song(value) == expected


def test_resolve_rejects_wrong_kind_and_junk():
    with pytest.raises(ValueError, match="points to a album"):
        refs.resolve_song("https://www.boomplay.com/albums/EQWIZGTMz9fFk55f7SUarC1t")
    with pytest.raises(ValueError):
        refs.resolve_song("hello world")
    with pytest.raises(ValueError, match="numeric"):
        refs.resolve_podcast("EQsD775w8kQRIIrFPqf1GSIp")
    with pytest.raises(ValueError):
        refs.resolve_artist("https://example.com/artists/1182")


def test_numeric_only_links():
    assert refs.resolve_podcast("https://www.boomplay.com/podcasts/5143") == "5143"
    assert refs.resolve_post("https://www.boomplay.com/buzz/5217370") == "5217370"
    assert refs.resolve_user("https://www.boomplay.com/users/1000005?x=1") == "1000005"
    assert refs.resolve_genre("53") == "53"


def test_country_table():
    assert refs.COUNTRY_IPS["NG"] and refs.COUNTRY_IPS["KE"] and refs.COUNTRY_IPS["US"]
    assert "OT" not in refs.COUNTRY_IPS


# ---- schemas ---------------------------------------------------------------

def test_schema_defaults_and_validation():
    data, err = load_query(schemas.SongCommentsSchema, {"song": "https://www.boomplay.com/songs/13977"})
    assert err is None and data == {"song": "13977", "country": "NG", "page": 1, "sort": "newest"}
    _, err = load_query(schemas.CountrySchema, {"country": "DE"})
    assert err and "no DE catalogue" in err["error"]
    _, err = load_query(schemas.QuerySchema, {"query": "x", "extra": "1"})
    assert err and "Unknown field" in err["error"]
    data, _ = load_query(schemas.TrendingSongsSchema, {"tag": "42"})
    assert data["tag"] == 42
    data, _ = load_query(schemas.ArtistBrowseSchema, {"letter": "b", "gender": "Female"})
    assert data["letter"] == "B" and data["gender"] == "female"
    _, err = load_query(schemas.ArtistRankingsSchema, {"period": "month"})
    assert err      # MONTHLY returns nothing upstream, so it is not offered


# ---- value helpers -----------------------------------------------------------

def test_value_helpers():
    assert parsers.duration_seconds("00:02:56") == 176
    assert parsers.duration_seconds("45:57") == 2757
    assert parsers.duration_seconds(3227) == 3227
    assert parsers.parse_count("1.3b") == 1_300_000_000
    assert parsers.parse_count("673.5k") == 673_500
    assert parsers.parse_count("2,738") == 2738
    assert parsers.ms_to_iso(1772778357000) == "2026-03-06T06:25:57Z"
    assert parsers.media_url("group10/M00/a.jpg") == "https://source.boomplaymusic.com/group10/M00/a.jpg"
    assert parsers.rank_change("+3") == 3 and parsers.rank_change("NEW") is None
    imgs = parsers.images({"lowIconID": "g/x_200_200.jpg", "iconMagicUrl": "g/x.jpg"})
    assert imgs["medium"].endswith("x_320_320.jpg") and imgs["original"].endswith("g/x.jpg")


def test_page_block():
    assert parsers.page_block(2, 20, 20) == {"page": 2, "items_per_page": 20, "total_pages": 3, "total_count": None}
    assert parsers.page_block(2, 20, 5)["total_pages"] == 2
    assert parsers.page_block(1, 20, 20, 555)["total_pages"] == 28


# ---- app parsers ---------------------------------------------------------------

def test_parse_song():
    song = parsers.parse_song(fixture("music_info.json"))
    assert song["id"] == 211634092 and song["name"] == "Love"
    assert song["duration_seconds"] == 176 and song["release_year"] == 2025
    assert song["record_label"] and song["is_explicit"] is True and song["has_lyrics"] is True
    assert song["artist"]["id"] == 1182 and song["artist"]["follower_count"]
    assert song["album"]["id"] == 113581283 and song["album"]["image"]
    assert "hdSourceID" not in json.dumps(song) and ".mp3" not in json.dumps(song)


def test_parse_album_and_tracks():
    payload = fixture("album.json")
    album = parsers.parse_album(payload["detailCol"])
    assert album["type"] == "album" and album["web_id"].startswith("EQ")
    assert album["stats"]["play_count"] > 0 and album["artist"]["name"] == "Burna Boy"
    tracks = parsers.parse_songs(payload["musics"])
    assert tracks and tracks[0]["position"] == 1


def test_parse_artist_detail():
    payload = fixture("artist.json")
    artist = parsers.parse_artist(payload["detailCol"])
    assert artist["name"] == "Burna Boy" and artist["gender"] == "male"
    assert artist["country"] == "Nigeria" and artist["bio"]
    assert artist["stats"]["follower_count"] > 0 and artist["album_count"] > 0
    assert artist["images"]["banner"].endswith("_800_432.jpg")
    assert [parsers.parse_album(a) for a in payload["albums"]][0]["id"]
    assert parsers.parse_video(payload["videos"][0])["type"]


def test_parse_playlist():
    playlist = parsers.parse_playlist(fixture("playlist.json")["detailCol"])
    assert playlist["owner"]["id"] == 1000005 and playlist["song_count"] == 100
    assert playlist["description"]


def test_parse_comments():
    items = parsers.parse_comments(fixture("comments.json")["comments"])
    assert items and items[0]["text"] and items[0]["created_at"].endswith("Z")
    assert items[0]["author"]["country_code"]


def test_parse_charts_and_trending():
    grps = fixture("charts.json")["chartGrps"]
    shelf = parsers.parse_collections(grps[0]["cols"])
    assert shelf and shelf[0]["type"] == "playlist"
    trending = {c.get("mainTitle"): c for c in fixture("trending_home.json")["data"]}
    songs = parsers.parse_songs(trending["Trending Songs"]["musics"])
    assert songs and songs[0]["artist"]["name"]
    albums = [parsers.parse_album(a) for a in trending["Trending Albums"]["albums"]]
    assert albums[0]["artist"]["name"]          # trending albums carry beArtist
    artists = [parsers.parse_artist(a) for a in trending["Trending Artists"]["artists"]]
    assert artists[0]["stats"]["play_count"] and artists[0]["stats"]["follower_count"]


def test_parse_podcast_and_episode():
    show = parsers.parse_podcast(fixture("show_detail.json")["data"])
    assert show["id"] == 5143 and show["episode_count"] and show["category"]["name"] == "Music"
    episode = parsers.parse_episode(fixture("episode_detail.json")["data"])
    assert episode["podcast"]["id"] == 5143 and episode["duration_seconds"] == 3227
    assert episode["audio_link"].startswith("https://")


def test_parse_post_and_video_and_genres():
    post = parsers.parse_post(fixture("buzz_hot.json")["buzzs"][0])
    assert post["id"] and post["author"]["id"] and post["published_at"]
    video = parsers.parse_video(fixture("video.json")["video"])
    assert video["id"] == 1011018 and video["stats"]["view_count"] >= 0
    assert ".mp4" not in json.dumps(video)
    genres = [parsers.parse_genre(g) for g in fixture("genres.json")["genres"]]
    assert genres[0]["id"] and genres[0]["images"]["icon"]


def test_parse_lrc():
    lyrics = parsers.parse_lrc(fixture("love.lrc"))
    assert lyrics["title"] == "Love" and lyrics["is_synced"]
    starts = [ln["start_ms"] for ln in lyrics["lines"]]
    assert starts == sorted(starts) and lyrics["text"]


# ---- web parsers -----------------------------------------------------------------

def test_web_artist_page():
    page = web.parse_artist_page(fixture("web_artist.html"))
    assert page["id"] == 1182 and page["web_id"] == "EQLrRCvdumHwHMf91r1e6aLl"
    assert page["rankings"]["current"] and page["rankings"]["all_time"]
    assert len(page["similar_artists"]) == 10 and page["similar_artists"][0]["web_id"].startswith("EQ")
    assert page["playlists"] and page["playlist_count"] == 200


def test_web_song_page():
    page = web.parse_song_page(fixture("web_song.html"))
    assert page["id"] == 13977 and page["play_count"] and page["genres"]
    assert page["similar_songs"] and page["similar_songs"][0]["type"] == "song"


def test_web_search():
    artists = web.parse_search_cards(fixture("web_search_artist.html"), "artist")
    assert len(artists) == 12 and artists[0]["name"] == "Burna Boy" and artists[0]["play_count"]
    podcasts = web.parse_search_podcasts(fixture("web_search_podcast.html"))
    assert podcasts["podcasts"] and podcasts["episodes"]
    ep = podcasts["episodes"][0]
    assert ep["published_date"] == "2019-08-03" and ep["podcast"]["id"] and ep["author"]["name"]


def test_web_user_page():
    user = web.parse_user_page(fixture("web_user.html"), "1000005")
    assert user["name"] == "Boomplay Charts" and user["is_verified"]
    assert user["follower_count"] and user["playlists"]


# ---- empty-page fallback --------------------------------------------------------------

def test_list_page_splits_empty_page(monkeypatch):
    calls = []

    def fake(path, params, country, what="item"):
        calls.append((params["pageIndex"], params["pageSize"]))
        if params["pageSize"] == 20:
            return {"playlists": []}                  # poisoned upstream key
        return {"playlists": [{"i": params["pageIndex"]}] * params["pageSize"]}

    monkeypatch.setattr(shared.fetch, "app_json", fake)
    items = shared.list_page("item/getPlaylists", {}, "playlists", 2, 20, "NG")
    assert len(items) == 20 and calls == [(1, 20), (2, 10), (3, 10)]
