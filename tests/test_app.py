import pytest
import numpy as np

from app import create_app
from app.extensions import db
from app.models import Movie
from app.recommender import recommender, _stem_word, compute_bayesian_ratings
from app.seed import load_sample, _safe_json_parse, _names, _extract_director, _upsert
from app.evaluation import compute_metrics_summary, get_model_report
from app.tmdb import build_image_url, fetch_movie_from_tmdb, search_tmdb_movies


@pytest.fixture()
def client(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.db", "TESTING": True}, load_model=False)
    with app.app_context():
        load_sample()
        recommender.fit_from_db()
    with app.test_client() as c:
        yield c


def test_similar_films_make_sense(client):
    with client.application.app_context():
        dark = Movie.query.filter_by(title="The Dark Knight").one()
        ids = [i for i, _ in recommender.similar(dark.id, 5)]
        titles = [db.session.get(Movie, i).title for i in ids]
    assert "Joker" in titles or "Inception" in titles or "The Prestige" in titles
    assert "The Dark Knight" not in titles


def test_pages_render(client):
    for url in ["/", "/movie/1", "/search?q=nolan", "/search?genre=Drama", "/my-list", "/about", "/healthz"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/nope").status_code == 404
    assert client.get("/movie/999999999").status_code == 404


def test_my_list_toggle_and_personalisation(client):
    r = client.post("/api/my-list/4").get_json()
    assert r["in_list"] and r["count"] == 1
    r2 = client.post("/api/my-list/4").get_json()
    assert not r2["in_list"] and r2["count"] == 0


def test_search_api(client):
    data = client.get("/api/search?q=incep").get_json()
    assert data and data["results"][0]["title"] == "Inception"


def test_suffix_stemmer():
    assert _stem_word("aliens") == "alien"
    assert _stem_word("infiltrating") == "infiltrat"
    assert _stem_word("darkness") == "dark"
    assert _stem_word("the") == "the"


def test_bayesian_ratings():
    class DummyMovie:
        def __init__(self, rating, vote_count):
            self.rating = rating
            self.vote_count = vote_count

    movies = [DummyMovie(10.0, 1), DummyMovie(8.8, 10000), DummyMovie(5.5, 100), DummyMovie(6.2, 200)]
    wr = compute_bayesian_ratings(movies, min_votes=20)
    assert len(wr) == 4
    # The movie with 10000 votes should retain its rating (0.88), while the 1-vote 10.0 is shrunk toward mean (~0.75)
    assert wr[1] > wr[0]


def test_metrics_api(client):
    resp = client.get("/api/metrics?k=5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "metrics" in data
    assert data["metrics"]["catalogue_coverage_pct"] > 0
    assert data["metrics"]["intra_list_diversity"] > 0
    assert "hit_rate_at_k" in data["metrics"]
    assert "accuracy_at_k" in data["metrics"]


def test_explainability_in_movie_detail(client):
    resp = client.get("/api/movie/1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "recommendations" in data
    if data["recommendations"]:
        first = data["recommendations"][0]
        assert "match_pct" in first
        assert "shared_reasons" in first


def test_recommender_caching(client):
    with client.application.app_context():
        res1 = recommender.similar(1, k=5)
        res2 = recommender.similar(1, k=5)
        assert res1 == res2


def test_image_url_construction():
    assert build_image_url("") == ""
    assert build_image_url(None) == ""
    assert build_image_url("null") == ""
    assert build_image_url("undefined") == ""
    assert build_image_url("https://example.com/poster.jpg") == "https://example.com/poster.jpg"
    assert build_image_url("/path.jpg", "w500") == "https://image.tmdb.org/t/p/w500/path.jpg"
    assert build_image_url("path.jpg", "w342") == "https://image.tmdb.org/t/p/w342/path.jpg"


def test_tmdb_missing_credentials_graceful():
    # Calling TMDB functions with no key should return None / empty list gracefully
    assert fetch_movie_from_tmdb(None) is None
    assert search_tmdb_movies("") == []


def test_safe_json_parsing_and_extraction():
    # Corrupt or malformed json strings
    assert _safe_json_parse(None) == []
    assert _safe_json_parse("{corrupted-json") == []
    assert _safe_json_parse("") == []

    # _names with missing fields or invalid format
    assert _names(None) == []
    assert _names('[{}]') == []
    assert _names('[{"name": "Action"}, {"other": "value"}]') == ["Action"]

    # _extract_director with malformed crew
    assert _extract_director(None) == ""
    assert _extract_director("invalid") == ""
    assert _extract_director('[{"name": "Christopher Nolan", "job": "Director"}]') == "Christopher Nolan"


def test_detail_endpoint_tmdb_id_lookup(client):
    # Lookup movie by its tmdb_id directly
    with client.application.app_context():
        m = Movie.query.filter(Movie.tmdb_id != None).first()
        if m:
            resp = client.get(f"/api/movie/{m.tmdb_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["movie"]["title"] == m.title


def test_idempotent_database_upsert(client):
    with client.application.app_context():
        initial_count = Movie.query.count()
        # Loading sample seed again should not duplicate rows
        load_sample()
        assert Movie.query.count() == initial_count
