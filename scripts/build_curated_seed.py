"""
Build Curated Movie Dataset for CinePhile
=========================================
Ingests TMDB 5000 dataset, cleans and validates fields,
enriches artwork URLs using TMDB API, and generates a
clean, production-ready app/data/movies_seed.csv with exactly
4,000 distinct, valid movies.
"""
import os
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

from app.tmdb import build_image_url

ROOT = Path(__file__).parent.parent
MOVIES_CSV = ROOT / "tmdb_5000_movies.csv"
CREDITS_CSV = ROOT / "tmdb_5000_credits.csv"
OUTPUT_CSV = ROOT / "app" / "data" / "movies_seed.csv"


def get_api_key():
    key = os.getenv("TMDB_API_KEY", "").strip()
    if key:
        return key
    env_file = ROOT / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("TMDB_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return ""


def parse_names(val, limit=None):
    if not val or pd.isna(val):
        return []
    try:
        items = json.loads(val)
        names = [x["name"].strip() for x in items if isinstance(x, dict) and x.get("name")]
        return names[:limit] if limit else names
    except Exception:
        return []


def parse_director(crew_val):
    if not crew_val or pd.isna(crew_val):
        return ""
    try:
        crew = json.loads(crew_val)
        for c in crew:
            if isinstance(c, dict) and c.get("job") == "Director":
                return c.get("name", "").strip()
    except Exception:
        pass
    return ""


def fetch_artwork_map(api_key, target_ids):
    art_map = {}
    if not api_key:
        print("[Warning] No TMDB_API_KEY provided; proceeding without live artwork enrichment.")
        return art_map

    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25)
    session.mount("https://", adapter)

    target_set = set(target_ids)
    print(f"[CinePhile] Fetching TMDB Discover pages for fast artwork lookup ({len(target_set)} target movies)...")

    # Step 1: Bulk Discover queries (vote_count.desc and popularity.desc)
    def fetch_discover_page(args):
        sort_order, page = args
        try:
            r = session.get(
                "https://api.themoviedb.org/3/discover/movie",
                params={"api_key": api_key, "page": page, "sort_by": sort_order},
                timeout=6,
            )
            if r.status_code == 200:
                return r.json().get("results", [])
        except Exception:
            pass
        return []

    discover_tasks = [("vote_count.desc", p) for p in range(1, 201)] + [("popularity.desc", p) for p in range(1, 201)]
    with ThreadPoolExecutor(max_workers=12) as ex:
        pages = list(ex.map(fetch_discover_page, discover_tasks))

    for page_results in pages:
        for m in page_results:
            mid = m.get("id")
            if mid in target_set and m.get("poster_path") and mid not in art_map:
                art_map[mid] = (m["poster_path"], m.get("backdrop_path") or m["poster_path"])

    print(f"[CinePhile] Fast Discover collected artwork for {len(art_map)}/{len(target_set)} movies.")

    # Step 2: Concurrent detail queries for remaining movies (up to 1,800 movies)
    missing_ids = [mid for mid in target_ids if mid not in art_map]
    print(f"[CinePhile] Querying TMDB API for {len(missing_ids)} remaining movie artworks...")

    def fetch_single(mid):
        try:
            r = session.get(
                f"https://api.themoviedb.org/3/movie/{mid}",
                params={"api_key": api_key},
                timeout=5,
            )
            if r.status_code == 200:
                d = r.json()
                p = d.get("poster_path")
                b = d.get("backdrop_path")
                if p:
                    return mid, p, b or p
        except Exception:
            pass
        return mid, None, None

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(fetch_single, missing_ids))

    for mid, p, b in results:
        if p:
            art_map[mid] = (p, b)

    elapsed = time.time() - t0
    print(f"[CinePhile] Direct lookup complete in {elapsed:.1f}s. Total artworks collected: {len(art_map)}/{len(target_set)}.")
    return art_map


