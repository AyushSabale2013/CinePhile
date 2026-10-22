"""Load films into the database.

    python -m app.seed --if-empty                       # bundled sample data (used by Docker)
    python -m app.seed --reset                          # wipe and reload the sample data
    python -m app.seed --tmdb movies.csv credits.csv    # import the Kaggle TMDB 5000 files
"""
import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from . import create_app
from .extensions import db
from .models import Movie

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


def _upsert(records):
    existing = {(m.title, m.year): m for m in Movie.query.all()}
    added = updated = 0
    for r in records:
        key = (r["title"], r["year"])
        if key in existing:
            for k, v in r.items():
                setattr(existing[key], k, v)
            updated += 1
        else:
            db.session.add(Movie(**r))
            added += 1
    db.session.commit()
    return added, updated


def load_sample(path=SAMPLE_CSV):
    df = pd.read_csv(path).fillna("")
    records = [
        {
            "title": str(r.title), "year": int(r.year), "runtime": int(r.runtime),
            "rating": float(r.rating), "genres": r.genres, "keywords": r.keywords,
            "cast": r.cast, "director": r.director, "overview": r.overview,
        }
        for r in df.itertuples()
    ]
    return _upsert(records)


def _names(raw, limit=None, key="name"):
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return []
    names = [i[key] for i in items if key in i]
    return names[:limit] if limit else names


def load_tmdb(movies_csv, credits_csv):
    m = pd.read_csv(movies_csv)
    c = pd.read_csv(credits_csv).rename(columns={"movie_id": "id"})[["id", "cast", "crew"]]
    df = m.merge(c, on="id").dropna(subset=["overview", "release_date"])
    records = []
    for r in df.itertuples():
        director = next((p["name"] for p in json.loads(r.crew) if p.get("job") == "Director"), "")
        records.append({
            "title": str(r.title)[:255],
            "year": int(str(r.release_date)[:4]),
            "runtime": int(r.runtime) if pd.notna(r.runtime) else None,
            "rating": float(r.vote_average or 0),
            "genres": "|".join(_names(r.genres)),
            "keywords": "|".join(_names(r.keywords)),
            "cast": "|".join(_names(r.cast, 3)),
            "director": director,
            "overview": r.overview,
        })
    return _upsert(records)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--if-empty", action="store_true", help="only load when the movies table is empty")
    p.add_argument("--reset", action="store_true", help="delete all movies first")
    p.add_argument("--tmdb", nargs=2, metavar=("MOVIES_CSV", "CREDITS_CSV"))
    args = p.parse_args()

    app = create_app(load_model=False)
    with app.app_context():
        wait_for_db()
        if args.reset:
            db.drop_all()
            db.create_all()
        if args.if_empty and Movie.query.count() > 0:
            print(f"Database already has {Movie.query.count()} movies - skipping seed.")
            return
        added, updated = load_tmdb(*args.tmdb) if args.tmdb else load_sample()
        print(f"Seed complete: {added} added, {updated} updated, {Movie.query.count()} total.")


if __name__ == "__main__":
    main()
