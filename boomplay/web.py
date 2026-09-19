"""www.boomplay.com HTML parsers — only for data the app API does not serve
anonymously: similar artists / songs, artist rankings + playlists, the web
search tabs (artists / albums / playlists / videos / podcasts) and user
profiles. Pages are server-rendered jQuery templates (no JSON state), so
parsing is regex over well-known class names, verified against live pages
2026-09-19.

A "card" is the site's universal tile: <a href="/<section>/<id>"> with an
image (style background-image / data-bgUrl / img src), a <strong> name and
an optional <span class="listen"> play count ("1.3b", "673.5k").
"""
import html as _html
import re

from boomplay.parsers import _int, _str, entity_link, parse_count

_SECTION_KIND = {"artists": "artist", "albums": "album", "playlists": "playlist",
                 "songs": "song", "video": "video", "podcasts": "podcast", "episode": "episode",
                 "users": "user"}
_CARD_RE = re.compile(r'<a\s+href="/(artists|albums|playlists|songs|video|podcasts|episode|users)/'
                      r'([A-Za-z0-9_-]+)(?:\?[^"]*)?"[^>]*>(.*?)</a>', re.S)
_IMG_RE = re.compile(r"(?:background-image:\s*url\('([^']+)'\)|data-bgUrl=\"([^\"]+)\"|"
                     r"data-src=\"(https://[^\"]+)\"|<img[^>]+src=\"(https://[^\"]+)\")", re.I)
_STRONG_RE = re.compile(r"<strong(?:\s+class=\"([^\"]*)\")?>(.*?)</strong>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def text(fragment):
    """HTML fragment -> collapsed plain text (None when empty)."""
    if fragment is None:
        return None
    plain = _html.unescape(_TAG_RE.sub(" ", fragment)).replace("\xa0", " ")
    return _str(" ".join(plain.split()))


def strip_scripts(page):
    return re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page or "", flags=re.S)


def _web_id_or_int(value):
    return int(value) if value.isdigit() else value


def _image(inner):
    m = _IMG_RE.search(inner or "")
    if not m:
        return None
    url = next((g for g in m.groups() if g), None)
    if not url or "img1x1" in url:
        return None
    return url


def parse_card(section, ident, inner):
    kind = _SECTION_KIND[section]
    strongs = _STRONG_RE.findall(inner)
    name = None
    subtitle = None
    for cls, value in strongs:
        value = text(value)
        if not value:
            continue
        if name is None or "videoName" in (cls or ""):
            if name is not None and "videoName" in (cls or ""):
                subtitle = name
            name = value
        elif subtitle is None:
            subtitle = value
    listen = re.search(r'<span class="listen">([^<]*)</span>', inner)
    duration = re.search(r'<span class="duration">([^<]*)</span>', inner)
    ident_value = _web_id_or_int(ident)
    card = {
        "type": kind,
        "id": ident_value if isinstance(ident_value, int) else None,
        "web_id": ident_value if isinstance(ident_value, str) else None,
        "name": name,
        "link": entity_link(kind, ident),
        "play_count": parse_count(listen.group(1)) if listen else None,
        "image": _image(inner),
    }
    if kind == "video":
        from boomplay.parsers import duration_seconds
        card["artist_name"] = subtitle
        card["duration_seconds"] = duration_seconds(duration.group(1).strip()) if duration else None
    return card


def cards(fragment, kinds=None):
    """Every card in an HTML fragment, de-duplicated by link, in order."""
    out, seen = [], set()
    for section, ident, inner in _CARD_RE.findall(fragment or ""):
        kind = _SECTION_KIND[section]
        if kinds and kind not in kinds:
            continue
        card = parse_card(section, ident, inner)
        if card["link"] in seen or not card["name"]:
            continue
        seen.add(card["link"])
        out.append(card)
    return out


def section_after(page, heading_re, end="</article>"):
    """The HTML after the <h2> whose text matches heading_re, up to `end`."""
    m = re.search(r"<h2[^>]*>\s*" + heading_re, page, re.I)
    if not m:
        return ""
    stop = page.find(end, m.end())
    return page[m.end(): stop if stop > 0 else None]


