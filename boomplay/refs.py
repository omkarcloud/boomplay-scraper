"""Boomplay reference parsing + the lookup tables the routes share.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair). Every entity ref accepts the numeric Boomplay id, the opaque
web id (`EQ...`, 24 chars) OR a pasted boomplay.com link:

  song      211634092 | EQsD775w8kQRIIrFPqf1GSIp | https://www.boomplay.com/songs/EQsD775w8kQRIIrFPqf1GSIp
                      | https://www.boomplay.com/lyrics/EQsD775w8kQRIIrFPqf1GSIp
  album     113581283 | EQWIZGTMz9fFk55f7SUarC1t | https://www.boomplay.com/albums/...
  artist    1182      | EQLrRCvdumHwHMf91r1e6aLl | https://www.boomplay.com/artists/...
  playlist  14106033  | EQEHP8Y_3jakWSaTcYRwB9wb | https://www.boomplay.com/playlists/...
  video     1011018   | EQwkHvy1racENGoh8InBHlFc | https://www.boomplay.com/video/...
  podcast   5143      | https://www.boomplay.com/podcasts/5143            (numeric only)
  episode   10316895  | https://www.boomplay.com/episode/10316895         (numeric only)
  post      5217370   | https://www.boomplay.com/buzz/5217370             (numeric only)
  user      1000005   | https://www.boomplay.com/users/1000005            (numeric only)
  genre     53        | https://www.boomplay.com/genres/53                (numeric only)

The app API decodes `EQ...` ids itself in its id params (musicID / colID /
videoID), so a resolver hands back either a digits string or the EQ id and
the endpoint passes it straight through.

Country: the app API geolocates from X-Forwarded-For (verified 2026-09-19
from Indian egress: NG/KE/GH/ZA/... each flip `cacheCountryCode`, charts and
copyright availability). COUNTRY_IPS maps every country the API recognises
to one representative IPv4 of that country (GeoLite2 block, each verified
against the live `cacheCountryCode`). Countries Boomplay does not serve
collapse to its "OT" (other) bucket and are left out.
"""
import re
from urllib.parse import unquote, urlparse

DEFAULT_COUNTRY = "NG"

