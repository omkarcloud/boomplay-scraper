"""/boomplay/charts, /boomplay/home, /boomplay/trending — country-localised
discovery shelves (all follow `country` via the forwarded IP).

App API:
  item/getCharts        chart shelves (weekly / daily / monthly chart
                        playlists, weekly top artists, weekly top albums)
  item/getCols          one shelf in full by its colGrpID (charts + home)
  item/getMusicHome     home page shelves (+ slides)
  trending/getHome      trending song shelves with their tag filters
  trending/getSongsTags + trending/getTrendingSongs   trending by tag
"""
from boomplay import fetch, parsers, refs, shared

_GROUP_SLUGS = {v: k for k, v in refs.CHART_GROUPS.items()}


def _shelf(g):
    gid = parsers._int(g.get("colGrpID"))
    return {
        "id": gid,
        "chart": _GROUP_SLUGS.get(gid),
        "name": parsers._str(g.get("name")),
        "items": parsers.parse_collections(g.get("cols")),
    }


def get_charts(country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("item/getCharts", {}, country)
    return {"country": country, "charts": [_shelf(g) for g in payload.get("chartGrps") or []
                                           if isinstance(g, dict)]}


def _cols(group_id, country):
    payload = fetch.app_json("item/getCols", {"colGrpID": group_id}, country, what="shelf")
    return parsers.parse_collections(payload.get("cols"))


def get_chart(chart="weekly", country=None):
    country = shared.country_of(country)
    items = _cols(refs.CHART_GROUPS[chart], country)
    return {"chart": chart, "country": country, "items": items}


def get_home(country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("item/getMusicHome", {}, country)
    sections = []
    for g in payload.get("grps") or []:
        if not isinstance(g, dict):
            continue
        items = parsers.parse_collections(g.get("cols"))
        if not items:
            continue          # empty Videos / Radio placeholders on the app home
        sections.append({"id": parsers._int(g.get("colGrpID")), "name": parsers._str(g.get("name")),
                         "items": items})
    return {"country": parsers._str(payload.get("cacheCountryCode")) or country, "sections": sections}


def get_home_section(section, country=None):
    country = shared.country_of(country)
    items = _cols(section, country)
    if not items:
        raise fetch.BoomplayNotFound(f"home section {section} not found in {country}")
    return {"section_id": int(section), "country": country, "items": items}


def _tag(t):
    tag_id = parsers._int(t.get("tagId"))
    slug = {-1: "hot", -2: "new"}.get(tag_id)
    return {"id": slug or tag_id, "name": parsers._str(t.get("name")),
            "rule": parsers._str(t.get("ruleDesc"))}


# trending/getHome shelf key -> (item type, parser)
_TRENDING_KEYS = (
    ("musics", "song", parsers.parse_song),
    ("albums", "album", parsers.parse_album),
    ("playlists", "playlist", parsers.parse_playlist),
    ("artists", "artist", parsers.parse_artist),
    ("episodes", "episode", parsers.parse_episode),
    ("shows", "podcast", parsers.parse_podcast),
)


def _ranked(items):
    for i, item in enumerate(items, 1):
        if isinstance(item, dict) and item.get("rank") is None:
            item["rank"] = i
    return items


def get_trending(country=None):
    """Every trending shelf: songs (with genre tags), albums, new releases,
    just-updated playlists, playlists, artists, episodes, podcasts."""
    country = shared.country_of(country)
    payload = fetch.app_json("trending/getHome", {}, country)
    shelves = []
    for c in payload.get("data") or []:
        if not isinstance(c, dict):
            continue
        for key, kind, parse in _TRENDING_KEYS:
            if isinstance(c.get(key), list):
                items = _ranked([x for x in (parse(i) for i in c[key]) if x])
                shelves.append({
                    "name": parsers._str(c.get("mainTitle")),
                    "type": kind,
                    "tags": [_tag(t) for t in c.get("tags") or [] if isinstance(t, dict)] or None,
                    "items": items,
                })
                break
    return {"country": country, "shelves": shelves}


def get_trending_tags(country=None):
    payload = fetch.app_json("trending/getSongsTags", {}, shared.country_of(country))
    return {"tags": [_tag(t) for t in payload.get("data") or [] if isinstance(t, dict)]}


def get_trending_songs(tag="hot", country=None):
    country = shared.country_of(country)
    tag_id = refs.TRENDING_TAGS.get(str(tag), tag)
    payload = fetch.app_json("trending/getTrendingSongs", {"tagId": tag_id}, country)
    data = payload.get("data") or {}
    return {"tag": tag, "country": country, "rule": parsers._str(data.get("ruleDesc")),
            "songs": _ranked(parsers.parse_songs(data.get("data")))}
