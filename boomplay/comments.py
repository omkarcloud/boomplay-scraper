"""Comments on any Boomplay entity (songs, albums, artists, playlists,
videos, podcasts, episodes, buzz posts).

  sort=newest  item/getTargetComments — paginated, `commentCount` = total
  sort=top     item/getHotComments    — the short "top comments" list (the
               upstream ignores pageIndex for it: one page only)

Both need the NUMERIC target id, so an EQ web id is resolved first.
"""
from boomplay import fetch, parsers, refs, shared

PAGE_SIZE = 20


def _numeric_target(kind, ref, country):
    if kind == "song":
        return shared.song_ids(ref, country)[0] if refs.is_web_id(ref) else int(ref)
    if kind in ("album", "playlist", "artist"):
        return shared.collection_ids(ref, country, kind)[0]
    if kind == "video" and refs.is_web_id(ref):
        video = fetch.app_json("item/getVideo", {"videoID": ref}, country, what="video").get("video") or {}
        ident = parsers._int(video.get("videoID"))
        if not ident:
            raise fetch.BoomplayNotFound("video not found")
        return ident
    return int(ref)


def get_comments(kind, ref, page=1, sort="newest", country=None):
    country = shared.country_of(country)
    target = _numeric_target(kind, ref, country)
    params = {"targetType": refs.COMMENT_TARGETS[kind], "targetID": target,
              **shared.page_params(page, PAGE_SIZE)}
    if sort == "top":
        if page > 1:
            return {"comments": [], "pagination": parsers.page_block(page, PAGE_SIZE, 0, 0)}
        payload = fetch.app_json("item/getHotComments", params, country, what=kind)
        items = parsers.parse_comments(payload.get("hotComments"))
        return {"comments": items,
                "pagination": parsers.page_block(1, PAGE_SIZE, len(items), len(items))}
    payload = fetch.app_json("item/getTargetComments", params, country, what=kind)
    items = parsers.parse_comments(payload.get("comments"))
    return {"comments": items,
            "pagination": parsers.page_block(page, PAGE_SIZE, len(items), payload.get("commentCount"))}