def tab_pane(page, pane_id):
    m = re.search(r'<div class="tab_pane[^"]*"\s+data-id="%d">' % pane_id, page)
    if not m:
        return ""
    nxt = re.search(r'<div class="tab_pane[^"]*"\s+data-id="\d+">', page[m.end():])
    return page[m.end(): m.end() + nxt.start() if nxt else None]


def _tab_counts(page):
    """'Songs(28)' / 'Albums(10)' / 'Playlists(200)' tab labels -> counts."""
    counts = {}
    for label, n in re.findall(r"<h2>\s*(Songs|Albums|Playlists|Videos)\s*<span>\((\d+)\)</span>", page):
        counts[label.lower()] = int(n)
    return counts


def _rank(page, cls):
    m = re.search(r'<div class="%s">[^#<]*#\s*([\d,]+)</div>' % cls, page)
    return _int(m.group(1).replace(",", "")) if m else None


# ---- artist page -------------------------------------------------------------

def parse_artist_page(page):
    """Web-only artist facts: rankings, country, similar artists, playlists."""
    page = strip_scripts(page)
    cid = re.search(r'id="artistsDetails"\s+data-cid="(\d+)"', page)
    mid = re.search(r'<button class="btn_share[^"]*"[^>]*data-mid="(EQ[^"]+)"', page)
    name = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    country = re.search(r'<cite class="boomIdDisplay">\s*Country/Region\s*:\s*([^<]+)</cite>', page)
    counts = _tab_counts(page)
    similar = cards(section_after(page, r"Similar Artists"), kinds={"artist"})
    playlists = cards(tab_pane(page, 2), kinds={"playlist"})
    return {
        "id": _int(cid.group(1)) if cid else None,
        "web_id": mid.group(1) if mid else None,
        "name": text(name.group(1)) if name else None,
        "country": _str(_html.unescape(country.group(1)).strip()) if country else None,
        "rankings": {"current": _rank(page, "rankingCurrent"),
                     "all_time": _rank(page, "rankingAllTime")},
        "playlist_count": counts.get("playlists"),
        "similar_artists": similar,
        "playlists": playlists,
    }


# ---- song page ---------------------------------------------------------------

def parse_song_page(page):
    """Web-only song facts: play count, genres, similar songs."""
    page = strip_scripts(page)
    cid = re.search(r'id="songsDetails"\s+data-cid="(\d+)"', page)
    mid = re.search(r'<button class="btn_share[^"]*isSong[^"]*"[^>]*data-mid="(EQ[^"]+)"', page)
    name = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    summary = page[page.find('class="summaryWrap'):page.find('class="songDetailInfo')] \
        if 'class="summaryWrap' in page else ""
    plays = re.search(r'<span class="listen">([^<]*)</span>', summary)
    share = re.search(r'class="btn_share[^"]*"[^>]*data-count="(\d+)"', page)
    genre = re.search(r"<li>\s*Genre:\s*<span>([^<]*)</span>", page)
    released = re.search(r"<li>\s*Year of Release:\s*<span>(\d{4})</span>", page)
    return {
        "id": _int(cid.group(1)) if cid else None,
        "web_id": mid.group(1) if mid else None,
        "name": text(name.group(1)) if name else None,
        "play_count": parse_count(plays.group(1)) if plays else None,
        "share_count": _int(share.group(1)) if share else None,
        "genres": [g.strip() for g in _html.unescape(genre.group(1)).split(",") if g.strip()] if genre else [],
        "release_year": _int(released.group(1)) if released else None,
        "similar_songs": cards(section_after(page, r"Similar Songs"), kinds={"song"}),
    }


# ---- search tabs -------------------------------------------------------------

def _search_body(page):
    page = strip_scripts(page)
    start = page.find('class="partTo_classification_search"')
    if start < 0:
        return ""
    end = page.find('class="bp_footer"', start)
    return page[start:end if end > 0 else None]


def parse_search_cards(page, kind):
    """artists / albums / playlists / videos tab -> cards of that kind."""
    return cards(_search_body(page), kinds={kind})


