"""Marshmallow request schemas for every /boomplay/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Boomplay resolvers and the per-route schemas. Every schema's load()
output is the kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair): `song` / `album` / `artist` / `playlist` / `video` accept
the numeric Boomplay id, the web id (EQ...) OR a boomplay.com link;
`podcast` / `episode` / `post` / `user` / `genre` accept the numeric id OR
a link (refs.py).
"""
from marshmallow import ValidationError, fields, validate

from schema_fields import BaseSchema, ChoiceField, CountryCodeField, PageField, QueryField, RefField
from boomplay import refs


# ---- id-or-link fields ---------------------------------------------------------

class SongRefField(RefField):
    resolver = staticmethod(refs.resolve_song)


class AlbumRefField(RefField):
    resolver = staticmethod(refs.resolve_album)


class ArtistRefField(RefField):
    resolver = staticmethod(refs.resolve_artist)


class PlaylistRefField(RefField):
    resolver = staticmethod(refs.resolve_playlist)


class VideoRefField(RefField):
    resolver = staticmethod(refs.resolve_video)


class PodcastRefField(RefField):
    resolver = staticmethod(refs.resolve_podcast)


class EpisodeRefField(RefField):
    resolver = staticmethod(refs.resolve_episode)


class PostRefField(RefField):
    resolver = staticmethod(refs.resolve_post)


class UserRefField(RefField):
    resolver = staticmethod(refs.resolve_user)


class GenreRefField(RefField):
    resolver = staticmethod(refs.resolve_genre)


class BoomplayCountryField(CountryCodeField):
    """ISO country code, default NG; must be a market the app API serves
    (the country is applied through the forwarded IP, refs.COUNTRY_IPS)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", refs.DEFAULT_COUNTRY)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is not None and value not in refs.COUNTRY_IPS:
            raise ValidationError(f"Boomplay has no {value} catalogue; use one of its markets "
                                  f"(NG, GH, KE, TZ, UG, ZA, CM, CI, SN, ZM, US, GB, IN, ...).")
        return value


class TrendingTagField(fields.Field):
    """'hot' | 'new' | a genre id from /boomplay/trending/tags."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", "hot")
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        text = str(value or "").strip().lower()
        if text in refs.TRENDING_TAGS:
            return text
        if text.isdigit() and int(text) > 0:
            return int(text)
        raise ValidationError("Must be hot, new, or a genre id from /boomplay/trending/tags.")


def _country():
    return BoomplayCountryField(metadata={"description": "ISO country code (default NG)"})


def _sort_comments():
    return ChoiceField(list(refs.COMMENT_SORTS), load_default="newest")


def _optional_genre():
    return GenreRefField(required=False, load_default=None)


class EmptySchema(BaseSchema):
    pass


class CountrySchema(BaseSchema):
    country = _country()


class QuerySchema(BaseSchema):
    query = QueryField(max_length=100)


class QueryPageSchema(QuerySchema):
    page = PageField(max_page=50)


class QueryCountrySchema(QuerySchema):
    country = _country()


class QueryPageCountrySchema(QueryPageSchema):
    country = _country()


# ---- songs -----------------------------------------------------------------------

class SongSchema(BaseSchema):
    song = SongRefField()
    country = _country()


class SongCommentsSchema(SongSchema):
    page = PageField(max_page=500)
    sort = _sort_comments()


# ---- albums / playlists ----------------------------------------------------------

class AlbumSchema(BaseSchema):
    album = AlbumRefField()
    country = _country()


class AlbumCommentsSchema(AlbumSchema):
    page = PageField(max_page=500)
    sort = _sort_comments()


class PlaylistSchema(BaseSchema):
    playlist = PlaylistRefField()
    country = _country()


class PlaylistCommentsSchema(PlaylistSchema):
    page = PageField(max_page=500)
    sort = _sort_comments()


class PlaylistBrowseSchema(BaseSchema):
    genre = _optional_genre()
    page = PageField(max_page=500)
    country = _country()


# ---- artists ---------------------------------------------------------------------

class ArtistSchema(BaseSchema):
    artist = ArtistRefField()
    country = _country()


class ArtistWebSchema(BaseSchema):
    artist = ArtistRefField()


class ArtistPageSchema(ArtistSchema):
    page = PageField(max_page=500)


class ArtistCommentsSchema(ArtistPageSchema):
    sort = _sort_comments()


class ArtistBrowseSchema(BaseSchema):
    genre = _optional_genre()
    gender = ChoiceField(list(refs.ARTIST_GENDERS), load_default="all")
    region = ChoiceField(list(refs.ARTIST_REGIONS), load_default="all")
    letter = ChoiceField([chr(c) for c in range(ord("A"), ord("Z") + 1)] + ["#"], load_default=None)
    page = PageField(max_page=500)
    country = _country()

    def load(self, *args, **kwargs):
        data = super().load(*args, **kwargs)
        if data.get("letter"):
            data["letter"] = data["letter"].upper()
        return data


class ArtistRankingsSchema(BaseSchema):
    period = ChoiceField(list(refs.RANKING_PERIODS), load_default="week")
    page = PageField(max_page=500)
    country = _country()


# ---- charts / home / trending / genres ------------------------------------------

class ChartSchema(BaseSchema):
    chart = ChoiceField(list(refs.CHART_GROUPS), load_default="weekly")
    country = _country()


class HomeSectionSchema(BaseSchema):
    section = fields.Integer(required=True, strict=False, validate=validate.Range(min=1),
                             metadata={"description": "a section id from /boomplay/home"})
    country = _country()


class TrendingSongsSchema(BaseSchema):
    tag = TrendingTagField()
    country = _country()


class GenreSchema(BaseSchema):
    genre = GenreRefField()
    page = PageField(max_page=500)
    country = _country()


# ---- videos -----------------------------------------------------------------------

class VideoListSchema(BaseSchema):
    category = ChoiceField(list(refs.VIDEO_CATEGORIES), load_default="music-videos")
    page = PageField(max_page=500)
    country = _country()


class VideoSchema(BaseSchema):
    video = VideoRefField()
    country = _country()


class VideoCommentsSchema(VideoSchema):
    page = PageField(max_page=500)
    sort = _sort_comments()


# ---- podcasts ---------------------------------------------------------------------

class PodcastBrowseSchema(BaseSchema):
    category = fields.Integer(load_default=0, strict=False, validate=validate.Range(min=0),
                              metadata={"description": "a category id from /boomplay/podcasts/categories"})
    sort = ChoiceField(["popular", "new"], load_default="popular")
    page = PageField(max_page=500)
    country = _country()


class PodcastSchema(BaseSchema):
    podcast = PodcastRefField()
    country = _country()


class PodcastEpisodesSchema(PodcastSchema):
    sort = ChoiceField(["newest", "oldest"], load_default="newest")
    page = PageField(max_page=500)


class PodcastCommentsSchema(PodcastSchema):
    page = PageField(max_page=500)
    sort = _sort_comments()


class EpisodeSchema(BaseSchema):
    episode = EpisodeRefField()
    country = _country()


class EpisodeCommentsSchema(EpisodeSchema):
    page = PageField(max_page=500)
    sort = _sort_comments()


# ---- buzz / users -----------------------------------------------------------------

class PostListSchema(BaseSchema):
    page = PageField(max_page=500)
    country = _country()


class PostSchema(BaseSchema):
    post = PostRefField()
    country = _country()


class PostCommentsSchema(PostSchema):
    page = PageField(max_page=500)
    sort = _sort_comments()


class UserSchema(BaseSchema):
    user = UserRefField()
