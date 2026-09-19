"""/boomplay/users/details — a public user profile (website /users/<id>,
open without the Cloudflare identity): name, verification, followers,
about block and public playlists."""
from boomplay import fetch, web


def get_details(user):
    parsed = web.parse_user_page(fetch.web_get(f"/users/{user}"), user)
    if parsed is None or not parsed.get("name"):
        raise fetch.BoomplayNotFound("user not found")
    playlists = parsed.pop("playlists")
    return {"user": parsed, "playlists": playlists}
