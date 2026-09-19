"""Deezer payload normalizers: public api.deezer.com objects and gw-light
(web player gateway) objects -> one clean snake_case shape per entity.

Conventions: `link` for URLs, `pictures` {small, medium, big, xl} for every
image set, `*_count` for counters, `is_*` booleans, ISO dates, null for
missing. Noise dropped everywhere: `share` (utm-tagged copy of `link`),
`md5_image`, `tracklist` (api.deezer.com URL), `type`, `track_token`
(+expiry), `__TYPE__`/`__PAYLOAD__`, locale name variants, product ids.
"""
import html as _html
import re
from datetime import datetime, timezone

WEB_BASE = "https://www.deezer.com"
IMAGE_BASE = "https://cdn-images.dzcdn.net/images"
_PICTURE_SIZES = (("small", 56), ("medium", 250), ("big", 500), ("xl", 1000))

# developers.deezer.com: explicit_content_lyrics / explicit_content_cover.
EXPLICIT_STATUS = {
    0: "not_explicit", 1: "explicit", 2: "unknown", 3: "edited",
    4: "partially_explicit", 5: "partially_unknown", 6: "no_advice",
    7: "partially_no_advice",
}
RECORD_TYPES = {"compile": "compilation"}
_ROLE_NAMES = {
    "main_artist": "main_artists", "featuring": "featured_artists",
    "author": "authors", "composer": "composers", "producer": "producers",
    "coproducer": "co_producers", "additionalproducer": "additional_producers",
    "executiveproducer": "executive_producers", "remixer": "remixers",
    "mixingengineer": "mixing_engineers",
    "masteringengineer": "mastering_engineers",
    "recordingengineer": "recording_engineers",
    "recordingsecondengineer": "recording_second_engineers",
    "arranger": "arrangers", "conductor": "conductors", "lyricist": "lyricists",
    "musicpublisher": "music_publishers", "writer": "writers",
    "engineer": "engineers", "vocals": "vocals", "performer": "performers",
}
_TAG_RE = re.compile(r"<[^>]+>")


# ---- value helpers ----------------------------------------------------------

def _clean(value):
    """'' / [] / {} -> None (uniform nulls)."""
    return None if value in ("", [], {}, None) else value


def _int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _bool(value):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    return str(value).strip().lower() in ("1", "true", "yes")


def iso_date(value):
    """'2001-03-07' / '2001-03-07 12:00:00' -> 'YYYY-MM-DD'; Deezer's
    '0000-00-00' placeholder -> None."""
    if not value or not isinstance(value, str):
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value.strip())
    if not m or m.group(1) == "0000":
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def iso_datetime(value):
    """'2017-05-23 00:29:35' (Deezer emits UTC) -> '2017-05-23T00:29:35Z';
    epoch ints -> ISO UTC; placeholders -> None."""
    if value in (None, "", 0, "0000-00-00 00:00:00"):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            return None
    value = str(value).strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", value)
    if m:
        return f"{m.group(1)}T{m.group(2)}Z"
    return iso_date(value)


def strip_html(text):
    """Bio HTML -> plain text with paragraph breaks."""
    if not text:
        return None
    text = re.sub(r"</p>\s*<p>", "\n\n", str(text))
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = _TAG_RE.sub("", text)
    return _clean(_html.unescape(text).strip())


def explicit_status(value):
    code = _int(value)
    return EXPLICIT_STATUS.get(code) if code is not None else None


def entity_link(kind, entity_id):
    return f"{WEB_BASE}/{kind}/{entity_id}" if entity_id not in (None, "") else None


def pictures_from_md5(kind, md5):
    """gw-light only ships the image hash; build the CDN set the public API
    returns (kind: cover | artist | playlist | user | talk | misc)."""
    if not md5 or not kind:
        return None
    return {name: f"{IMAGE_BASE}/{kind}/{md5}/{px}x{px}-000000-80-0-0.jpg"
            for name, px in _PICTURE_SIZES}


def pictures(obj, prefix):
    """picture_small/medium/big/xl (or cover_*) -> {small, medium, big, xl}."""
    if not isinstance(obj, dict):
        return None
    out = {name: _clean(obj.get(f"{prefix}_{name}")) for name, _ in _PICTURE_SIZES}
    if not any(out.values()):
        return None
    return out


