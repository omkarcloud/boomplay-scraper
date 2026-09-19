# 🎵 Boomplay Scraper

Boomplay Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Boomplay data for free.

## ✨ What Can I Get?

- 🎵 **Full details on 100M+ songs** — artists, album, release year, label, lyrics & play counts
- 🎤 **Every artist, album & playlist** — bios, followers, total plays, full tracklists & comments
- 📈 **Charts & trending in 179 countries** — weekly, daily & monthly charts, top artists, trending by genre
- 🎙️ **Podcasts, videos & Buzz** — episodes with audio links, music videos, posts & comments

## 🎥 Example: A Full Boomplay Artist

```json
{
  "artist": {
    "id": 1182,
    "name": "Burna Boy",
    "link": "https://www.boomplay.com/artists/EQLrRCvdumHwHMf91r1e6aLl",
    "gender": "male",
    "bio": "Damini Ebunoluwa Ogulu, professionally known as Burna Boy is a top Nigerian afro-fusion singer and songwriter,rapper, and dancer...",
    "country": "Nigeria",
    "song_count": 204,
    "album_count": 56,
    "video_count": 36,
    "stats": {
      "play_count": 1384375597,
      "follower_count": 838611,
      "favorite_count": 45930,
      "share_count": 2738,
      "comment_count": 3784
    },
    "images": { "large": "https://source.boomplaymusic.com/group10/M00/02/11/82521dd59ff14d43a62740e5ddcace2e_464_464.jpg" }
  },
  "top_songs": [
    { "id": 211634092, "name": "Love", "duration_seconds": 176, "is_explicit": true, "has_lyrics": true, "album": { "id": 113581283, "name": "No Sign Of Weakness" } }
  ],
  "albums": [
    { "id": 114584180, "name": "Love", "type": "album", "release_year": 2025, "stats": { "play_count": 617056, "favorite_count": 267 } }
  ],
  "videos": [
    { "id": 1282504, "name": "Love", "type": "music_video", "duration_seconds": 188, "stats": { "view_count": 951, "favorite_count": 33 } }
  ]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Boomplay Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/boomplay-scraper
cd boomplay-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/artists/details?artist=1182"
```

```json
{
  "artist": {
    "id": 1182,
    "web_id": "EQLrRCvdumHwHMf91r1e6aLl",
    "name": "Burna Boy",
    "link": "https://www.boomplay.com/artists/EQLrRCvdumHwHMf91r1e6aLl",
    "gender": "male",
    "country_code": "NG",
    "country": "Nigeria",
    "song_count": 204,
    "album_count": 56,
    "video_count": 36,
    "playlist_count": 200,
    "stats": {
      "play_count": 1384375597,
      "follower_count": 838611,
      "favorite_count": 45930
    }
  }
}
```

All 61 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

61 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Artist Details | `/artists/details` | Bio, followers, total plays, top songs, albums & videos |
| Search Suggestions | `/search/suggestions` | Typeahead for artists, songs, albums & playlists |
| Search Songs / Artists / Albums | `/search/songs`, `/search/artists`, `/search/albums` | Matching results with plays, artwork & links |
| Search Playlists / Videos / Podcasts / Users | `/search/playlists`, `/search/videos`, `/search/podcasts`, `/search/users` | Playlists, music videos, shows, episodes & profiles |
| Song Details | `/songs/details` | Artists, album, year, label, duration & favorites |
| Song Lyrics | `/songs/lyrics` | Full lyrics plus time-synced lines |
| Similar Songs | `/songs/similar` | 20 similar songs with play counts |
| Song Playlists | `/songs/playlists` | Playlists featuring the song |
| Artist Songs / Albums / Videos | `/artists/songs`, `/artists/albums`, `/artists/videos` | An artist's full catalogue, 20 per page |
| Similar Artists | `/artists/similar` | Similar artists plus current and all-time rank |
| Artist Playlists | `/artists/playlists` | Playlists featuring the artist |
| Album Details | `/albums/details` | Full tracklist, year, type, plays & favorites |
| Playlist Details | `/playlists/details` | Every track, owner, description & plays |
| Album / Playlist Recommendations | `/albums/recommendations`, `/playlists/recommendations` | What Boomplay recommends alongside it |
| Comments | `/songs/comments`, `/albums/comments`, `/artists/comments`, `/playlists/comments`, `/videos/comments`, `/podcasts/comments`, `/episodes/comments`, `/buzz/posts/comments` | Newest or top comments with likes & country |
| Charts | `/charts`, `/charts/list` | Weekly, daily & monthly charts, top artists & albums |
| Trending | `/trending`, `/trending/songs`, `/trending/tags` | Every trending shelf, songs by genre tag |
| Home | `/home`, `/home/section` | The Boomplay home page for any country |
| Popular on Search | `/search/popular-songs`, `/search/popular-artists`, `/search/trending-keywords` | What a country is searching right now |
| Artist Rankings | `/artists/rankings` | Top artists by day, week or all time |
| Browse Artists | `/artists/browse`, `/artists/browse-filters` | Artists by genre, gender, region & letter |
| Browse Playlists | `/playlists/browse`, `/playlists/genres` | Playlists by genre |
| Genres | `/genres`, `/genres/details` | Every genre with its top artists, albums & playlists |
| Videos | `/videos`, `/videos/categories`, `/videos/details` | Music videos, interviews & concerts with view counts |
| Podcasts | `/podcasts/details`, `/podcasts/episodes`, `/podcasts/browse`, `/podcasts/home`, `/podcasts/trending`, `/podcasts/categories` | Shows, every episode, categories & what's trending |
| Episodes | `/episodes/details`, `/episodes/browse` | Show notes, duration, plays & audio link |
| Buzz Posts | `/buzz/posts`, `/buzz/posts/details` | Boomplay's music feed: posts, media, views & likes |
| User Details | `/users/details` | Public profile, followers & public playlists |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-boomplay-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-boomplay-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-boomplay-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/artists/details",
    params={"artist": "1182"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Boomplay Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Boomplay%20Scraper%20API.)

[![Ask Us by Email about Boomplay Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Boomplay%20Scraper%20API&body=I%20need%20help%20using%20the%20Boomplay%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**Deezer Scraper**](https://github.com/omkarcloud/deezer-scraper) — unlimited Deezer tracks, albums, artists, playlists & charts
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/boomplay-scraper)

Star the repo ⭐ and become a star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/boomplay-scraper)
