import pytest

from app import create_app
from app.extensions import db
from app.recommender import recommender
from app.seed import load_sample


@pytest.fixture()
def client(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.db", "TESTING": True}, load_model=False)
    with app.app_context():
        load_sample()
        recommender.fit_from_db()
    with app.test_client() as c:
        yield c


def test_similar_films_make_sense(client):
    from app.models import Movie

    with client.application.app_context():
        dark = Movie.query.filter_by(title="The Dark Knight").one()
        ids = [i for i, _ in recommender.similar(dark.id, 5)]
        titles = [db.session.get(Movie, i).title for i in ids]
    assert "Joker" in titles or "Inception" in titles
    assert "The Dark Knight" not in titles


def test_pages_render(client):
    for url in ["/", "/movie/1", "/search?q=nolan", "/search?genre=Drama", "/my-list", "/about", "/healthz"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/nope").status_code == 404
    assert client.get("/movie/9999").status_code == 404


def test_my_list_toggle_and_personalisation(client):
    r = client.post("/api/my-list/4").get_json()
    assert r["in_list"] and r["count"] == 1
    assert b"Picked for you" in client.get("/").data
    r = client.post("/api/my-list/4").get_json()
    assert not r["in_list"] and r["count"] == 0


def test_search_api(client):
    data = client.get("/api/search?q=incep").get_json()
    assert data and data[0]["title"] == "Inception"
