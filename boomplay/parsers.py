"""Boomplay app-API payload normalizers -> one clean snake_case shape per
entity. Value helpers come from deezer.parsers (DRY across music scrapers).

Conventions: identity first (id, web_id, name, link), then content, then
`stats` ({play_count, favorite_count, share_count, comment_count,
download_count, ...}), then nested refs (artist / album / owner), then
`images` ({small, medium, large, original}) last. Dates ISO (UTC), durations
in seconds, booleans as `is_*` / `has_*`, null for missing.

Dropped on purpose (noise / not public data):
  * audio + video file paths (ld/md/hdSourceID, sizes, sourceID .mp4,
    getResourceAddr) — copyrighted media, not metadata. Podcast episodes
    keep `audio_link` because those are the publisher's public RSS files.
  * `exclusion`, `permission`, `cpID` (content-provider id), `coin`,
    `subCoin`, `colPrice`, `orderStatus`, `version`, `extend`,
    `rcmdEngine*`, `_id.bytes`, `isFollowed`, `isLike`, `isRecomBlocked`,
    `localColID`, `staticAddr`, `displayStatus`, `commentNum` (uuid),
    `subType/subGrade`, `block`, `status`, `remindStatus`
  * presentation-only colours: `picColor`, `bgc`, `colPicColor`, `colBgc`
  * `bannerID`/`adImgID` duplicates of the cover in another crop are kept
    only where they differ in shape (`images.banner`).
"""
import re

from deezer.parsers import _bool, _int, iso_datetime, ordered, strip_html  # noqa: F401  (ordered: re-exported)

WEB_BASE = "https://www.boomplay.com"
STATIC_BASE = "https://source.boomplaymusic.com/"

GENDERS = {"M": "male", "F": "female", "G": "group"}
ALBUM_TYPES = {"ALBUM": "album", "SINGLE": "single", "EP": "ep", "COMPILATION": "compilation"}
VIDEO_TYPES = {"MUSIC_VIDEO": "music_video", "INTERVIEW": "interview", "DOCUMENTARY": "documentary",
               "TALK_SHOW": "talk_show", "COMEDY": "comedy", "LIVE_SHOW": "concert"}
# Collection types on the app API.
COL_TYPES = {1: "playlist", 2: "artist", 5: "album"}
_SIZE_RE = re.compile(r"_(\d+)_(\d+)(\.[A-Za-z]+)$")


# ---- value helpers ------------------------------------------------------------

