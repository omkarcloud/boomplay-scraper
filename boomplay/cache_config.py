"""Cache TTL per /boomplay/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so `?country=NG` and no `country`
share a row).

Tiers follow how fast Boomplay moves each surface: charts and trending are
recomputed daily/weekly, catalogue metadata (song / album / artist facts,
lyrics) almost never changes, play / favourite counts drift slowly, and
comments / buzz move within minutes.
"""
from datetime import timedelta

# --- discovery shelves -------------------------------------------------------
CHARTS_CACHE = timedelta(hours=1)          # charts, chart lists, home, trending
RANKINGS_CACHE = timedelta(hours=1)
POPULAR_CACHE = timedelta(hours=1)         # popular songs / artists, trending keywords

# --- catalogue ---------------------------------------------------------------
DETAIL_CACHE = timedelta(hours=6)          # song / album / playlist / artist / video / podcast details
LISTING_CACHE = timedelta(hours=6)         # artist songs/albums/videos, podcast episodes, related
LYRICS_CACHE = timedelta(days=7)
WEB_CACHE = timedelta(hours=12)            # website-backed: similar, artist playlists, users
BROWSE_CACHE = timedelta(hours=6)          # artist / playlist / genre / video / podcast browse
CATALOG_CACHE = timedelta(hours=24)        # genres, categories, filters, trending tags

# --- search ------------------------------------------------------------------
SEARCH_CACHE = timedelta(hours=1)
SUGGEST_CACHE = timedelta(hours=6)

# --- social ------------------------------------------------------------------
COMMENTS_CACHE = timedelta(minutes=10)
BUZZ_CACHE = timedelta(minutes=10)
