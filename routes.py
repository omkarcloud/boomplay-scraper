"""The 61 Boomplay endpoints. Every path is served with and without the
`/boomplay` prefix, so code generated against the hosted API (paths like
/artists/details) runs unchanged against this server.

Params are validated by the same marshmallow schemas the hosted API uses
(boomplay/schemas.py), so defaults, enums and error messages are identical:
unknown params are rejected, and ONE param per input accepts a Boomplay id,
a web id (EQ...) or a pasted boomplay.com link. List endpoints page with
`page` and return count / per_page / current_page / total_pages / next /
previous first, exactly like the hosted API.
"""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from boomplay import (albums, artists, buzz, charts, genres, playlists, podcasts, schemas,
                      search, songs, users, videos)

PREFIX = "/boomplay"


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so a UTF-8 "Beyoncé" would arrive as "BeyoncÃ©")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    return f"{request.urlparts.scheme}://{request.urlparts.netloc}{request.path}?{urlencode(query)}"


def paginate(result, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next /
    previous first, then the data."""
    pagination = result.pop("pagination", None) or {}
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if page < total_pages else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(path, schema, impl, paginated=False):
    """Validate the query with the endpoint's schema, run it, and map every
    failure the way the hosted API does: bad params -> 400, missing entity
    -> 404, upstream failure or block -> 502, anything else -> 500."""
    params = query_dict()
    data, error = load_query(schema, params)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"boomplay rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"boomplay blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"boomplay {path} failed: {e}"}, 502)
    except Exception as e:
        return json_response({"error": f"boomplay {path} failed: {type(e).__name__}: {e}"}, 500)
    return json_response(paginate(result, params) if paginated else result)


P = True   # paginated (page)

# (public path, request schema, endpoint function, paginated) — the order of the docs.
ENDPOINTS = [
    ("/artists/details", schemas.ArtistSchema, artists.get_details, False),
    ("/search/suggestions", schemas.QueryCountrySchema, search.suggestions, False),
    ("/search/songs", schemas.QueryPageCountrySchema, search.search_songs, P),
    ("/search/artists", schemas.QueryPageSchema, search.search_artists, P),
    ("/search/albums", schemas.QueryPageSchema, search.search_albums, P),
    ("/search/playlists", schemas.QueryPageSchema, search.search_playlists, P),
    ("/search/videos", schemas.QueryPageSchema, search.search_videos, P),
    ("/search/podcasts", schemas.QueryPageSchema, search.search_podcasts, P),
    ("/search/users", schemas.QueryPageCountrySchema, search.search_users, P),
    ("/songs/details", schemas.SongSchema, songs.get_details, False),
    ("/songs/lyrics", schemas.SongSchema, songs.get_lyrics, False),
    ("/songs/similar", schemas.SongSchema, songs.get_similar, False),
    ("/songs/playlists", schemas.SongSchema, songs.get_playlists, False),
    ("/songs/comments", schemas.SongCommentsSchema, songs.get_comments, P),
    ("/artists/songs", schemas.ArtistPageSchema, artists.get_songs, P),
    ("/artists/albums", schemas.ArtistPageSchema, artists.get_albums, P),
    ("/artists/videos", schemas.ArtistPageSchema, artists.get_videos, P),
    ("/artists/similar", schemas.ArtistWebSchema, artists.get_similar, False),
    ("/artists/playlists", schemas.ArtistWebSchema, artists.get_playlists, False),
    ("/artists/comments", schemas.ArtistCommentsSchema, artists.get_comments, P),
    ("/albums/details", schemas.AlbumSchema, albums.get_details, False),
    ("/albums/recommendations", schemas.AlbumSchema, albums.get_recommendations, False),
    ("/albums/comments", schemas.AlbumCommentsSchema, albums.get_comments, P),
    ("/playlists/details", schemas.PlaylistSchema, playlists.get_details, False),
    ("/playlists/recommendations", schemas.PlaylistSchema, playlists.get_recommendations, False),
    ("/playlists/comments", schemas.PlaylistCommentsSchema, playlists.get_comments, P),
    ("/charts", schemas.CountrySchema, charts.get_charts, False),
    ("/charts/list", schemas.ChartSchema, charts.get_chart, False),
    ("/trending", schemas.CountrySchema, charts.get_trending, False),
    ("/trending/songs", schemas.TrendingSongsSchema, charts.get_trending_songs, False),
    ("/trending/tags", schemas.CountrySchema, charts.get_trending_tags, False),
    ("/home", schemas.CountrySchema, charts.get_home, False),
    ("/home/section", schemas.HomeSectionSchema, charts.get_home_section, False),
    ("/search/popular-songs", schemas.CountrySchema, search.popular_songs, False),
    ("/search/popular-artists", schemas.CountrySchema, search.popular_artists, False),
    ("/search/trending-keywords", schemas.CountrySchema, search.trending_keywords, False),
    ("/artists/rankings", schemas.ArtistRankingsSchema, artists.get_rankings, P),
    ("/artists/browse", schemas.ArtistBrowseSchema, artists.browse, P),
    ("/artists/browse-filters", schemas.CountrySchema, artists.get_filters, False),
    ("/playlists/browse", schemas.PlaylistBrowseSchema, playlists.browse, P),
    ("/playlists/genres", schemas.CountrySchema, playlists.get_genres, False),
    ("/genres", schemas.CountrySchema, genres.get_list, False),
    ("/genres/details", schemas.GenreSchema, genres.get_details, P),
    ("/videos/details", schemas.VideoSchema, videos.get_details, False),
    ("/videos", schemas.VideoListSchema, videos.get_list, P),
    ("/videos/categories", schemas.CountrySchema, videos.get_categories, False),
    ("/videos/comments", schemas.VideoCommentsSchema, videos.get_comments, P),
    ("/podcasts/details", schemas.PodcastSchema, podcasts.get_details, False),
    ("/podcasts/episodes", schemas.PodcastEpisodesSchema, podcasts.get_episodes, P),
    ("/podcasts/comments", schemas.PodcastCommentsSchema, podcasts.get_comments, P),
    ("/podcasts/browse", schemas.PodcastBrowseSchema, podcasts.browse, P),
    ("/podcasts/home", schemas.CountrySchema, podcasts.get_home, False),
    ("/podcasts/trending", schemas.CountrySchema, podcasts.get_trending, False),
    ("/podcasts/categories", schemas.CountrySchema, podcasts.get_categories, False),
    ("/episodes/details", schemas.EpisodeSchema, podcasts.get_episode, False),
    ("/episodes/comments", schemas.EpisodeCommentsSchema, podcasts.get_episode_comments, P),
    ("/episodes/browse", schemas.PodcastBrowseSchema, podcasts.browse_episodes, P),
    ("/buzz/posts", schemas.PostListSchema, buzz.get_posts, P),
    ("/buzz/posts/details", schemas.PostSchema, buzz.get_post, False),
    ("/buzz/posts/comments", schemas.PostCommentsSchema, buzz.get_comments, P),
    ("/users/details", schemas.UserSchema, users.get_details, False),
]


def mount(path, schema, impl, paginated):
    """Serve one endpoint at /path and /boomplay/path."""
    def handler():
        return call(path, schema, impl, paginated)
    handler.__name__ = "boomplay_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route(PREFIX + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
@route(PREFIX + "/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, _, _, _ in ENDPOINTS]})
