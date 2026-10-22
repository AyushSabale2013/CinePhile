"""TMDB API integration client.

Provides safe, cached access to the The Movie Database (TMDB) API v3.
Ensures API keys remain strictly on the backend, handles network errors,
rate limits, and provides standard image URL construction.
"""
import os
import time
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

# In-memory bounded cache for TMDB movie details
_MOVIE_CACHE = {}
_MAX_CACHE_SIZE = 1000


def get_api_key() -> str:
    """Retrieve the TMDB API key from environment or Flask configuration."""
    try:
        from flask import current_app
        key = current_app.config.get("TMDB_API_KEY")
        if key:
            return key.strip()
    except Exception:
        pass
    return os.getenv("TMDB_API_KEY", "").strip()


def build_image_url(path: str, size: str = "w500") -> str:
    """Safely construct a TMDB image URL.

    Handles:
      - None, empty, 'null', 'undefined'
      - Full URLs starting with http:// or https://
      - Paths with or without leading slash
    """
    if not path or not isinstance(path, str):
        return ""
    p = path.strip()
    if p.lower() in ("null", "undefined", "none", ""):
        return ""
    if p.startswith("http://") or p.startswith("https://"):
        return p
    clean_path = p.lstrip("/")
    return f"{TMDB_IMAGE_BASE_URL}/{size}/{clean_path}"


def _get_http_session(api_key: str) -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=8, pool_maxsize=8)
    session.mount("https://", adapter)
    session.params.update({"api_key": api_key})
    session.headers.update({"Accept": "application/json"})
    return session


def fetch_movie_from_tmdb(tmdb_id: int) -> dict | None:
    """Fetch movie details and credits from TMDB by its TMDB ID.

    Returns normalized dict or None if not found / error / no API key.
    """
    key = get_api_key()
    if not key or not tmdb_id:
        return None

    if tmdb_id in _MOVIE_CACHE:
        return _MOVIE_CACHE[tmdb_id]

    session = _get_http_session(key)
    try:
        resp = session.get(
            f"{TMDB_BASE_URL}/movie/{tmdb_id}",
            params={"append_to_response": "credits,keywords", "language": "en-US"},
            timeout=5.0,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    # Parse and normalize fields
    title = (data.get("title") or data.get("original_title") or "").strip()
    release_date = data.get("release_date") or ""
    year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else 0

    genres = [g["name"] for g in data.get("genres", []) if g.get("name")]
    keywords = [k["name"] for k in data.get("keywords", {}).get("keywords", []) if k.get("name")]

    crew = data.get("credits", {}).get("crew", [])
    director = next((c["name"] for c in crew if c.get("job") == "Director"), "")

    cast = [c["name"] for c in data.get("credits", {}).get("cast", [])[:5] if c.get("name")]

    poster_path = data.get("poster_path")
    backdrop_path = data.get("backdrop_path")

    normalized = {
        "tmdb_id": int(data["id"]),
        "title": title,
        "year": year,
        "runtime": data.get("runtime"),
        "rating": float(data.get("vote_average") or 0.0),
        "vote_count": int(data.get("vote_count") or 0),
        "popularity": float(data.get("popularity") or 0.0),
        "overview": (data.get("overview") or "").strip(),
        "genres": "|".join(genres),
        "keywords": "|".join(keywords[:10]),
        "cast": "|".join(cast),
        "director": director,
        "poster_url": build_image_url(poster_path, "w500"),
        "backdrop_url": build_image_url(backdrop_path or poster_path, "w1280"),
    }

    if len(_MOVIE_CACHE) >= _MAX_CACHE_SIZE:
        _MOVIE_CACHE.clear()
    _MOVIE_CACHE[tmdb_id] = normalized
    return normalized


def search_tmdb_movies(query: str, limit: int = 20) -> list[dict]:
    """Search TMDB API for movies matching a search string.

    Returns a list of normalized movie dictionaries.
    """
    key = get_api_key()
    q = (query or "").strip()
    if not key or not q:
        return []

    session = _get_http_session(key)
    try:
        resp = session.get(
            f"{TMDB_BASE_URL}/search/movie",
            params={"query": q, "language": "en-US", "page": 1, "include_adult": "false"},
            timeout=4.0,
        )
        if resp.status_code != 200:
            return []
        results = resp.json().get("results", [])
    except Exception:
        return []

    normalized_list = []
    for item in results[:limit]:
        title = (item.get("title") or item.get("original_title") or "").strip()
        date = item.get("release_date") or ""
        year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else 0
        poster_path = item.get("poster_path")
        backdrop_path = item.get("backdrop_path")

        normalized_list.append({
            "tmdb_id": int(item["id"]),
            "title": title,
            "year": year,
            "rating": float(item.get("vote_average") or 0.0),
            "vote_count": int(item.get("vote_count") or 0),
            "popularity": float(item.get("popularity") or 0.0),
            "overview": (item.get("overview") or "").strip(),
            "poster_url": build_image_url(poster_path, "w500"),
            "backdrop_url": build_image_url(backdrop_path or poster_path, "w1280"),
        })

    return normalized_list