COUNTRY_IPS = {
    "AD": "46.172.225.1", "AE": "2.48.1.1", "AF": "149.54.65.1", "AG": "69.50.65.1", "AL": "79.106.1.1",
    "AM": "46.130.129.1", "AO": "105.170.1.1", "AR": "181.108.1.1", "AT": "46.220.1.1", "AU": "1.148.1.1",
    "AZ": "5.197.65.1", "BA": "46.36.161.1", "BB": "196.3.193.1", "BD": "180.211.129.1", "BE": "57.4.1.1",
    "BF": "102.178.129.1", "BG": "194.141.129.1", "BH": "109.63.65.1", "BI": "154.119.1.1", "BJ": "137.255.193.1",
    "BN": "156.31.1.1", "BO": "167.157.1.1", "BR": "179.200.1.1", "BS": "24.51.65.1", "BT": "119.2.97.1",
    "BW": "129.205.193.1", "BY": "178.127.1.1", "BZ": "190.197.65.1", "CA": "167.40.1.1", "CD": "197.189.1.1",
    "CG": "160.113.129.1", "CH": "57.8.1.1", "CI": "102.136.1.1", "CK": "202.65.33.1", "CL": "152.139.1.1",
    "CM": "102.246.1.1", "CN": "59.192.1.1", "CO": "181.144.1.1", "CR": "144.23.1.1", "CU": "169.158.1.1",
    "CV": "41.215.209.1", "CY": "37.149.1.1", "CZ": "85.161.1.1", "DJ": "197.241.97.1", "DK": "94.148.1.1",
    "DO": "148.0.65.1", "DZ": "197.142.1.1", "EC": "186.3.129.1", "EE": "46.131.129.1", "EG": "156.168.1.1",
    "ES": "79.113.1.1", "ET": "197.154.1.1", "FI": "85.78.1.1", "FJ": "144.120.1.1", "FR": "163.80.1.1",
    "GA": "154.112.129.1", "GB": "25.0.1.1", "GE": "37.233.129.1", "GF": "161.22.65.1", "GH": "154.168.1.1",
    "GM": "160.182.1.1", "GN": "102.176.161.1", "GR": "79.128.1.1", "GT": "168.234.129.1", "GU": "168.123.1.1",
    "GY": "190.80.97.1", "HN": "181.210.129.1", "HR": "31.147.1.1", "HT": "148.102.129.1", "HU": "147.7.1.1",
    "ID": "39.224.1.1", "IE": "57.208.1.1", "IL": "132.75.1.1", "IN": "101.208.1.1", "IQ": "95.159.65.1",
    "IR": "5.208.1.1", "IS": "160.210.1.1", "IT": "5.84.1.1", "JM": "184.170.1.1", "JO": "176.29.1.1",
    "JP": "219.176.1.1", "KE": "105.48.1.1", "KG": "31.29.1.1", "KH": "36.37.129.1", "KM": "197.255.225.1",
    "KR": "175.224.1.1", "KW": "161.252.1.1", "KZ": "2.74.1.1", "LB": "94.187.65.1", "LI": "82.117.1.1",
    "LK": "116.12.65.1", "LR": "41.86.1.1", "LS": "156.0.1.1", "LT": "78.59.1.1", "LU": "131.166.1.1",
    "LV": "83.241.1.1", "LY": "41.255.1.1", "MA": "105.144.1.1", "MC": "88.209.65.1", "MD": "37.75.97.1",
    "ME": "78.155.33.1", "MG": "102.19.1.1", "MH": "117.103.89.1", "MK": "62.162.1.1", "ML": "154.118.129.1",
    "MM": "37.111.65.1", "MN": "49.0.129.1", "MR": "41.188.65.1", "MT": "46.54.65.1", "MU": "41.166.1.1",
    "MV": "27.114.129.1", "MW": "102.71.1.1", "MX": "148.248.1.1", "MY": "42.154.1.1", "MZ": "41.94.1.1",
    "NA": "197.188.1.1", "NC": "101.101.1.1", "NE": "41.138.33.1", "NG": "105.112.0.1", "NI": "186.76.1.1",
    "NL": "145.160.1.1", "NO": "139.108.1.1", "NP": "36.253.1.1", "NR": "203.98.241.1", "NZ": "118.90.1.1",
    "OM": "148.151.1.1", "PA": "181.38.1.1", "PE": "186.160.1.1", "PF": "148.66.65.1", "PG": "202.1.49.1",
    "PH": "121.96.1.1", "PK": "39.54.1.1", "PL": "77.254.1.1", "PS": "37.8.65.1", "PT": "139.83.1.1",
    "PY": "181.125.1.1", "QA": "37.211.1.1", "RO": "85.123.1.1", "RS": "160.99.1.1", "RU": "91.76.1.1",
    "RW": "41.197.1.1", "SA": "2.88.1.1", "SC": "24.235.25.1", "SD": "154.96.1.1", "SE": "2.0.1.1",
    "SG": "43.0.1.1", "SI": "46.122.129.1", "SK": "158.193.129.1", "SL": "102.143.65.1", "SM": "89.186.33.1",
    "SN": "102.164.129.1", "SO": "154.115.193.1", "SR": "186.179.193.1", "ST": "197.159.161.1", "SV": "190.87.1.1",
    "SY": "5.155.1.1", "SZ": "41.84.225.1", "TD": "154.68.129.1", "TG": "196.169.129.1", "TH": "1.0.129.1",
    "TJ": "85.9.161.1", "TM": "95.85.113.1", "TN": "102.240.1.1", "TR": "2.56.153.1", "TT": "190.59.1.1",
    "TW": "42.64.1.1", "TZ": "156.156.1.1", "UA": "5.207.1.1", "UG": "102.80.1.1", "US": "19.128.1.1",
    "UY": "186.8.1.1", "UZ": "83.69.129.1", "VA": "212.77.1.1", "VE": "179.20.1.1", "VN": "14.250.1.1",
    "YE": "94.26.193.1", "ZA": "197.104.1.1", "ZM": "165.60.1.1", "ZW": "41.190.33.1",
}

_DIGITS_RE = re.compile(r"^\d{1,12}$")
_WEB_ID_RE = re.compile(r"^EQ[A-Za-z0-9_-]{20,24}$")
_HOST_RE = re.compile(r"(^|\.)boomplay(music)?\.com$")

# URL path section -> entity kind (a link to the wrong kind is rejected).
_SECTIONS = {
    "songs": "song", "lyrics": "song", "albums": "album", "artists": "artist",
    "playlists": "playlist", "video": "video", "podcasts": "podcast",
    "episode": "episode", "buzz": "post", "users": "user", "genres": "genre",
}
_NUMERIC_ONLY = {"podcast", "episode", "post", "user", "genre"}


