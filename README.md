# CinePhile — Movie Discovery

A Netflix-inspired movie discovery app with a React frontend, Flask API, PostgreSQL catalogue, and a content-based recommendation model. The interface is deliberately clean: typography and film artwork carry the visual hierarchy; there are no decorative icons or emoji.

## Stack

- **Frontend:** React + Vite, responsive CSS, DM Sans / Manrope
- **API:** Python 3.12, Flask, SQLAlchemy
- **Database:** PostgreSQL 16 (SQLite for local tests)
- **Recommendations:** scikit-learn TF-IDF + cosine similarity
- **Catalogue/artwork:** TMDB API import utility using real movie metadata, poster paths and backdrop paths
- **Deployment:** Docker Compose

## Start the application

```bash
docker compose up --build -d
```

Open `http://localhost:8000`. The bundled seed catalogue lets the application start without a TMDB key. It is a small demo catalogue, not a 5,000-film training set. For a full real-data catalogue, follow the next section.

## Populate 5,000 real TMDB movies and fit the model

1. Create a TMDB account and obtain a **TMDB v3 API key**. Keep the key private.
2. Copy `.env.example` to `.env`, then set `TMDB_API_KEY=your_key` and a strong `SECRET_KEY`.
3. Start the app and import the catalogue:

```bash
docker compose up --build -d
docker compose exec web python -m app.sync_tmdb --target 5000
docker compose restart web
```

The importer fetches real records from TMDB Discover, including valid poster/backdrop paths, ratings, release years, genre labels and overview text. It updates records by TMDB ID, commits page-by-page, and does not fabricate missing films. After restart, the backend fits TF-IDF on the database catalogue at startup. Check `http://localhost:8000/healthz` for model readiness and movie count.

TMDB API availability, rate limits and catalogue contents can change. Some legitimate TMDB records have no poster or backdrop; the UI provides a clean fallback rather than inventing a fake image. The import utility is intentionally explicit so the app does not unexpectedly consume API quota on every boot.

## Recommendation model

`app/recommender.py` represents each movie with a weighted text document built from genres, keywords, director, cast and synopsis. `TfidfVectorizer` creates a sparse matrix, and cosine similarity ranks candidates. My List can be used to form a profile centroid and produce personalised recommendations. Ratings contribute a small tie-breaking signal. This is a **content-based recommendation model**, not a neural-network model trained to predict user ratings; it learns similarity structure from catalogue metadata.

The bundled 60-film seed data is only for smoke-testing. Do not claim a 5,000-film model has been trained until the TMDB import has completed successfully and `/healthz` reports the resulting catalogue size. The model is refit when the backend starts, so restart the web service after importing.

## API endpoints

- `GET /api/home` — featured title and discovery rows
- `GET /api/search?q=alien&limit=30` — title/genre/cast/director search
- `GET /api/movie/<id>` — film details and similar films
- `POST /api/my-list/<id>` — toggle a film in the anonymous session watchlist
- `GET /healthz` — health and model status

## Helpful commands

```bash
docker compose logs -f web
docker compose down                 # stop containers, retain DB volume
docker compose down -v              # stop and delete DB volume (destructive)
```

If port 8000 is busy, set `WEB_PORT=8080` in `.env`. Do not run `docker compose down -v` unless you intend to erase the database.

## HCI choices

- **Recognition over recall:** consistent visible navigation and labelled actions.
- **Visual hierarchy:** a single featured hero, clear row headings and restrained red accent.
- **Feedback:** visible confirmation after watchlist changes.
- **Consistency and standards:** predictable card layouts, typography and action styles.
- **Responsive design:** horizontal discovery rails, flexible grids and compact mobile navigation.
- **Accessibility:** semantic controls, accessible labels, visible focus, lazy-loaded poster images and reduced-motion support.
- **Progressive disclosure:** detailed synopsis, cast and recommendations appear on a focused film page; project explanation lives in an About dialog.

## Data and attribution

CinePhile uses the TMDB API but is not endorsed or certified by TMDB. Film metadata and artwork remain subject to TMDB's terms and applicable rights. Use a personal API key in `.env` only; never commit it. The existing Flask templates remain as a fallback for local tests, while Docker builds and serves the React app.
