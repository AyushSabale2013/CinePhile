# CinePhile — Movie Discovery & Recommendation System

A production-safe, Netflix-inspired movie discovery web application with a React single-page frontend, Flask API, PostgreSQL catalogue, and an explainable content-based recommendation system evaluated with a strict train/test split.

---

## 1. Architecture Overview

CinePhile separates responsibilities across three distinct tiers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        React Frontend (Vite SPA)                       │
│  Dark cinematic UI · Responsive Grids · Accessible · Zero Emojis       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / JSON
┌───────────────────────────────────▼────────────────────────────────────┐
│                         Flask API & Web Service                        │
│  - SPA Routing & Catch-All       - Session-based Watchlists (My List)  │
│  - Parameter Validation          - Dynamic Similarity Matching Curve   │
│  - Backend TMDB Client (Hidden)  - Safe Idempotent Upsert Engine       │
└───────────────────┬───────────────────────────────┬────────────────────┘
                    │                               │
         ┌──────────▼──────────┐         ┌──────────▼──────────┐
         │ PostgreSQL Database │         │ Content Recommender │
         │  - Movies Catalogue │         │  - Train/Test Split │
         │  - User Watchlists  │         │  - TF-IDF Vectorizer│
         │  - TMDB Identifiers │         │  - Cosine Alignment │
         │  - Artwork Paths    │         │  - Bayesian Blend   │
         └──────────▲──────────┘         └─────────────────────┘
                    │
         ┌──────────┴──────────────────────────────┐
         │                                         │
┌────────┴─────────────┐                ┌──────────┴───────────┐
│   TMDB 5000 CSVs     │                │     TMDB v3 API      │
│  Offline preparation │                │ Live search fallback │
│  and model training  │                │ Live artwork healing │
└──────────────────────┘                └──────────────────────┘
```

### A. TMDB 5000 Dataset (Offline Data)
- **Role:** Offline dataset for model preparation, training, and evaluation.
- **Fields:** `title`, `release_date` (year), `runtime`, `vote_average` (rating), `genres`, `keywords`, `cast` (top 5), `director`, `overview`, `popularity`, `vote_count`, `id` (`tmdb_id`), `poster_path`, `backdrop_path`.
- **Parsing:** Robust JSON parsing with error recovery handles malformed or missing fields without crashing.
- **Git & Docker Safety:** Large CSVs are kept out of Git (`.gitignore`) and excluded from Docker build contexts (`.dockerignore`).

### B. Recommendation Engine (`app/recommender.py`)
- **Pipeline:**
  1. **Stratified Split:** Deterministic 78% train / 22% test split stratified by genre (no data leakage).
  2. **Feature Engineering:** Weighted token repetition combining genres (x3), director (x3), keywords (x2), cast (x2), and normalized overview (x1).
  3. **Vectorizer:** Scikit-learn `TfidfVectorizer` (unigrams + bigrams) fitted strictly on the **training set**.
  4. **Bayesian Rating Blend:** IMDB weighted vote formula smoothly blends popularity/quality confidence into similarity rankings.
  5. **Live Evaluation:** Leave-one-out testing yields **Hit Rate @ K (Accuracy)**, **Precision @ K**, **Recall @ K**, and **NDCG @ K**.
  6. **Caching:** Computed similarity vectors are cached in-memory with a bounded LRU eviction strategy.

### C. TMDB API Integration (`app/tmdb.py`)
- **Credentials:** `TMDB_API_KEY` is loaded exclusively on the backend from environment variables. Credentials are never sent to the browser, JavaScript bundles, or logs.
- **Live Fallback:** Unseen movies and artwork are fetched on demand from TMDB v3 API and persisted idempotently.
- **Rate-Limiting & Timeouts:** Built-in connection pooling, exponential backoff retries, and strict timeouts (4-5s) prevent hanging workers.
- **Attribution:** TMDB non-endorsement attribution is preserved on the UI and API endpoints.

---

## 2. Environment Configuration

Create a `.env` file in the project root (copied from `.env.example`):

```bash
# Database Credentials
POSTGRES_DB=cinephile
POSTGRES_USER=cinephile
POSTGRES_PASSWORD=cinephile
DATABASE_URL=postgresql+psycopg2://cinephile:cinephile@db:5432/cinephile

# Security
SECRET_KEY=generate-a-secure-random-secret-key

# TMDB API (Optional for demo seed, required for full live sync & artwork enrichment)
TMDB_API_KEY=your_tmdb_v3_api_key

# Web Service Port (default: 8000)
WEB_PORT=8000
```

---

## 3. Running Locally (Docker Compose)

### Start the Service:
```bash
docker compose up --build -d
```
The web service boots on `http://localhost:8000`. On first run with an empty database, it safely loads the bundled seed dataset with high-resolution TMDB artwork.