def _paged(payload, parse_item):
    """{"data", "total", "next"} -> (items, total, has_next)."""
    data = payload.get("data") if isinstance(payload, dict) else None
    items = [parse_item(x) for x in (data or []) if isinstance(x, dict)]
    total = _int(payload.get("total")) if isinstance(payload, dict) else None
    has_next = bool(payload.get("next")) if isinstance(payload, dict) else False
    return items, total, has_next


def ordered(data, first, last=()):
    """Reorder a flat dict: `first` keys (in order), the rest as-is, `last`
    keys at the end. Missing keys are skipped."""
    out = {}
    for k in first:
        if k in data:
            out[k] = data[k]
    for k, v in data.items():
        if k not in out and k not in last:
            out[k] = v
    for k in last:
        if k in data:
            out[k] = data[k]
    return out


def credits_by_role(contributors):
    """SNG_CONTRIBUTORS / ALB_CONTRIBUTORS {role: [names]} -> readable roles."""
    if not isinstance(contributors, dict):
        return None
    out = {}
    for role, names in contributors.items():
        if not isinstance(names, list) or not names:
            continue
        key = _ROLE_NAMES.get(role) or re.sub(r"[^a-z0-9]+", "_", str(role).lower())
        out[key] = [str(n) for n in names if n]
    return out or None


# ---- public API: nested references -----------------------------------------

def artist_ref(a):
    """Compact artist as embedded in tracks/albums/playlists."""
    if not isinstance(a, dict) or a.get("id") is None:
        return None
    out = {
        "id": _int(a.get("id")),
        "name": _clean(a.get("name")),
        "link": _clean(a.get("link")) or entity_link("artist", a.get("id")),
        "pictures": pictures(a, "picture"),
    }
    if "role" in a:
        out["role"] = _clean(a.get("role"))
    return out


def album_ref(a):
    """Compact album as embedded in tracks."""
    if not isinstance(a, dict) or a.get("id") is None:
        return None
    return {
        "id": _int(a.get("id")),
        "title": _clean(a.get("title")),
        "link": _clean(a.get("link")) or entity_link("album", a.get("id")),
        "upc": _clean(a.get("upc")),
        "release_date": iso_date(a.get("release_date")),
        "cover": pictures(a, "cover"),
    }


def user_ref(u):
    if not isinstance(u, dict) or u.get("id") is None:
        return None
    return {
        "id": _int(u.get("id")),
        "name": _clean(u.get("name")),
        "link": entity_link("profile", u.get("id")),
        "pictures": pictures(u, "picture"),
    }


# ---- public API: entities ---------------------------------------------------

def parse_track(t):
    """Track object/card (search, chart, album/playlist tracklists, top)."""
    if not isinstance(t, dict):
        return None
    out = {
        "id": _int(t.get("id")),
        "title": _clean(t.get("title")),
        "title_short": _clean(t.get("title_short")),
        "title_version": _clean(t.get("title_version")),
        "link": _clean(t.get("link")) or entity_link("track", t.get("id")),
        "preview_link": _clean(t.get("preview")),
        "isrc": _clean(t.get("isrc")),
        "duration_seconds": _int(t.get("duration")),
        "release_date": iso_date(t.get("release_date")),
        "track_position": _int(t.get("track_position")),
        "disk_number": _int(t.get("disk_number")),
        "bpm": _float(t.get("bpm")) or None,
        "gain_db": _float(t.get("gain")),
        "rank": _int(t.get("rank")),
        "is_readable": _bool(t.get("readable")),
        "is_explicit_lyrics": _bool(t.get("explicit_lyrics")),
        "explicit_lyrics_status": explicit_status(t.get("explicit_content_lyrics")),
        "explicit_cover_status": explicit_status(t.get("explicit_content_cover")),
        "artist": artist_ref(t.get("artist")),
        "album": album_ref(t.get("album")),
    }
    if "position" in t:                       # chart rank
        out["position"] = _int(t.get("position"))
    if "time_add" in t:                       # playlist membership
        out["added_at"] = iso_datetime(t.get("time_add"))
    if isinstance(t.get("contributors"), list):
        out["contributors"] = [artist_ref(c) for c in t["contributors"]
                               if isinstance(c, dict)]
    return out


