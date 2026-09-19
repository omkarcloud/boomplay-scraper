"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. See README.md → "Endpoints" for the full function list.
"""
import json
import os

from boomplay.artists import get_details as get_artist_details
from boomplay.charts import get_trending_songs
from boomplay.songs import get_lyrics

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # an artist id, web id or any boomplay.com artist link — this is Burna Boy
    save("artist_1182.json", get_artist_details("1182"))

    # a song id or link — "Calm Down" by Rema ft. Selena Gomez, time-synced lyrics
    save("lyrics_99585404.json", get_lyrics("99585404"))

    # the 100 hottest songs in Nigeria right now (any Boomplay market: KE, GH, ZA, ...)
    save("trending_songs_ng.json", get_trending_songs(tag="hot", country="NG"))