### Check Status & Health:
```bash
curl http://localhost:8000/healthz
```
Response:
```json
{"model_ready": true, "movies": 3502, "status": "ok"}
```

---

## 4. Populating & Importing Catalogues Safely

### Option A: Import Kaggle TMDB 5000 CSVs
Place `tmdb_5000_movies.csv` and `tmdb_5000_credits.csv` inside `./data/` (or the project root):
```bash
# Auto-discovers CSV files in ./data or root:
docker compose exec web python -m app.seed --tmdb

# Or specify custom paths:
docker compose exec web python -m app.seed --tmdb data/tmdb_5000_movies.csv data/tmdb_5000_credits.csv
```
- **Idempotent:** Matches films by `tmdb_id` first, then `(title, year)`.
- **Safe:** Never deletes existing user watchlists (`my_list` table is untouched).
- **Non-destructive:** Retains existing poster URLs if CSV rows lack artwork.

### Option B: Sync Full TMDB API Catalogue
To sync 2,000 to 5,000 real films directly from TMDB Discover:
```bash
docker compose exec web python -m app.sync_tmdb --target 3500
```

---

## 5. Running the Test Suite

Run the comprehensive 14-test suite inside the Docker container:
```bash
docker compose exec -e PYTHONPATH=/srv web pytest tests/ -v
```
Tests cover:
1. Recommender similarity logic and Batman / Joker alignment.
2. HTTP page rendering (`/`, `/movie/<id>`, `/my-list`, `/search`, `/about`, `/healthz`).
3. Watchlist (My List) toggle and profile centroid personalisation.
4. Search API querying and ranking.
5. Suffix stemming rules.
6. Bayesian IMDB weighted rating calculations.
7. Live evaluation metrics API (`accuracy_at_k`, `precision_at_k`, `recall_at_k`, `ndcg_at_k`).
8. Explainability features (shared directors, genres, cast).
9. Recommender query caching.
10. Image URL construction with null, undefined, relative, and absolute paths.
11. TMDB API error handling and missing credentials.
12. Resilient JSON parsing and CSV data extraction.
13. Movie detail lookup by both primary key ID and `tmdb_id`.
14. Idempotent database upsert validation.

---

## 6. Production Deployment on Render

CinePhile is configured as a single Docker Web Service on Render connected to a Render PostgreSQL database.

### Step 1: Render Web Service Settings
- **Environment:** `Docker`
- **Build Command:** Built automatically via `Dockerfile` (multi-stage Node.js + Python build).
- **Start Command:** `./entrypoint.sh` (executes Gunicorn on `0.0.0.0:$PORT`).
- **Health Check Path:** `/healthz`

### Step 2: Render Environment Variables
Configure the following in the Render Dashboard:
- `DATABASE_URL`: Your Render PostgreSQL internal connection string (e.g. `postgresql://user:pass@host/db`).
- `SECRET_KEY`: A strong random string for session signing.
- `TMDB_API_KEY`: Your TMDB API v3 key.
- `PYTHONUNBUFFERED`: `1`

### Step 3: Startup Safety & Database Migrations
- `entrypoint.sh` executes `python -m app.seed --if-empty`.
  - If the production database already contains movies, it **skips seeding entirely** to protect live data.
  - If the database is empty, it initializes the bundled seed dataset with real TMDB artwork.
- `create_app()` automatically runs additive column migrations (e.g. `backdrop_url`, `tmdb_id`, `popularity`, `vote_count`) without dropping tables or altering existing user records.

---

## 7. HCI & UI/UX Principles Applied

- **Zero Emojis:** Replaced all informal emoji characters with bespoke SVG vectors (crisp popcorn cinema art, vector rating stars, checkmarks, and remove icons).
- **Doherty Threshold (<400ms feedback):** Fast skeleton loading states, debounced live search, and full-page boot indicators.
- **User Control & Freedom (Nielsen #3):** Interactive notification toasts provide one-click **Undo** for watchlist removals.
- **Recognition over Recall (Nielsen #6):** Genre filter chips and clear category rails minimize cognitive search effort.
- **Explainable AI (Nielsen #10):** Recommendations display specific reasons for alignment (e.g., shared directors, cast, genres) and un-clamped match percentages.
- **Component Isolation:** Dedicated padding and grid layouts on `/my-list` eliminate navigation header overlaps.

---

## 8. Data Attribution & Legal Notice

CinePhile uses the TMDB API for film metadata and artwork but is not endorsed or certified by TMDB. Film artwork and metadata remain subject to TMDB's terms of service and applicable intellectual property rights.