def parse_album(a):
    """Album object/card (search, artist albums, chart, details header)."""
    if not isinstance(a, dict):
        return None
    genres = a.get("genres")
    genre_list = None
    if isinstance(genres, dict):
        genre_list = [parse_genre(g) for g in genres.get("data") or []
                      if isinstance(g, dict)]
    record_type = _clean(a.get("record_type"))
    out = {
        "id": _int(a.get("id")),
        "title": _clean(a.get("title")),
        "link": _clean(a.get("link")) or entity_link("album", a.get("id")),
        "upc": _clean(a.get("upc")),
        "cover": pictures(a, "cover"),
        "record_type": RECORD_TYPES.get(record_type, record_type),
        "release_date": iso_date(a.get("release_date")),
        "label": _clean(a.get("label")),
        "genre_id": _int(a.get("genre_id")),
        "genres": genre_list,
        "track_count": _int(a.get("nb_tracks")),
        "duration_seconds": _int(a.get("duration")),
        "fan_count": _int(a.get("fans")),
        "is_available": _bool(a.get("available")),
        "is_explicit_lyrics": _bool(a.get("explicit_lyrics")),
        "explicit_lyrics_status": explicit_status(a.get("explicit_content_lyrics")),
        "explicit_cover_status": explicit_status(a.get("explicit_content_cover")),
        "artist": artist_ref(a.get("artist")),
    }
    if "position" in a:
        out["position"] = _int(a.get("position"))
    if "time_add" in a:
        out["added_at"] = iso_datetime(a.get("time_add"))
    if isinstance(a.get("contributors"), list):
        out["contributors"] = [artist_ref(c) for c in a["contributors"]
                               if isinstance(c, dict)]
    return out


def parse_artist(a):
    """Artist object/card (search, related, chart, details header)."""
    if not isinstance(a, dict):
        return None
    out = {
        "id": _int(a.get("id")),
        "name": _clean(a.get("name")),
        "link": _clean(a.get("link")) or entity_link("artist", a.get("id")),
        "pictures": pictures(a, "picture"),
        "album_count": _int(a.get("nb_album")),
        "fan_count": _int(a.get("nb_fan")),
        "has_radio": _bool(a.get("radio")),
    }
    if "position" in a:
        out["position"] = _int(a.get("position"))
    return out


def parse_playlist(p):
    """Playlist object/card (search, chart, artist playlists, details)."""
    if not isinstance(p, dict):
        return None
    out = {
        "id": _int(p.get("id")),
        "title": _clean(p.get("title")),
        "link": _clean(p.get("link")) or entity_link("playlist", p.get("id")),
        "description": _clean(p.get("description")),
        "pictures": pictures(p, "picture"),
        "picture_type": _clean(p.get("picture_type")),
        "track_count": _int(p.get("nb_tracks")),
        "duration_seconds": _int(p.get("duration")),
        "fan_count": _int(p.get("fans")),
        "is_public": _bool(p.get("public")),
        "is_collaborative": _bool(p.get("collaborative")),
        "is_loved_tracks": _bool(p.get("is_loved_track")),
        "created_at": iso_datetime(p.get("creation_date")),
        "updated_at": iso_datetime(p.get("mod_date")),
        "creator": user_ref(p.get("creator") or p.get("user")),
    }
    if "position" in p:
        out["position"] = _int(p.get("position"))
    return out


def parse_user(u):
    if not isinstance(u, dict):
        return None
    return {
        "id": _int(u.get("id")),
        "name": _clean(u.get("name")),
        "link": _clean(u.get("link")) or entity_link("profile", u.get("id")),
        "pictures": pictures(u, "picture"),
        "country": _clean(u.get("country")),
    }


def parse_podcast(p):
    if not isinstance(p, dict):
        return None
    out = {
        "id": _int(p.get("id")),
        "title": _clean(p.get("title")),
        "link": _clean(p.get("link")) or entity_link("show", p.get("id")),
        "description": _clean(p.get("description")),
        "pictures": pictures(p, "picture"),
        "fan_count": _int(p.get("fans")),
        "is_available": _bool(p.get("available")),
    }
    if "position" in p:
        out["position"] = _int(p.get("position"))
    return out


