"""/boomplay/buzz/* — Boomplay Buzz (the app's music-news / social feed):
hot posts, one post, its comments (buzz1/getHotBuzzs, buzz1/getBuzzDetail)."""
from boomplay import comments, fetch, parsers, shared

PAGE_SIZE = 20


def get_posts(page=1, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("buzz1/getHotBuzzs", shared.page_params(page, PAGE_SIZE), country)
    items = [p for p in (parsers.parse_post(x) for x in payload.get("buzzs") or []) if p]
    return {"posts": items, "pagination": shared.paged(items, page, PAGE_SIZE)}


def get_post(post, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("buzz1/getBuzzDetail", {"buzzID": post}, country, what="buzz post")
    parsed = parsers.parse_post(payload)
    if parsed is None:
        raise fetch.BoomplayNotFound("buzz post not found")
    return {"post": parsed}


def get_comments(post, page=1, sort="newest", country=None):
    return comments.get_comments("post", post, page, sort, country)
