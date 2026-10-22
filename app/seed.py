"""Load films into the database safely and idempotently.

Usage:
    python -m app.seed --if-empty                       # bundled sample data with artwork (used on Render boot)
    python -m app.seed --tmdb                           # auto-discover & import Kaggle TMDB 5000 files
    python -m app.seed --tmdb movies.csv credits.csv    # import specified CSV files
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from . import create_app
from .extensions import db
from .models import Movie
from .tmdb import build_image_url

SAMPLE_CSV = Path(__file__).parent / "data" / "movies_seed.csv"


def wait_for_db(retries=40):
    for _ in range(retries):
        try:
            db.session.execute(text("SELECT 1"))
            return
        except Exception:
            db.session.rollback()
            time.sleep(1.5)
    sys.exit("Database is not reachable.")


def _safe_json_parse(raw):
    """Safely parse JSON string, returning empty list/dict on malformed content."""
    if not raw or pd.isna(raw):
        return []
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _names(raw, limit=None, key="name"):
    items = _safe_json_parse(raw)
    if not isinstance(items, list):
        return []
    names = [i[key] for i in items if isinstance(i, dict) and key in i and i[key]]
    return names[:limit] if limit else names


def _extract_director(crew_raw):
    crew = _safe_json_parse(crew_raw)
    if not isinstance(crew, list):
        return ""
    for member in crew:
        if isinstance(member, dict) and member.get("job") == "Director":
            return member.get("name", "").strip()
    return ""


def _upsert(records, batch_size=200):
    """Idempotently insert or update movie records.

    Matches by tmdb_id first, falling back to (title, year).
    Preserves existing poster/backdrop URLs if the incoming record is empty.
    Preserves user watchlists (MyListItem records are never touched).
    """
    existing_by_tmdb = {}
    existing_by_title_year = {}

    for m in Movie.query.all():
        if m.tmdb_id:
            existing_by_tmdb[m.tmdb_id] = m
        existing_by_title_year[(m.title.lower().strip(), m.year)] = m

    added = 0
    updated = 0

    for i, r in enumerate(records):
        tmdb_id = r.get("tmdb_id")
        title_year_key = (str(r.get("title", "")).lower().strip(), r.get("year"))

        target = None
        if tmdb_id and tmdb_id in existing_by_tmdb:
            target = existing_by_tmdb[tmdb_id]
        elif title_year_key in existing_by_title_year:
            target = existing_by_title_year[title_year_key]

        if target:
            for k, v in r.items():
                # Preserve existing poster/backdrop if the incoming record is empty
                if k in ("poster_url", "backdrop_url") and not v and getattr(target, k):
                    continue
                setattr(target, k, v)
            updated += 1
        else:
            new_movie = Movie(**r)
            db.session.add(new_movie)
            if tmdb_id:
                existing_by_tmdb[tmdb_id] = new_movie
            existing_by_title_year[title_year_key] = new_movie
            added += 1

        if (i + 1) % batch_size == 0:
            db.session.commit()

    db.session.commit()
    return added, updated


def load_sample(path=SAMPLE_CSV):
    if not Path(path).exists():
        sys.exit(f"Sample seed file not found at: {path}")

    df = pd.read_csv(path).fillna("")
    records = []
    for r in df.itertuples():
        poster_url = getattr(r, "poster_url", "")
        backdrop_url = getattr(r, "backdrop_url", "")
        tmdb_id = getattr(r, "tmdb_id", None)
        popularity = getattr(r, "popularity", 0.0)
        vote_count = getattr(r, "vote_count", 0)

        record = {
            "title": str(r.title).strip()[:255],
            "year": int(r.year) if r.year else 0,
            "runtime": int(r.runtime) if r.runtime else None,
            "rating": float(r.rating or 0.0),
            "genres": str(r.genres),
            "keywords": str(r.keywords),
            "cast": str(r.cast),
            "director": str(r.director),
            "overview": str(r.overview),
            "poster_url": build_image_url(poster_url, "w500"),
            "backdrop_url": build_image_url(backdrop_url or poster_url, "w1280"),
            "tmdb_id": int(tmdb_id) if tmdb_id and str(tmdb_id).isdigit() else None,
            "popularity": float(popularity or 0.0),
            "vote_count": int(vote_count or 0),
        }
        records.append(record)

    return _upsert(records)


def discover_tmdb_csvs():
    candidates = [
        ("data/tmdb_5000_movies.csv", "data/tmdb_5000_credits.csv"),
        ("tmdb_5000_movies.csv", "tmdb_5000_credits.csv"),
        ("data/movies.csv", "data/credits.csv"),
    ]
    for m_path, c_path in candidates:
        if Path(m_path).exists() and Path(c_path).exists():
            return m_path, c_path
    return None, None


def load_tmdb(movies_csv=None, credits_csv=None):
    if not movies_csv or not credits_csv:
        movies_csv, credits_csv = discover_tmdb_csvs()

    if not movies_csv or not credits_csv:
        print("[CinePhile] TMDB 5000 CSV files not found.")
        print("Please place 'tmdb_5000_movies.csv' and 'tmdb_5000_credits.csv' in the 'data/' directory,")
        print("or run: python -m app.seed --tmdb <path_to_movies.csv> <path_to_credits.csv>")
        return 0, 0

    print(f"[CinePhile] Importing TMDB dataset: {movies_csv} + {credits_csv}...")
    m = pd.read_csv(movies_csv)
    c = pd.read_csv(credits_csv).rename(columns={"movie_id": "id"})[["id", "cast", "crew"]]
    df = m.merge(c, on="id").dropna(subset=["overview", "release_date"])

    records = []
    for r in df.itertuples():
        director = _extract_director(getattr(r, "crew", ""))
        date_str = str(getattr(r, "release_date", ""))
        year = int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else 0
        if year == 0:
            continue

        raw_poster = getattr(r, "poster_path", "") or getattr(r, "poster_url", "")
        raw_backdrop = getattr(r, "backdrop_path", "") or getattr(r, "backdrop_url", "")

        records.append({
            "tmdb_id": int(r.id),
            "title": str(r.title).strip()[:255],
            "year": year,
            "runtime": int(r.runtime) if pd.notna(getattr(r, "runtime", None)) else None,
            "rating": float(getattr(r, "vote_average", 0) or 0.0),
            "vote_count": int(getattr(r, "vote_count", 0) or 0),
            "popularity": float(getattr(r, "popularity", 0.0) or 0.0),
            "genres": "|".join(_names(getattr(r, "genres", ""))),
            "keywords": "|".join(_names(getattr(r, "keywords", ""))),
            "cast": "|".join(_names(getattr(r, "cast", ""), 5)),
            "director": director,
            "overview": str(getattr(r, "overview", "") or ""),
            "poster_url": build_image_url(raw_poster, "w500"),
            "backdrop_url": build_image_url(raw_backdrop, "w1280"),
        })

    return _upsert(records)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--if-empty", action="store_true", help="only load when the movies table is empty")
    p.add_argument("--reset", action="store_true", help="delete all movies first (development only)")
    p.add_argument("--tmdb", nargs="*", metavar="CSV_FILE", help="import TMDB 5000 files (auto-detected if omitted)")
    args = p.parse_args()

    app = create_app(load_model=False)
    with app.app_context():
        wait_for_db()
        if args.reset:
            print("[Warning] Resetting movies table...")
            db.drop_all()
            db.create_all()

        if args.if_empty and Movie.query.count() > 0:
            print(f"Database already has {Movie.query.count()} movies - skipping seed.")
            return

        if args.tmdb is not None:
            if len(args.tmdb) == 2:
                added, updated = load_tmdb(args.tmdb[0], args.tmdb[1])
            else:
                added, updated = load_tmdb()
        else:
            added, updated = load_sample()

        print(f"Seed complete: {added} added, {updated} updated, {Movie.query.count()} total movies in database.")


if __name__ == "__main__":
    main()
