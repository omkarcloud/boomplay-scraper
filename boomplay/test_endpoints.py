"""Live endpoint smoke tests: one call per /boomplay/* route against a
running service, with example values proven to return data (2026-09-19).
The listing tooling (derive_facts.py) reads each route's FIRST call from
this file's AST as its working example, so the values stay literals.

Skipped unless BOOMPLAY_BASE points at a running service:

    ONLY_SCRAPER=boomplay python run.py            # or any bottle runner
    BOOMPLAY_BASE=http://127.0.0.1:6002 python -m pytest boomplay/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("BOOMPLAY_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set BOOMPLAY_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def test_search():
    assert call("/boomplay/search/songs", query="calm down")["songs"]
    assert call("/boomplay/search/artists", query="burna boy")["artists"]
    assert call("/boomplay/search/albums", query="burna boy")["albums"]
    assert call("/boomplay/search/playlists", query="afrobeats")["playlists"]
    assert call("/boomplay/search/videos", query="burna boy")["videos"]
    assert call("/boomplay/search/podcasts", query="afrobeats")["podcasts"]
    assert call("/boomplay/search/users", query="burna")["users"]
    assert call("/boomplay/search/suggestions", query="burna")["suggestions"]
    assert call("/boomplay/search/popular-songs", country="NG")["songs"]
    assert call("/boomplay/search/popular-artists", country="NG")["artists"]
    assert call("/boomplay/search/trending-keywords", country="NG")["keywords"]


def test_songs():
    assert call("/boomplay/songs/details", song="99585404")["song"]["name"]
    assert call("/boomplay/songs/lyrics", song="99585404")["lines"]
    assert call("/boomplay/songs/playlists", song="99585404")["playlists"]
    assert call("/boomplay/songs/similar", song="99585404")["similar_songs"]
    assert call("/boomplay/songs/comments", song="99585404")["comments"]


def test_albums():
    assert call("/boomplay/albums/details", album="113581283")["tracks"]
    assert call("/boomplay/albums/recommendations", album="113581283")["recommendations"]
    assert call("/boomplay/albums/comments", album="113581283")["comments"]


def test_artists():
    assert call("/boomplay/artists/details", artist="1182")["artist"]["bio"]
    assert call("/boomplay/artists/songs", artist="1182")["songs"]
    assert call("/boomplay/artists/albums", artist="1182")["albums"]
    assert call("/boomplay/artists/videos", artist="1182")["videos"]
    assert call("/boomplay/artists/similar", artist="1182")["similar_artists"]
    assert call("/boomplay/artists/playlists", artist="1182")["playlists"]
    assert call("/boomplay/artists/comments", artist="1182")["comments"]
    assert call("/boomplay/artists/browse", gender="female", region="nigeria")["artists"]
    assert call("/boomplay/artists/browse-filters", country="NG")["genres"]
    assert call("/boomplay/artists/rankings", period="week", country="NG")["artists"]


def test_playlists():
    assert call("/boomplay/playlists/details", playlist="850210")["tracks"]
    assert call("/boomplay/playlists/recommendations", playlist="850210")["recommendations"]
    assert call("/boomplay/playlists/comments", playlist="850210")["comments"]
    assert call("/boomplay/playlists/browse", genre="53")["playlists"]
    assert call("/boomplay/playlists/genres", country="NG")["genres"]


def test_charts_home_trending():
    assert call("/boomplay/charts", country="NG")["charts"]
    assert call("/boomplay/charts/list", chart="weekly", country="NG")["items"]
    assert call("/boomplay/home", country="NG")["sections"]
    assert call("/boomplay/home/section", section="10002", country="NG")["items"]
    assert call("/boomplay/trending", country="NG")["shelves"]
    assert call("/boomplay/trending/songs", tag="hot", country="NG")["songs"]
    assert call("/boomplay/trending/tags", country="NG")["tags"]


def test_genres():
    assert call("/boomplay/genres", country="NG")["genres"]
    assert call("/boomplay/genres/details", genre="53")["artists"]


def test_videos():
    assert call("/boomplay/videos", category="music-videos")["videos"]
    assert call("/boomplay/videos/categories", country="NG")["categories"]
    assert call("/boomplay/videos/details", video="957921")["video"]["name"]
    assert call("/boomplay/videos/comments", video="957921")["comments"]


def test_podcasts():
    assert call("/boomplay/podcasts/categories", country="NG")["categories"]
    assert call("/boomplay/podcasts/home", country="NG")["sections"]
    assert call("/boomplay/podcasts/trending", country="NG")["podcasts"]
    assert call("/boomplay/podcasts/browse", category="1", sort="popular")["podcasts"]
    assert call("/boomplay/podcasts/details", podcast="5143")["podcast"]["name"]
    assert call("/boomplay/podcasts/episodes", podcast="5143")["episodes"]
    assert call("/boomplay/podcasts/comments", podcast="5143")["comments"]
    assert call("/boomplay/episodes/browse", category="1", sort="popular")["episodes"]
    assert call("/boomplay/episodes/details", episode="10316895")["episode"]["name"]
    assert call("/boomplay/episodes/comments", episode="5379845")["comments"]


def test_buzz_and_users():
    assert call("/boomplay/buzz/posts", country="NG")["posts"]
    assert call("/boomplay/buzz/posts/details", post="4392325")["post"]["id"]
    assert call("/boomplay/buzz/posts/comments", post="4392325")["comments"]
    assert call("/boomplay/users/details", user="1000005")["user"]["name"]