def _parse_link(text):
    url = text if "://" in text else "https://" + text.lstrip("/")
    parsed = urlparse(url)
    if not _HOST_RE.search((parsed.hostname or "").lower()):
        return None, None
    parts = [unquote(p) for p in parsed.path.split("/") if p]
    for i, part in enumerate(parts):
        kind = _SECTIONS.get(part.lower())
        if kind and i + 1 < len(parts):
            return kind, parts[i + 1].split(";")[0]
    return None, None


def _ref(value, kind):
    """A bare id / EQ id / boomplay.com link -> the id string for `kind`."""
    text = str(value if value is not None else "").strip()
    label = kind if kind != "post" else "buzz post"
    if not text:
        raise ValueError(f"{label} must not be empty")
    if _DIGITS_RE.match(text):
        if int(text) <= 0:
            raise ValueError(f"{label} id must be positive")
        return str(int(text))
    if _WEB_ID_RE.match(text):
        if kind in _NUMERIC_ONLY:
            raise ValueError(f"{label} must be a numeric Boomplay id or a boomplay.com link")
        return text
    if "boomplay" in text.lower() or text.startswith(("http://", "https://", "www.")):
        link_kind, ident = _parse_link(text)
        if link_kind is None:
            raise ValueError(f"{label} must be a Boomplay id or a boomplay.com/{_section_of(kind)}/... link")
        if link_kind != kind:
            raise ValueError(f"that link points to a {link_kind}, not a {label}")
        return _ref(ident, kind)
    raise ValueError(f"{label} must be a Boomplay id or a boomplay.com link, got {text!r}")


def _section_of(kind):
    return {"song": "songs", "album": "albums", "artist": "artists", "playlist": "playlists",
            "video": "video", "podcast": "podcasts", "episode": "episode", "post": "buzz",
            "user": "users", "genre": "genres"}[kind]


def resolve_song(value):
    return _ref(value, "song")


def resolve_album(value):
    return _ref(value, "album")


def resolve_artist(value):
    return _ref(value, "artist")


def resolve_playlist(value):
    return _ref(value, "playlist")


def resolve_video(value):
    return _ref(value, "video")


def resolve_podcast(value):
    return _ref(value, "podcast")


def resolve_episode(value):
    return _ref(value, "episode")


def resolve_post(value):
    return _ref(value, "post")


def resolve_user(value):
    return _ref(value, "user")


def resolve_genre(value):
    return _ref(value, "genre")


def is_web_id(value):
    return bool(_WEB_ID_RE.match(str(value or "")))


# ---- choice tables (read off the live app API 2026-09-19) --------------------

# /item/getCols?colGrpID=... chart shelves (the web "More" pages use the same ids).
CHART_GROUPS = {
    "weekly": 10112,
    "daily": 10141,
    "monthly": 10143,
    "top-artists": 10127,
    "top-albums": 10002,
}

# /artist/getArtistRankList `time`. The catalogue also lists MONTHLY, but the
# API answers an empty list for it in every country (2026-09-19) — left out.
RANKING_PERIODS = {"day": "DAY", "week": "WEEK", "all-time": "ALL"}

# /item/getArtists filters (item/getCatalog?type=ARTIST).
ARTIST_GENDERS = {"all": "", "male": "M", "female": "F", "group": "G"}
ARTIST_REGIONS = {
    "all": "", "nigeria": "NG", "kenya": "KE", "tanzania": "TZ", "ghana": "GH",
    "europe-north-america": "EN", "other": "OT",
}

# /item/getVideoCates.
VIDEO_CATEGORIES = {
    "music-videos": "MUSIC_VIDEO", "interviews": "INTERVIEW", "documentaries": "DOCUMENTARY",
    "talk-shows": "TALK_SHOW", "comedy": "COMEDY", "concerts": "LIVE_SHOW",
}

# /trending/getSongsTags: two pseudo tags, the rest are genre ids.
TRENDING_TAGS = {"hot": -1, "new": -2}

# Comment target types (item/getTargetComments / item/getHotComments).
COMMENT_TARGETS = {
    "song": "MUSIC", "album": "COL", "artist": "COL", "playlist": "COL",
    "video": "VIDEO", "podcast": "SHOW", "episode": "EPISODE", "post": "EXCLUSIVE",
}
COMMENT_SORTS = ("newest", "top")

# Search tabs served by the website (the app search only covers songs/users).
WEB_SEARCH_TABS = {"artists": "artist", "albums": "album", "playlists": "playlist",
                   "videos": "video", "podcasts": "podcast"}
