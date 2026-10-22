"""Import a real TMDB catalogue using the TMDB v3 API.

Usage:
    python -m app.sync_tmdb --target 500
    python -m app.sync_tmdb --target 1000 --no-details
"""
import argparse
import os
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from . import create_app
from .extensions import db
from .models import Movie
from .recommender import recommender

BASE = "https://api.themoviedb.org/3"
IMAGE = "https://image.tmdb.org/t/p/"


def create_session(api_key: str) -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.params.update({"api_key": api_key})
    session.headers.update({"Accept": "application/json"})
    return session


def fetch_movie_details(session: requests.Session, tmdb_id: int) -> dict:
    """Fetch credits, keywords and runtime via append_to_response."""
    try:
        resp = session.get(
            f"{BASE}/movie/{tmdb_id}",
            params={"append_to_response": "credits,keywords", "language": "en-US"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def run(target: int = 500, with_details: bool = True, min_votes: int = 10):
    key = os.getenv("TMDB_API_KEY", "").strip()
    if not key:
        sys.exit("TMDB_API_KEY is required. Set it in .env or your environment.")

    session = create_session(key)

    # Fetch official genre mapping
    try:
        genre_resp = session.get(f"{BASE}/genre/movie/list", params={"language": "en-US"}, timeout=15)
        genre_resp.raise_for_status()
        genre_names = {g["id"]: g["name"] for g in genre_resp.json().get("genres", [])}
    except Exception as e:
        print(f"[Warning] Failed to fetch genre map ({e}); proceeding with defaults.")
        genre_names = {}

    app = create_app(load_model=False)
    imported = 0
    updated = 0
    page = 1

    print(f"\n[CinePhile] Starting TMDB sync: Target={target} movies (Details={with_details})...")
    start_time = time.time()

    with app.app_context():
        while (imported + updated) < target:
            try:
                discover_resp = session.get(
                    f"{BASE}/discover/movie",
                    params={
                        "language": "en-US",
                        "sort_by": "popularity.desc",
                        "include_adult": "false",
                        "include_video": "false",
                        "page": page,
                        "vote_count.gte": min_votes,
                    },
                    timeout=20,
                )
                if discover_resp.status_code != 200:
                    print(f"Failed discover page {page} ({discover_resp.status_code}), retrying...")
                    time.sleep(2)
                    continue
                data = discover_resp.json()
            except Exception as e:
                print(f"Error requesting page {page}: {e}. Retrying in 3s...")
                time.sleep(3)
                continue

            results = data.get("results", [])
            if not results:
                print("No more results returned from TMDB.")
                break

            for item in results:
                title = (item.get("title") or item.get("original_title") or "").strip()
                date = item.get("release_date") or ""
                poster_path = item.get("poster_path")
                backdrop_path = item.get("backdrop_path")

                # Require a valid title, release year, and at least a poster
                if not title or len(date) < 4 or not poster_path:
                    continue

                year = int(date[:4])
                tmdb_id = int(item["id"])

                # Artwork URLs with high-res standard sizes
                poster_url = f"{IMAGE}w500{poster_path}"
                backdrop_url = f"{IMAGE}w1280{backdrop_path}" if backdrop_path else poster_url

                # Basic discover metadata
                rating = float(item.get("vote_average") or 0.0)
                vote_count = int(item.get("vote_count") or 0)
                popularity = float(item.get("popularity") or 0.0)
                overview = (item.get("overview") or "").strip()
                genres = "|".join(genre_names.get(g, "") for g in item.get("genre_ids", []) if genre_names.get(g))

                director = ""
                cast_str = ""
                keywords_str = ""
                runtime = None

                # Enriched metadata (credits & keywords)
                if with_details:
                    details = fetch_movie_details(session, tmdb_id)
                    if details:
                        runtime = details.get("runtime")
                        if details.get("overview"):
                            overview = details["overview"].strip()

                        # Extract director
                        crew = details.get("credits", {}).get("crew", [])
                        director = next((c["name"] for c in crew if c.get("job") == "Director"), "")

                        # Extract top 5 cast
                        cast_members = [c["name"] for c in details.get("credits", {}).get("cast", [])[:5]]
                        cast_str = "|".join(cast_members)

                        # Extract top 10 keywords
                        kw_list = [k["name"] for k in details.get("keywords", {}).get("keywords", [])[:10]]
                        keywords_str = "|".join(kw_list)

                        # Genre names from details if available
                        if details.get("genres"):
                            genres = "|".join(g["name"] for g in details["genres"] if g.get("name"))

                # Database Upsert with safe transaction handling
                try:
                    movie = Movie.query.filter_by(tmdb_id=tmdb_id).first()
                    if movie is None:
                        movie = Movie.query.filter_by(title=title[:255], year=year).first()

                    is_new = movie is None
                    if is_new:
                        movie = Movie(tmdb_id=tmdb_id, title=title[:255], year=year)
                        db.session.add(movie)
                        imported += 1
                    else:
                        updated += 1

                    # Update attributes
                    movie.title = title[:255]
                    movie.year = year
                    movie.rating = rating
                    movie.vote_count = vote_count
                    movie.popularity = popularity
                    movie.overview = overview
                    movie.genres = genres
                    movie.poster_url = poster_url
                    movie.backdrop_url = backdrop_url
                    if director:
                        movie.director = director
                    if cast_str:
                        movie.cast = cast_str
                    if keywords_str:
                        movie.keywords = keywords_str
                    if runtime:
                        movie.runtime = runtime

                    db.session.commit()
                except Exception as ex:
                    db.session.rollback()
                    continue

                total_synced = imported + updated
                if total_synced % 20 == 0 or total_synced == target:
                    pct = (total_synced / target) * 100
                    print(f"[{total_synced}/{target}] ({pct:.1f}%) Synced: '{movie.title}' ({movie.year}) | Total in DB: {Movie.query.count()}")

                if total_synced >= target:
                    break

            total_pages = int(data.get("total_pages") or 500)
            if page >= min(total_pages, 500) or (imported + updated) >= target:
                break
            page += 1

        # Re-fit the recommender model on the freshly imported catalogue
        print("\n[CinePhile] Fitting recommender model on updated catalogue...")
        recommender.fit_from_db()
        elapsed = time.time() - start_time

        total_in_db = Movie.query.count()
        with_art = Movie.query.filter(Movie.poster_url != None).count()
        with_dir = Movie.query.filter(Movie.director != "", Movie.director != None).count()
        vocab_size = len(recommender.vectorizer.vocabulary_) if recommender.vectorizer else 0

        print(f"\n{'='*55}")
        print(f"Sync complete in {elapsed:.1f}s!")
        print(f"Newly Added: {imported} | Refreshed: {updated}")
        print(f"Total Movies in Database: {total_in_db}")
        print(f"Movies with Posters: {with_art}/{total_in_db}")
        print(f"Movies with Directors: {with_dir}/{total_in_db}")
        print(f"Recommender Vocabulary Size: {vocab_size} features")
        print(f"{'='*55}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=500, help="Target number of movies to sync (default: 500)")
    parser.add_argument("--no-details", dest="with_details", action="store_false", help="Skip credits/keywords for faster sync")
    parser.add_argument("--min-votes", type=int, default=10, help="Minimum vote count threshold")
    parser.set_defaults(with_details=True)
    args = parser.parse_args()
    run(target=args.target, with_details=args.with_details, min_votes=args.min_votes)