def build_curated_seed(target_count=4000):
    print(f"[CinePhile] Loading raw datasets: {MOVIES_CSV} & {CREDITS_CSV}...")
    movies = pd.read_csv(MOVIES_CSV)
    credits = pd.read_csv(CREDITS_CSV).rename(columns={"movie_id": "id"})[["id", "cast", "crew"]]
    df = movies.merge(credits, on="id")

    df["year"] = pd.to_datetime(df["release_date"], errors="coerce").dt.year

    print("[CinePhile] Parsing structured features (genres, directors, cast, keywords)...")
    df["genre_list"] = df["genres"].apply(parse_names)
    df["director_name"] = df["crew"].apply(parse_director)
    df["cast_list"] = df["cast"].apply(lambda x: parse_names(x, limit=5))
    df["keyword_list"] = df["keywords"].apply(parse_names)

    # Clean & validate
    valid_mask = (
        df["title"].fillna("").str.strip().ne("") &
        df["year"].notna() & (df["year"] > 1900) & (df["year"] <= 2026) &
        df["overview"].fillna("").str.strip().ne("") &
        df["runtime"].notna() & (df["runtime"] > 0) &
        (df["genre_list"].apply(len) > 0) &
        (df["director_name"].ne("")) &
        (df["vote_count"] >= 1)
    )

    cleaned = df[valid_mask].copy()
    cleaned = cleaned.drop_duplicates(subset=["id"]).drop_duplicates(subset=["title", "year"])
    print(f"[CinePhile] Total verified valid distinct records: {len(cleaned)}")

    # Sort by quality/popularity to take the top target_count
    sorted_df = cleaned.sort_values(by=["vote_count", "popularity"], ascending=[False, False])
    curated = sorted_df.iloc[:target_count].copy()
    print(f"[CinePhile] Selected top {len(curated)} movies (min vote_count: {curated.iloc[-1]['vote_count']}).")

    api_key = get_api_key()
    target_ids = curated["id"].astype(int).tolist()
    art_map = fetch_artwork_map(api_key, target_ids)

    # Format into application schema
    records = []
    for r in curated.itertuples():
        mid = int(r.id)
        raw_poster, raw_backdrop = art_map.get(mid, ("", ""))

        records.append({
            "title": str(r.title).strip()[:255],
            "year": int(r.year),
            "runtime": int(r.runtime),
            "rating": round(float(getattr(r, "vote_average", 0) or 0.0), 1),
            "genres": "|".join(r.genre_list),
            "keywords": "|".join(r.keyword_list[:12]),
            "cast": "|".join(r.cast_list),
            "director": r.director_name[:255],
            "overview": str(r.overview).strip(),
            "tmdb_id": mid,
            "poster_url": build_image_url(raw_poster, "w500") if raw_poster else "",
            "backdrop_url": build_image_url(raw_backdrop, "w1280") if raw_backdrop else "",
            "popularity": round(float(getattr(r, "popularity", 0.0) or 0.0), 4),
            "vote_count": int(getattr(r, "vote_count", 0) or 0),
        })

    out_df = pd.DataFrame(records)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUTPUT_CSV, index=False)

    size_mb = OUTPUT_CSV.stat().st_size / (1024 * 1024)
    with_posters = (out_df["poster_url"].str.strip() != "").sum()
    pct_posters = with_posters / len(out_df) * 100

    print(f"\n{'='*60}")
    print(f"Curated dataset generated successfully at: {OUTPUT_CSV}")
    print(f"Total Movies: {len(out_df)}")
    print(f"File Size: {size_mb:.2f} MB")
    print(f"Movies with TMDB Posters: {with_posters}/{len(out_df)} ({pct_posters:.1f}%)")
    print(f"Release Year Range: {out_df['year'].min()} - {out_df['year'].max()}")
    print(f"Runtime Range: {out_df['runtime'].min()} min - {out_df['runtime'].max()} min")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    build_curated_seed(target_count=4000)