def parse_genre(g):
    if not isinstance(g, dict):
        return None
    return {
        "id": _int(g.get("id")),
        "name": _clean(g.get("name")),
        "pictures": pictures(g, "picture"),
    }


def parse_list(payload, parse_item):
    """Public list payload -> {"results", "total_results", "has_next"}."""
    items, total, has_next = _paged(payload, parse_item)
    return {"results": [i for i in items if i], "total_results": total,
            "has_next": has_next}


# ---- gw-light: entities -----------------------------------------------------

def _gw_artist_ref(a):
    if not isinstance(a, dict) or not a.get("ART_ID"):
        return None
    return {
        "id": _int(a.get("ART_ID")),
        "name": _clean(a.get("ART_NAME")),
        "link": entity_link("artist", a.get("ART_ID")),
        "pictures": pictures_from_md5("artist", a.get("ART_PICTURE")),
    }


def gw_artist(a):
    """Artist card from gw-light (search sections, related artists)."""
    if not isinstance(a, dict):
        return None
    return {
        "id": _int(a.get("ART_ID")),
        "name": _clean(a.get("ART_NAME")),
        "link": entity_link("artist", a.get("ART_ID")),
        "pictures": pictures_from_md5("artist", a.get("ART_PICTURE")),
        "fan_count": _int(a.get("NB_FAN")),
    }


def _extra_artists(main, artists):
    """The ARTISTS list only earns a key when it adds to the main artist
    (features/collaborations); a single copy of `main` is dropped."""
    artists = [x for x in artists if x]
    if not artists:
        return None
    if len(artists) == 1 and main and artists[0].get("id") == main.get("id"):
        return None
    return artists


def _gw_subtypes(sub):
    if not isinstance(sub, dict):
        return None
    return {
        "is_studio": _bool(sub.get("isStudio")),
        "is_live": _bool(sub.get("isLive")),
        "is_compilation": _bool(sub.get("isCompilation")),
        "is_karaoke": _bool(sub.get("isKaraoke")),
    }


def gw_album(a):
    """Album card from gw-light (search, discography, highlight, related)."""
    if not isinstance(a, dict):
        return None
    explicit = a.get("EXPLICIT_ALBUM_CONTENT") or {}
    artists = [_gw_artist_ref(x) for x in a.get("ARTISTS") or []
               if isinstance(x, dict)]
    main = {"id": _int(a.get("ART_ID")), "name": _clean(a.get("ART_NAME")),
            "link": entity_link("artist", a.get("ART_ID"))} if a.get("ART_ID") else None
    if main is None and artists and artists[0]:
        main = dict(artists[0])           # highlight items carry no ART_ID
    songs = a.get("SONGS") if isinstance(a.get("SONGS"), dict) else {}
    return {
        "id": _int(a.get("ALB_ID")),
        "title": _clean(a.get("ALB_TITLE")),
        "title_version": _clean(a.get("VERSION")),
        "link": entity_link("album", a.get("ALB_ID")),
        "cover": pictures_from_md5("cover", a.get("ALB_PICTURE")),
        "release_date": iso_date(a.get("DIGITAL_RELEASE_DATE")
                                 or a.get("PHYSICAL_RELEASE_DATE")),
        "original_release_date": iso_date(a.get("ORIGINAL_RELEASE_DATE")),
        "track_count": _int(a.get("NUMBER_TRACK")) or _int(songs.get("total")),
        "copyright": _clean(a.get("COPYRIGHT")),
        "producer_line": _clean(a.get("PRODUCER_LINE")),
        "is_available": _bool(a.get("AVAILABLE")),
        "is_official": _bool(a.get("ARTISTS_ALBUMS_IS_OFFICIAL")),
        "explicit_lyrics_status": explicit_status(explicit.get("EXPLICIT_LYRICS_STATUS")),
        "explicit_cover_status": explicit_status(explicit.get("EXPLICIT_COVER_STATUS")),
        "subtypes": _gw_subtypes(a.get("SUBTYPES")),
        "artist": main,
        "artists": _extra_artists(main, artists),
    }


