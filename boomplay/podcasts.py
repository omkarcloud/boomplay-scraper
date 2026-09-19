"""/boomplay/podcasts/* + /boomplay/episodes/* — podcast categories, the
podcast home, browse by category, details with every episode, episode
details, trending, comments.

App API: podcast/getPodcastLabels (categories), podcast/getSearchPodcastHome,
podcast/getSearchShowMore + getSearchEpisodeMore (labelID = category;
categoryID = the home shelf: 1 popular episodes, 2 popular podcasts,
3 new episodes, 4 new podcasts — so it doubles as the sort key),
podcast/getShowDetailInfo (every season + episode in one payload),
podcast/getEpisodeDetailInfo, trending/getShows + trending/getEpisodes.
"""
from boomplay import comments, fetch, parsers, shared

PAGE_SIZE = 20
_SHOW_SHELF = {"popular": 2, "new": 4}
_EPISODE_SHELF = {"popular": 1, "new": 3}


def get_categories(country=None):
    payload = fetch.app_json("podcast/getPodcastLabels", {}, shared.country_of(country))
    return {"categories": [{"id": parsers._int(c.get("labelID")), "name": parsers._str(c.get("labelName"))}
                           for c in payload.get("data") or [] if isinstance(c, dict)]}


def get_home(country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("podcast/getSearchPodcastHome", {}, country)
    sections = []
    for s in payload.get("data") or []:
        if not isinstance(s, dict):
            continue
        sections.append({
            "name": parsers._str(s.get("categoryName")),
            "podcasts": [p for p in (parsers.parse_podcast(x) for x in s.get("shows") or []) if p],
            "episodes": [e for e in (parsers.parse_episode(x) for x in s.get("episodes") or []) if e],
        })
    return {"country": country, "sections": sections}


def browse(category=0, sort="popular", page=1, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("podcast/getSearchShowMore",
                             {"labelID": category, "categoryID": _SHOW_SHELF[sort],
                              **shared.page_params(page, PAGE_SIZE)}, country)
    items = [p for p in (parsers.parse_podcast(x) for x in payload.get("data") or []) if p]
    return {"category_id": category, "sort": sort, "podcasts": items,
            "pagination": shared.paged(items, page, PAGE_SIZE)}


def browse_episodes(category=0, sort="popular", page=1, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("podcast/getSearchEpisodeMore",
                             {"labelID": category, "categoryID": _EPISODE_SHELF[sort],
                              **shared.page_params(page, PAGE_SIZE)}, country)
    items = [e for e in (parsers.parse_episode(x) for x in payload.get("data") or []) if e]
    return {"category_id": category, "sort": sort, "episodes": items,
            "pagination": shared.paged(items, page, PAGE_SIZE)}


def _show(podcast, country):
    payload = fetch.app_json("podcast/getShowDetailInfo", {"showID": podcast}, country, what="podcast")
    data = payload.get("data")
    if not isinstance(data, dict) or not data.get("showID"):
        raise fetch.BoomplayNotFound("podcast not found")
    return data


def get_details(podcast, country=None):
    country = shared.country_of(country)
    data = _show(podcast, country)
    return {"podcast": parsers.parse_podcast(data),
            "seasons": [{"season_number": parsers._int(s.get("seasonNo")),
                         "episode_count": len(s.get("episodes") or [])}
                        for s in data.get("seasons") or [] if isinstance(s, dict)]}


def get_episodes(podcast, sort="newest", page=1, country=None):
    """Every episode of the show (all seasons), paged locally."""
    country = shared.country_of(country)
    data = _show(podcast, country)
    episodes = []
    for s in data.get("seasons") or []:
        for e in (s or {}).get("episodes") or []:
            parsed = parsers.parse_episode(e)
            if parsed:
                parsed.pop("podcast", None)       # the parent show, repeated per row
                episodes.append(parsed)
    episodes.sort(key=lambda e: e.get("published_at") or "", reverse=(sort == "newest"))
    items, pagination = shared.slice_page(episodes, page, PAGE_SIZE)
    return {"podcast_id": parsers._int(data.get("showID")), "sort": sort, "episodes": items,
            "pagination": pagination}


def get_episode(episode, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("podcast/getEpisodeDetailInfo", {"episodeID": episode}, country,
                             what="episode")
    parsed = parsers.parse_episode(payload.get("data"))
    if parsed is None:
        raise fetch.BoomplayNotFound("episode not found")
    return {"episode": parsed}


def get_trending(country=None):
    country = shared.country_of(country)
    shows = fetch.app_json("trending/getShows", {}, country).get("data") or {}
    eps = fetch.app_json("trending/getEpisodes", {"pageIndex": 0, "pageSize": 20}, country).get("data") or {}
    return {"country": country,
            "podcasts": [p for p in (parsers.parse_podcast(x) for x in shows.get("data") or []) if p],
            "episodes": [e for e in (parsers.parse_episode(x) for x in eps.get("data") or []) if e]}


def get_comments(podcast, page=1, sort="newest", country=None):
    return comments.get_comments("podcast", podcast, page, sort, country)


def get_episode_comments(episode, page=1, sort="newest", country=None):
    return comments.get_comments("episode", episode, page, sort, country)