def _str(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tf(value):
    """'T'/'F' flags -> bool; anything else -> None."""
    if value in ("T", "t", True):
        return True
    if value in ("F", "f", False):
        return False
    return None


def ms_to_iso(value):
    """Epoch milliseconds -> ISO UTC datetime."""
    ms = _int(value)
    if not ms or ms <= 0:
        return None
    return iso_datetime(ms / 1000)


def ms_to_date(value):
    stamp = ms_to_iso(value)
    return stamp[:10] if stamp else None


def duration_seconds(value):
    """'00:02:56' / '03:42' / 176 -> seconds."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    parts = str(value).strip().split(":")
    if not all(p.isdigit() for p in parts) or not parts:
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total or None


def year(value):
    y = _int(value)
    return y if y and 1800 < y < 2200 else None


def gender(value):
    return GENDERS.get(str(value or "").upper())


def media_url(path):
    """A CDN path ('group10/M00/..jpg') or absolute URL -> absolute URL."""
    path = _str(path)
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    return STATIC_BASE + path.lstrip("/")


def _resize(url, size):
    """Swap the _W_H suffix of a sized CDN image; unsized originals get one."""
    if not url:
        return None
    m = _SIZE_RE.search(url)
    if m:
        return url[:m.start()] + f"_{size}_{size}" + m.group(3)
    base, dot, ext = url.rpartition(".")
    return f"{base}_{size}_{size}.{ext}" if dot else None


def images(obj, original_key="iconMagicUrl", keys=("lowIconID", "smIconID", "bigIconID")):
    """{small 200, medium 320, large 464, original} from the app's icon
    fields; any one sized icon is enough to derive the rest."""
    if not isinstance(obj, dict):
        return None
    found = [media_url(obj.get(k)) for k in keys if obj.get(k)]
    for k in ("cover", "iconID", "avatar", "imgID"):
        if obj.get(k):
            found.append(media_url(obj.get(k)))
    original = media_url(obj.get(original_key))
    base = found[0] if found else original
    if not base:
        return None
    return {
        "small": _resize(base, 200),
        "medium": _resize(base, 320),
        "large": _resize(base, 464),
        "original": original or (_SIZE_RE.sub(r"\3", base) if _SIZE_RE.search(base) else base),
    }


def image(obj):
    """One mid-size (320px) image URL for nested refs."""
    imgs = images(obj)
    return (imgs or {}).get("medium") or (imgs or {}).get("original")


def entity_link(kind, ident):
    if ident in (None, ""):
        return None
    section = {"song": "songs", "album": "albums", "artist": "artists", "playlist": "playlists",
               "video": "video", "podcast": "podcasts", "episode": "episode", "post": "buzz",
               "user": "users", "genre": "genres", "lyrics": "lyrics"}[kind]
    return f"{WEB_BASE}/{section}/{ident}"


def _stats(**counts):
    """Counter block, or None when the upstream sent nothing real: several
    list payloads (trending, recommendations) carry all-zero placeholder
    counters for songs that obviously have plays."""
    out = {k: _int(v) for k, v in counts.items()}
    return out if any(v for v in out.values()) else None


def parse_count(text):
    """Web abbreviations '1.3b' / '673.5k' / '2,738' / '1m' -> int (approx)."""
    if text is None:
        return None
    t = str(text).strip().lower().replace(",", "")
    m = re.match(r"^([\d.]+)\s*([kmb]?)$", t)
    if not m:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    return int(round(num * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)]))


def rank_change(value):
    """liftNum: '+3' / '-2' / '0' / 'NEW' -> int movement (new -> None)."""
    text = _str(value)
    if text is None:
        return None
    try:
        return int(text.replace("+", ""))
    except ValueError:
        return None


# ---- small refs -----------------------------------------------------------------

def artist_ref(a):
    if not isinstance(a, dict) or not (a.get("colID") or a.get("name")):
        return None
    ident = _int(a.get("colID"))
    return {
        "id": ident,
        "name": _str(a.get("name")),
        "link": entity_link("artist", ident),
        "gender": gender(a.get("sex")),
        "follower_count": _int(a.get("followerCount")),
        "image": image(a),
    }


def album_ref(a):
    if not isinstance(a, dict) or not (a.get("colID") or a.get("name")):
        return None
    ident = _int(a.get("colID"))
    return {
        "id": ident,
        "name": _str(a.get("name")),
        "link": entity_link("album", ident),
        "is_new_release": a.get("newRelease") if isinstance(a.get("newRelease"), bool) else None,
        "image": image(a),
    }


def user_ref(u):
    """App user / owner object (afid is the public profile id)."""
    if not isinstance(u, dict) or not (u.get("afid") or u.get("name") or u.get("userName")):
        return None
    ident = _int(u.get("afid"))
    return {
        "id": ident,
        "name": _str(u.get("name")),
        "username": _str(u.get("userName")),
        "link": entity_link("user", ident),
        "bio": _str(u.get("sign")),
        "gender": gender(u.get("sex")),
        "country_code": _str(u.get("countryCode") or u.get("country")),
        "country": _str(u.get("countryName")),
        "is_vip": _tf(u.get("isVip")),
        "is_verified": True if _str(u.get("verifiedInfo")) else None,
        "follower_count": _int(u.get("followerCount")),
        "following_count": _int(u.get("followingCount")),
        "avatar": media_url(u.get("avatar") or u.get("bigAvatar")) or media_url(u.get("iconMagicUrl")),
    }


# ---- songs ------------------------------------------------------------------------

def parse_song(m, web_id=None):
    """Any app song object (getMusicInfo, collection tracks, charts,
    trending, search, top lists)."""
    if not isinstance(m, dict) or not (m.get("musicID") or m.get("name")):
        return None
    ident = _int(m.get("musicID"))
    web_id = web_id or _str(m.get("musicMid"))
    artist = artist_ref(m.get("beArtist"))
    singers = m.get("singers")
    if artist is None and isinstance(singers, list) and singers:
        artist = {"id": None, "name": _str(singers[0].get("name")), "link": None,
                  "gender": None, "follower_count": None, "image": None}
    return {
        "id": ident,
        "web_id": web_id,
        "name": _str(m.get("name")),
        "link": entity_link("song", web_id or ident),
        "position": _int(m.get("seq")) or None,
        "rank": _int(m.get("rank")) or _int(m.get("floatRank")) or None,
        "rank_change": rank_change(m.get("liftNum")),
        "duration_seconds": duration_seconds(m.get("deaution") or m.get("duration")),
        "release_year": year(m.get("publicYear")),
        "record_label": _str(m.get("recordLabel")),
        "is_explicit": _bool(m.get("explicit")) if m.get("explicit") is not None else None,
        "has_lyrics": bool(_str(m.get("lyricID"))) if "lyricID" in m else None,
        "video_id": _int(m.get("videoID")) or None,
        "stats": _stats(play_count=m.get("streamCount"), favorite_count=m.get("collectCount"),
                        share_count=m.get("shareCount"), comment_count=m.get("commentCount")),
        "artist": artist,
        "album": album_ref(m.get("beAlbum")),
        "images": images(m, keys=("lowIconID", "smIconID", "bigIconID", "cover")) or
                  images(m.get("beAlbum") or {}),
    }


def parse_songs(items):
    return [s for s in (parse_song(m) for m in (items or []) if isinstance(m, dict)) if s]


# ---- collections (album / playlist / artist) ----------------------------------------

def parse_album(c):
    if not isinstance(c, dict) or not (c.get("colID") or c.get("name")):
        return None
    ident = _int(c.get("colID"))
    web_id = _str(c.get("colMid"))
    return {
        "id": ident,
        "web_id": web_id,
        "name": _str(c.get("name")),
        "link": entity_link("album", web_id or ident),
        "type": ALBUM_TYPES.get(str(c.get("albumType") or "").upper()),
        "rank": _int(c.get("rank")) or None,
        "release_year": year(c.get("publicYear")),
        "description": _str(strip_html(c.get("descr"))) if c.get("descr") else None,
        "is_explicit": _bool(c.get("explicit")) if c.get("explicit") is not None else None,
        "song_count": _int(c.get("songCount")),
        "stats": _stats(play_count=c.get("streamCount"), favorite_count=c.get("collectCount"),
                        share_count=c.get("shareCount"), comment_count=c.get("commentCount"),
                        download_count=c.get("downloadCount")),
        "artist": artist_ref(c.get("artist") or c.get("beArtist")),
        "images": images(c),
    }


def parse_playlist(c):
    if not isinstance(c, dict) or not (c.get("colID") or c.get("name")):
        return None
    ident = _int(c.get("colID"))
    web_id = _str(c.get("colMid"))
    return {
        "id": ident,
        "web_id": web_id,
        "name": _str(c.get("name")),
        "link": entity_link("playlist", web_id or ident),
        "description": _str(strip_html(c.get("descr"))) if c.get("descr") else None,
        "song_count": _int(c.get("songCount")),
        "is_featured": _tf(c.get("isTop")),
        "updated_at": ms_to_iso(c.get("updateTime")),
        "stats": _stats(play_count=c.get("streamCount"), favorite_count=c.get("collectCount"),
                        share_count=c.get("shareCount"), comment_count=c.get("commentCount"),
                        download_count=c.get("downloadCount")),
        "owner": user_ref(c.get("owner")),
        "images": _with_banner(images(c), c),
    }


def parse_artist(c):
    """Artist collection object: detailCol (full) or a list item."""
    if not isinstance(c, dict) or not (c.get("colID") or c.get("name")):
        return None
    ident = _int(c.get("colID"))
    web_id = _str(c.get("colMid"))
    profile = c.get("userInfo") if isinstance(c.get("userInfo"), dict) else {}
    country_code = _str(c.get("countryCode") or profile.get("countryCode"))
    return {
        "id": ident,
        "web_id": web_id,
        "name": _str(c.get("name")),
        "link": entity_link("artist", web_id or ident),
        "rank": _int(c.get("rank")) or None,
        "rank_change": rank_change(c.get("liftNum")),
        "gender": gender(c.get("sex") or profile.get("sex")),
        "bio": _str(strip_html(c.get("descr"))) if c.get("descr") else None,
        "country_code": country_code if country_code not in ("OT", "EN") else None,
        "country": _str(profile.get("countryName")),
        "profile_user_id": _int(c.get("afid") or profile.get("afid")),
        "song_count": _int(c.get("songCount")),
        "album_count": _int(c.get("albumCount")),
        "video_count": _int(c.get("videoCount")),
        "playlist_count": _int(c.get("playlistCount")),
        "stats": _stats(play_count=c.get("streamCount") or c.get("playCount"),
                        follower_count=c.get("followerCount") or profile.get("followerCount"),
                        favorite_count=c.get("collectCount"), share_count=c.get("shareCount"),
                        comment_count=c.get("commentCount"), download_count=c.get("downloadCount")),
        "images": _with_banner(images(c), c),
    }


def _with_banner(imgs, c):
    banner = media_url(c.get("bannerID1") or c.get("bannerID"))
    if imgs is None and not banner:
        return None
    imgs = dict(imgs or {"small": None, "medium": None, "large": None, "original": None})
    imgs["banner"] = banner
    return imgs


def parse_collection(c):
    """Dispatch a mixed shelf item on colType (1 playlist, 2 artist, 5 album)."""
    if not isinstance(c, dict):
        return None
    kind = COL_TYPES.get(_int(c.get("colType")))
    if kind == "artist":
        out = parse_artist(c)
    elif kind == "album":
        out = parse_album(c)
    elif kind == "playlist":
        out = parse_playlist(c)
    else:
        return None
    if out is not None:
        if kind == "album":
            # parse_album's own `type` (album / single / ep) must not clobber the kind.
            out = {"type": kind, "album_type": out.pop("type", None), **out}
        else:
            out = {"type": kind, **out}
    return out


def parse_collections(items):
    return [c for c in (parse_collection(x) for x in (items or [])) if c]


# ---- videos ---------------------------------------------------------------------------

def parse_video(v):
    if not isinstance(v, dict) or not (v.get("videoID") or v.get("name")):
        return None
    ident = _int(v.get("videoID"))
    artist = artist_ref(v.get("artist"))
    if artist is None and isinstance(v.get("singers"), list) and v["singers"]:
        s = v["singers"][0]
        artist = {"id": None, "name": _str(s.get("name")), "link": None, "gender": None,
                  "follower_count": None, "image": None}
    cover = media_url(v.get("iconID"))
    return {
        "id": ident,
        "name": _str(strip_html(v.get("name"))),
        "link": entity_link("video", ident),
        "type": VIDEO_TYPES.get(str(v.get("type") or "").upper()),
        "source": _str(v.get("videoSource")),
        "description": _str(strip_html(v.get("descr"))) if v.get("descr") else None,
        "duration_seconds": duration_seconds(v.get("duration")),
        "stats": _stats(view_count=v.get("viewCount"), favorite_count=v.get("collectCount"),
                        comment_count=v.get("commentCount"), share_count=v.get("shareCount"),
                        download_count=v.get("downloadCount")),
        "artist": artist,
        "images": {"cover": cover, "banner": media_url(v.get("bannerID"))} if cover or v.get("bannerID") else None,
    }


# ---- podcasts -------------------------------------------------------------------------

def _author(a):
    if not isinstance(a, dict) or not (a.get("authorID") or a.get("name")):
        return None
    return {"id": _int(a.get("authorID")), "name": _str(a.get("name"))}


def _category(c):
    if not isinstance(c, dict) or not (c.get("cateID") or c.get("cateName")):
        return None
    return {"id": _int(c.get("cateID")), "name": _str(c.get("cateName")),
            "parent": _str(c.get("parentName"))}


def show_ref(s):
    if not isinstance(s, dict) or not (s.get("showID") or s.get("title")):
        return None
    ident = _int(s.get("showID"))
    return {"id": ident, "name": _str(s.get("title")), "link": entity_link("podcast", ident),
            "image": image(s)}


def parse_podcast(s):
    if not isinstance(s, dict) or not (s.get("showID") or s.get("title") or s.get("showTitle")):
        return None
    ident = _int(s.get("showID"))
    return {
        "id": ident,
        "name": _str(s.get("title") or s.get("showTitle")),
        "link": entity_link("podcast", ident),
        "description": _str(strip_html(s.get("description"))) if s.get("description") else None,
        "language": _str(s.get("language")),
        "copyright": _str(s.get("copyright")),
        "is_explicit": _bool(s.get("explicit")) if s.get("explicit") is not None else None,
        "is_complete": _bool(s.get("complete")) if s.get("complete") is not None else None,
        "episode_count": _int(s.get("episodeCount")),
        "last_published_at": ms_to_iso(s.get("pubDate")),
        "stats": _stats(play_count=s.get("streamCount"), favorite_count=s.get("collectCount"),
                        comment_count=s.get("commentCount"), share_count=s.get("shareCount")),
        "author": _author(s.get("beAuthor")),
        "category": _category(s.get("category")),
        "images": _with_banner(images(s), s) if s.get("bannerID") else images(s),
    }


def _audio_link(e):
    for key in ("hdStreamSourceID", "mdStreamSourceID", "ldStreamSourceID"):
        value = _str(e.get(key))
        if value and value.startswith(("http://", "https://")):
            return value
    return None


def parse_episode(e):
    if not isinstance(e, dict) or not (e.get("episodeID") or e.get("title")):
        return None
    ident = _int(e.get("episodeID"))
    notes = e.get("htmlContent") or e.get("description")
    return {
        "id": ident,
        "name": _str(e.get("title")),
        "link": entity_link("episode", ident),
        "description": _str(strip_html(notes)) if notes else None,
        "season_number": _int(e.get("seasonNo")) or None,
        "episode_number": _int(e.get("episodeNo")) or None,
        "duration_seconds": duration_seconds(e.get("duration")),
        "published_at": ms_to_iso(e.get("pubDate")),
        "is_explicit": _bool(e.get("explicit")) if e.get("explicit") is not None else None,
        "audio_link": _audio_link(e),
        "stats": _stats(play_count=e.get("streamCount"), favorite_count=e.get("collectCount"),
                        comment_count=e.get("commentCount"), share_count=e.get("shareCount")),
        "podcast": show_ref(e.get("beShow")),
        "author": _author(e.get("beAuthor")),
        "category": _category(e.get("category")),
        "images": images(e),
    }


# ---- buzz posts -------------------------------------------------------------------------

def _post_media(data):
    out = []
    for s in ((data or {}).get("sources") or []):
        if not isinstance(s, dict):
            continue
        link = media_url(s.get("originUrl") or s.get("imgUrl"))
        if not link:
            continue
        out.append({"type": (_str(s.get("sourceType")) or "").lower() or None, "link": link,
                    "width": _int(s.get("width")), "height": _int(s.get("height"))})
    return out


def _post_item(data):
    """The music item a post embeds (a song / album / playlist card)."""
    item = (data or {}).get("item")
    if not isinstance(item, dict):
        return None
    if isinstance(item.get("col"), dict):
        return parse_collection(item["col"])
    if isinstance(item.get("music"), dict):
        song = parse_song(item["music"])
        return {"type": "song", **song} if song else None
    return None


def parse_post(b):
    if not isinstance(b, dict) or not b.get("buzzID"):
        return None
    ident = _int(b.get("buzzID"))
    tag = b.get("tag") if isinstance(b.get("tag"), dict) else None
    return {
        "id": ident,
        "title": _str(b.get("title")),
        "link": entity_link("post", ident),
        "content": _str(re.sub(r"\n{3,}", "\n\n", strip_html(b.get("content")) or "")),
        "published_at": ms_to_iso(b.get("addDate")),
        "is_official": _bool(b.get("isOffice")) if b.get("isOffice") is not None else None,
        "stats": _stats(view_count=b.get("views"), favorite_count=b.get("favorites"),
                        share_count=b.get("shares"), comment_count=b.get("comments")),
        "tag": {"id": _int(tag.get("tagID")), "name": _str(tag.get("name")),
                "image": media_url(tag.get("imgID"))} if tag else None,
        "author": user_ref(b.get("owner")),
        "media": _post_media(b.get("data")),
        "linked_item": _post_item(b.get("data")),
    }


# ---- comments -----------------------------------------------------------------------------

def parse_comment(c):
    if not isinstance(c, dict) or not (c.get("id") or c.get("comment")):
        return None
    reply_to = c.get("beComment")
    images_ = [media_url(s) for s in (c.get("sources") or []) if s]
    return {
        "id": _int(c.get("id")),
        "text": _str(c.get("comment")),
        "created_at": ms_to_iso(c.get("addDate")),
        "like_count": _int(c.get("likeCount")),
        "reply_count": _int(c.get("replyCount")),
        "images": images_ or None,
        "author": user_ref(c),
        "reply_to": {"id": _int(reply_to.get("id")), "text": _str(reply_to.get("comment")),
                     "author": user_ref(reply_to)} if isinstance(reply_to, dict) else None,
    }


def parse_comments(items):
    return [c for c in (parse_comment(x) for x in (items or [])) if c]


# ---- genres ---------------------------------------------------------------------------------

def parse_genre(g):
    if not isinstance(g, dict) or g.get("categoryID") is None:
        return None
    ident = _int(g.get("categoryID"))
    icon = media_url(g.get("iconID") or g.get("bigIconID") or g.get("smIconID"))
    return {
        "id": ident,
        "name": _str(g.get("category") or g.get("name")),
        "link": entity_link("genre", ident) if ident else None,
        "description": _str(g.get("description")),
        "images": {"icon": icon, "banner": media_url(g.get("bannerID")),
                   "original": media_url(g.get("iconMagicUrl"))} if icon or g.get("bannerID") else None,
    }


# ---- lyrics -----------------------------------------------------------------------------------

_LRC_TAG_RE = re.compile(r"^\[(ti|ar|al|by|offset|length|re|ve):(.*)\]$", re.I)
_LRC_TIME_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


def parse_lrc(text):
    """LRC file -> {metadata, is_synced, lines:[{start_ms, text}], text}."""
    meta, lines = {}, []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        tag = _LRC_TAG_RE.match(raw)
        if tag:
            meta[tag.group(1).lower()] = tag.group(2).strip()
            continue
        stamps = list(_LRC_TIME_RE.finditer(raw))
        body = _LRC_TIME_RE.sub("", raw).strip()
        if not stamps:
            if body:
                lines.append({"start_ms": None, "text": body})
            continue
        for st in stamps:
            frac = st.group(3) or "0"
            ms = int(st.group(1)) * 60000 + int(st.group(2)) * 1000 + int(frac.ljust(3, "0")[:3])
            lines.append({"start_ms": ms, "text": body})
    offset = _int(meta.get("offset"))
    if offset:
        for ln in lines:
            if ln["start_ms"] is not None:
                # LRC: a positive offset makes lyrics appear sooner.
                ln["start_ms"] = max(0, ln["start_ms"] - offset)
    lines.sort(key=lambda ln: (ln["start_ms"] is None, ln["start_ms"] or 0))
    return {
        "title": _str(meta.get("ti")),
        "artist": _str(meta.get("ar")),
        "album": _str(meta.get("al")),
        "is_synced": any(ln["start_ms"] is not None for ln in lines),
        "lines": lines,
        "text": "\n".join(ln["text"] for ln in lines if ln["text"]) or None,
    }


# ---- pagination -------------------------------------------------------------------------------

def page_block(page, per_page, returned, total=None):
    """Scraper-side pagination block (route_glue.paginate lifts it). When the
    upstream gives no total, a full page implies one more page may exist."""
    total = _int(total)
    if total is not None:
        pages = max(1, -(-total // per_page)) if per_page else 1
    else:
        pages = page + 1 if returned >= per_page else page
    return {"page": page, "items_per_page": per_page, "total_pages": pages, "total_count": total}