def gw_track(t):
    """Track card from gw-light (search, top tracks, album songs)."""
    if not isinstance(t, dict):
        return None
    explicit = t.get("EXPLICIT_TRACK_CONTENT") or {}
    rights = t.get("RIGHTS") or {}
    preview = next((m.get("HREF") for m in t.get("MEDIA") or []
                    if isinstance(m, dict) and m.get("TYPE") == "preview"), None)
    payload = t.get("__PAYLOAD__") if isinstance(t.get("__PAYLOAD__"), dict) else {}
    artists = [_gw_artist_ref(x) for x in t.get("ARTISTS") or []
               if isinstance(x, dict)]
    main = {"id": _int(t.get("ART_ID")), "name": _clean(t.get("ART_NAME")),
            "link": entity_link("artist", t.get("ART_ID")),
            "pictures": pictures_from_md5("artist", t.get("ART_PICTURE"))} \
        if t.get("ART_ID") else None
    out = {
        "id": _int(t.get("SNG_ID")),
        "title": _clean(t.get("SNG_TITLE")),
        "title_version": _clean(t.get("VERSION")),
        "link": entity_link("track", t.get("SNG_ID")),
        "preview_link": _clean(preview),
        "isrc": _clean(t.get("ISRC")),
        "duration_seconds": _int(t.get("DURATION")),
        "track_position": _int(t.get("TRACK_NUMBER")),
        "disk_number": _int(t.get("DISK_NUMBER")),
        "gain_db": _float(t.get("GAIN")),
        "rank": _int(t.get("RANK_SNG")),
        "is_explicit_lyrics": _bool(t.get("EXPLICIT_LYRICS")),
        "explicit_lyrics_status": explicit_status(explicit.get("EXPLICIT_LYRICS_STATUS")),
        "explicit_cover_status": explicit_status(explicit.get("EXPLICIT_COVER_STATUS")),
        "has_lyrics": bool(_int(t.get("LYRICS_ID"))) if "LYRICS_ID" in t else None,
        "is_free_stream_available": _bool(rights.get("STREAM_ADS_AVAILABLE")),
        "is_subscription_stream_available": _bool(rights.get("STREAM_SUB_AVAILABLE")),
        "credits": credits_by_role(t.get("SNG_CONTRIBUTORS")),
        "artist": main,
        "artists": _extra_artists(main, artists),
        "album": {"id": _int(t.get("ALB_ID")), "title": _clean(t.get("ALB_TITLE")),
                  "link": entity_link("album", t.get("ALB_ID")),
                  "cover": pictures_from_md5("cover", t.get("ALB_PICTURE"))}
                 if t.get("ALB_ID") else None,
    }
    if payload.get("COUNTRY_RANK") is not None or payload.get("GLOBAL_RANK") is not None:
        out["country_rank"] = _int(payload.get("COUNTRY_RANK"))
        out["global_rank"] = _int(payload.get("GLOBAL_RANK"))
    return out


def gw_playlist(p):
    if not isinstance(p, dict):
        return None
    linked = [_gw_artist_ref(x) for x in p.get("PLAYLIST_LINKED_ARTIST") or []
              if isinstance(x, dict)]
    return {
        "id": _int(p.get("PLAYLIST_ID")),
        "title": _clean(p.get("TITLE")),
        "link": entity_link("playlist", p.get("PLAYLIST_ID")),
        "description": _clean(p.get("DESCRIPTION")),
        "pictures": pictures_from_md5(p.get("PICTURE_TYPE") or "playlist",
                                      p.get("PLAYLIST_PICTURE")),
        "track_count": _int(p.get("NB_SONG")),
        "fan_count": _int(p.get("NB_FAN")),
        "is_public": (_int(p.get("STATUS")) == 0) if p.get("STATUS") is not None else None,
        "created_at": iso_datetime(p.get("DATE_ADD")),
        "updated_at": iso_datetime(p.get("DATE_MOD")),
        "creator": {"id": _int(p.get("PARENT_USER_ID")),
                    "name": _clean(p.get("PARENT_USERNAME")),
                    "link": entity_link("profile", p.get("PARENT_USER_ID")),
                    "pictures": pictures_from_md5("user", p.get("PARENT_USER_PICTURE"))}
                   if p.get("PARENT_USER_ID") else None,
        "linked_artists": [x for x in linked if x] or None,
    }