def parse_search_podcasts(page):
    """Podcasts tab -> {podcasts: show cards, episodes: episode rows}."""
    body = _search_body(page)
    shows_part = section_after(body, r"Shows")
    episodes_part = body[body.find(">Episodes</h2>"):] if ">Episodes</h2>" in body else ""
    episodes = []
    for li in re.findall(r'<li class="clearfix"[^>]*data-id="(\d+)"[^>]*>(.*?)</li>', episodes_part, re.S):
        ident, inner = li
        title = re.search(r'<h3><a href="/episode/\d+">(.*?)</a></h3>', inner, re.S)
        desc = re.search(r'<div class="description"><a[^>]*>(.*?)</a></div>', inner, re.S)
        date = re.search(r'<span class="publishDate">([^<]+)</span>', inner)
        dur = re.search(r'data-duration="(\d+)"', inner)
        data = re.search(r'data-data="([^"]+)"', inner)
        # data-data = episodeID@+#podcast@+#showID@+#cover@+#title@+#authorName@+#authorID@+#seconds...
        show_id = author = None
        if data:
            from urllib.parse import unquote
            parts = unquote(data.group(1)).split("@+#")
            if len(parts) > 6:
                show_id = _int(parts[2])
                author = {"id": _int(parts[6]), "name": _str(parts[5])} if _str(parts[5]) else None
        name = text(title.group(1)) if title else None
        if name:
            name = re.sub(r"^\d+\.\s*", "", name)
        episodes.append({
            "type": "episode",
            "id": int(ident),
            "name": name,
            "link": entity_link("episode", ident),
            "description": text(desc.group(1)) if desc else None,
            "published_date": _web_date(date.group(1)) if date else None,
            "duration_seconds": _int(dur.group(1)) if dur else None,
            "podcast": {"id": show_id, "link": entity_link("podcast", show_id)} if show_id else None,
            "author": author,
            "image": _image(inner),
        })
    return {"podcasts": cards(shows_part, kinds={"podcast"}), "episodes": episodes}


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _web_date(value):
    """'Aug 03,2019' -> '2019-08-03'."""
    m = re.match(r"^\s*([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s*(\d{4})", value or "")
    if not m or m.group(1).lower() not in _MONTHS:
        return None
    return f"{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"


def has_more(page):
    """The page renders a 'More' button while another page exists."""
    return bool(re.search(r'class="moreBtn[^"]*"[^>]*data-formSrc="/search/', page or "", re.I))


# ---- user page ---------------------------------------------------------------

def parse_user_page(page, user_id):
    page = strip_scripts(page)
    if 'id="usersDetails"' not in page:
        return None
    head = page[page.find('id="usersDetails"'):]
    name = re.search(r"<h2[^>]*>(.*?)</h2>", head, re.S)
    verified = re.search(r'<cite class="boomIdDisplay">\s*Verified:\s*([^<]+)</cite>', head)
    followers = re.search(r"<strong>([^<]+)</strong>\s*Followers", head)
    following = re.search(r"<strong>([^<]+)</strong>\s*Following", head)
    avatar = re.search(r'<section class="default default_user_icon[^"]*">.*?<img class="img" src="([^"]+)"',
                        head, re.S)
    about = {}
    for key, value in re.findall(r"<li><strong>([^<]+)</strong>\s*<div>(.*?)</div>\s*</li>",
                                 tab_pane(head, 2), re.S):
        about[key.strip().lower()] = text(value)
    country = about.get("country")
    gender_text = (about.get("gender") or "").lower()
    return {
        "id": _int(user_id),
        "name": text(name.group(1)) if name else None,
        "link": entity_link("user", user_id),
        "full_name": about.get("name"),
        "bio": about.get("bio"),
        "gender": gender_text if gender_text in ("male", "female") else None,
        "country": country if country and country.lower() != "none" else None,
        "is_verified": bool(verified),
        "verified_as": _str(_html.unescape(verified.group(1))) if verified else None,
        "follower_count": parse_count(followers.group(1)) if followers else None,
        "following_count": parse_count(following.group(1)) if following else None,
        "avatar": avatar.group(1) if avatar else None,
        "playlists": cards(tab_pane(head, 0), kinds={"playlist"}),
    }
