"""/boomplay/videos/* — video categories, category listings, details and
comments (item/getVideoCates, item/getVideosByCate, item/getVideo)."""
from boomplay import comments, fetch, parsers, refs, shared

PAGE_SIZE = 20
_CATEGORY_SLUGS = {v: k for k, v in refs.VIDEO_CATEGORIES.items()}


def get_categories(country=None):
    payload = fetch.app_json("item/getVideoCates", {}, shared.country_of(country))
    return {"categories": [{"id": _CATEGORY_SLUGS.get(c.get("cateID"), parsers._str(c.get("cateID"))),
                            "name": parsers._str(c.get("cateName"))}
                           for c in payload.get("cates") or [] if isinstance(c, dict)]}


def get_list(category="music-videos", page=1, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("item/getVideosByCate",
                             {"cateID": refs.VIDEO_CATEGORIES[category], **shared.page_params(page, PAGE_SIZE)},
                             country)
    items = [v for v in (parsers.parse_video(x) for x in payload.get("videos") or []) if v]
    return {"category": category, "videos": items, "pagination": shared.paged(items, page, PAGE_SIZE)}


def get_details(video, country=None):
    country = shared.country_of(country)
    payload = fetch.app_json("item/getVideo", {"videoID": video}, country, what="video")
    parsed = parsers.parse_video(payload.get("video"))
    if parsed is None:
        raise fetch.BoomplayNotFound("video not found")
    return {"video": parsed}


def get_comments(video, page=1, sort="newest", country=None):
    return comments.get_comments("video", video, page, sort, country)