def gw_user(u):
    if not isinstance(u, dict):
        return None
    first, last = _clean(u.get("FIRSTNAME")), _clean(u.get("LASTNAME"))
    return {
        "id": _int(u.get("USER_ID")),
        "name": _clean(u.get("BLOG_NAME")),
        "full_name": _clean(" ".join(x for x in (first, last) if x)),
        "link": entity_link("profile", u.get("USER_ID")),
        "pictures": pictures_from_md5("user", u.get("USER_PICTURE")),
        "follower_count": _int(u.get("NB_FOLLOWERS")),
    }


def gw_podcast(s):
    if not isinstance(s, dict):
        return None
    return {
        "id": _int(s.get("SHOW_ID")),
        "title": _clean(s.get("SHOW_NAME")),
        "link": entity_link("show", s.get("SHOW_ID")),
        "description": _clean(s.get("SHOW_DESCRIPTION")),
        "pictures": pictures_from_md5("talk", s.get("SHOW_ART_MD5")),
        "language": _clean(s.get("LANGUAGE_CD")),
        "label": _clean(s.get("LABEL_NAME")),
        "genres": [{"id": _int(g.get("GENRE_ID")), "name": _clean(g.get("GENRE_NAME"))}
                   for g in s.get("GENRES") or [] if isinstance(g, dict)] or None,
        "fan_count": _int(s.get("NB_FAN")),
        "is_available": _bool(s.get("AVAILABLE")),
        "is_explicit": _bool(s.get("SHOW_IS_EXPLICIT")),
    }


def gw_episode(e):
    if not isinstance(e, dict):
        return None
    return {
        "id": _int(e.get("EPISODE_ID")),
        "title": _clean(e.get("EPISODE_TITLE")),
        "link": entity_link("episode", e.get("EPISODE_ID")),
        "description": _clean(e.get("EPISODE_DESCRIPTION")),
        "pictures": pictures_from_md5("talk", e.get("EPISODE_IMAGE_MD5")
                                      or e.get("SHOW_ART_MD5")),
        "duration_seconds": _int(e.get("DURATION")),
        "published_at": iso_datetime(e.get("EPISODE_PUBLISHED_TIMESTAMP")),
        "stream_link": _clean(e.get("EPISODE_DIRECT_STREAM_URL")),
        "is_available": _bool(e.get("AVAILABLE")),
        "podcast": {"id": _int(e.get("SHOW_ID")), "title": _clean(e.get("SHOW_NAME")),
                    "link": entity_link("show", e.get("SHOW_ID"))}
                   if e.get("SHOW_ID") else None,
    }


def gw_livestream(l):
    if not isinstance(l, dict):
        return None
    urls = ((l.get("LIVESTREAM_URLS") or {}).get("data") or {})
    streams = []
    if isinstance(urls, dict):
        for bitrate, fmts in urls.items():
            if isinstance(fmts, dict):
                for fmt, href in fmts.items():
                    streams.append({"bitrate_kbps": _int(bitrate), "format": fmt,
                                    "link": href})
    return {
        "id": _int(l.get("LIVESTREAM_ID")),
        "title": _clean(l.get("LIVESTREAM_TITLE")),
        "link": entity_link("radio", l.get("LIVESTREAM_ID")),
        "description": _clean(l.get("LIVESTREAM_DESCRIPTION")),
        "pictures": pictures_from_md5("misc", l.get("LIVESTREAM_IMAGE_MD5")),
        "streams": streams or None,
        "is_available": _bool(l.get("AVAILABLE")),
    }


GW_TYPE_PARSERS = {
    "artist": gw_artist, "album": gw_album, "song": gw_track,
    "playlist": gw_playlist, "user": gw_user, "show": gw_podcast,
    "episode": gw_episode, "livestream": gw_livestream,
}


def gw_any(item):
    """Dispatch on __TYPE__ (used for the search top result)."""
    if not isinstance(item, dict):
        return None
    kind = item.get("__TYPE__")
    parser = GW_TYPE_PARSERS.get(kind)
    parsed = parser(item) if parser else None
    if parsed is None:
        return None
    return {"type": "track" if kind == "song" else
            "podcast" if kind == "show" else kind, **parsed}


def gw_section(section, parse_item):
    """gw list section {"data", "count", "total", "next"} -> (items, total)."""
    if not isinstance(section, dict):
        return [], None
    items = [parse_item(x) for x in section.get("data") or [] if isinstance(x, dict)]
    return [i for i in items if i], _int(section.get("total"))
