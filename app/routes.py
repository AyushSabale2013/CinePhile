import uuid
from datetime import date

from flask import Blueprint, abort, jsonify, render_template, request, session, send_from_directory, current_app
from sqlalchemy import or_

from .extensions import db
from .models import Movie, MyListItem
from .recommender import recommender

bp = Blueprint("main", __name__)

HOME_GENRES = ["Action", "Sci-Fi", "Drama", "Animation", "Comedy", "Thriller", "Romance", "Horror"]


# ----------------------------------------------------------------- helpers
def session_id():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    session.permanent = True
    return session["sid"]


def my_ids():
    rows = (
        MyListItem.query.filter_by(session_id=session_id())
        .order_by(MyListItem.added_at.desc())
        .all()
    )
    return [r.movie_id for r in rows]


def movies_by_ids(ids):
    if not ids:
        return []
    found = {m.id: m for m in Movie.query.filter(Movie.id.in_(ids)).all()}
    return [found[i] for i in ids if i in found]


def with_scores(pairs):
    """[(id, sim)] -> ([Movie], [sim]) keeping rank order."""
    movies = movies_by_ids([i for i, _ in pairs])
    score = dict(pairs)
    return movies, [score[m.id] for m in movies]


def all_genres():
    seen = set()
    for (g,) in db.session.query(Movie.genres).all():
        seen.update(p.strip() for p in (g or "").split("|") if p.strip())
    return sorted(seen)


def shared_terms(a, b):
    """Human-readable reasons two films are alike (explainable recommendations)."""
    out = []
    if a.director and a.director == b.director:
        out.append(a.director)
    for pool_a, pool_b in ((a.genre_list, b.genre_list), (a.keyword_list, b.keyword_list), (a.cast_list, b.cast_list)):
        out += [t for t in pool_a if t in pool_b]
    return out[:3]


def run_search(q, genre=None, limit=60):
    query = Movie.query
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Movie.title.ilike(like),
                Movie.genres.ilike(like),
                Movie.cast.ilike(like),
                Movie.director.ilike(like),
                Movie.keywords.ilike(like),
            )
        )
    if genre:
        query = query.filter(Movie.genres.ilike(f"%{genre}%"))
    rows = query.order_by(Movie.rating.desc()).all()
    ql = q.lower()
    rows.sort(key=lambda m: (not m.title.lower().startswith(ql), ql not in m.title.lower(), -(m.rating or 0)))
    return rows[:limit]


def hue(title):
    """Stable 0-359 hue per title, used for generated poster colours."""
    return sum(ord(c) * (i + 3) for i, c in enumerate(title)) % 360


@bp.app_context_processor
def inject_globals():
    return {"my_count": len(my_ids())}


# ------------------------------------------------------------------- pages
@bp.route("/")
def home():
    react_index = current_app.static_folder + "/react/index.html"
    import os
    if os.path.exists(react_index):
        return send_from_directory(current_app.static_folder + "/react", "index.html")
    top = Movie.query.order_by(Movie.rating.desc()).limit(12).all()
    featured = top[date.today().toordinal() % len(top)] if top else None

    rows = []
    liked = my_ids()
    if liked and recommender.ready:
        movies, sims = with_scores(recommender.for_profile(liked, 16))
        if movies:
            rows.append({"id": "for-you", "title": "Picked for you", "movies": movies, "sims": sims})
        last = movies_by_ids(liked[:1])
        if last:
            m2, s2 = with_scores(recommender.similar(last[0].id, 16))
            rows.append({"id": "because", "title": f"Because you added {last[0].title}", "movies": m2, "sims": s2})

    rows.append({"id": "top", "title": "Top rated", "movies": Movie.query.order_by(Movie.rating.desc()).limit(16).all(), "sims": None})
    modern = Movie.query.filter(Movie.year >= 2015).order_by(Movie.rating.desc()).limit(16).all()
    if modern:
        rows.append({"id": "modern", "title": "Modern hits (2015 onwards)", "movies": modern, "sims": None})
    for g in HOME_GENRES:
        ms = Movie.query.filter(Movie.genres.ilike(f"%{g}%")).order_by(Movie.rating.desc()).limit(16).all()
        if ms:
            rows.append({"id": g.lower().replace(" ", "-"), "title": g, "movies": ms, "sims": None})

    return render_template("index.html", featured=featured, rows=rows,
                           featured_in_list=bool(featured and featured.id in liked), page="home")


@bp.route("/movie/<int:movie_id>")
def movie(movie_id):
    m = db.session.get(Movie, movie_id) or Movie.query.filter_by(tmdb_id=movie_id).first()
    if not m:
        from .tmdb import fetch_movie_from_tmdb
        tmdb_data = fetch_movie_from_tmdb(movie_id)
        if not tmdb_data:
            abort(404)
    react_index = current_app.static_folder + "/react/index.html"
    import os
    if os.path.exists(react_index):
        return send_from_directory(current_app.static_folder + "/react", "index.html")
    similar, sims = with_scores(recommender.similar(m.id, 12)) if m else ([], [])
    reasons = [shared_terms(m, s) for s in similar] if m else []
    return render_template("movie.html", m=m, similar=list(zip(similar, sims, reasons)),
                           in_list=m.id in my_ids() if m else False, page="movie")


@bp.route("/search")
def search():
    react_index = current_app.static_folder + "/react/index.html"
    import os
    if os.path.exists(react_index):
        return send_from_directory(current_app.static_folder + "/react", "index.html")
    q = request.args.get("q", "").strip()
    genre = request.args.get("genre", "").strip()
    results = run_search(q, genre)
    return render_template("search.html", q=q, genre=genre, results=results,
                           genres=all_genres(), page="search")


@bp.route("/my-list")
def my_list():
    react_index = current_app.static_folder + "/react/index.html"
    import os
    if os.path.exists(react_index):
        return send_from_directory(current_app.static_folder + "/react", "index.html")
    ids = my_ids()
    movies = movies_by_ids(ids)
    picks, sims = with_scores(recommender.for_profile(ids, 12)) if ids else ([], [])
    return render_template("mylist.html", movies=movies, picks=picks, sims=sims, page="mylist")


@bp.route("/about")
def about():
    react_index = current_app.static_folder + "/react/index.html"
    import os
    if os.path.exists(react_index):
        return send_from_directory(current_app.static_folder + "/react", "index.html")
    return render_template("about.html", total=Movie.query.count(), page="about")


@bp.route("/healthz")
def healthz():
    return {"status": "ok", "movies": len(recommender.ids), "model_ready": recommender.ready}


# --------------------------------------------------------------------- API
@bp.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    limit = min(max(request.args.get("limit", 30, type=int), 1), 100)
    rows = run_search(q, limit=limit)
    results = [m.to_dict() for m in rows]

    # If local results are sparse and TMDB_API_KEY is available, enrich with TMDB search
    if len(results) < 5 and len(q) >= 3:
        from .tmdb import search_tmdb_movies
        tmdb_results = search_tmdb_movies(q, limit=limit - len(results))
        existing_tmdb_ids = {r.get("tmdb_id") for r in results if r.get("tmdb_id")}
        for tr in tmdb_results:
            if tr.get("tmdb_id") not in existing_tmdb_ids:
                tr["id"] = tr["tmdb_id"]
                results.append(tr)
                existing_tmdb_ids.add(tr["tmdb_id"])

    return jsonify({"results": results})


@bp.route("/api/recommend/<int:movie_id>")
def api_recommend(movie_id):
    m = db.session.get(Movie, movie_id) or Movie.query.filter_by(tmdb_id=movie_id).first() or abort(404)
    movies, sims = with_scores(recommender.similar(m.id, int(request.args.get("k", 10))))
    return jsonify({"movie": m.to_dict(),
                    "recommendations": [dict(x.to_dict(), similarity=round(s, 4)) for x, s in zip(movies, sims)]})


@bp.route("/api/my-list/<int:movie_id>", methods=["POST"])
def api_toggle_list(movie_id):
    m = db.session.get(Movie, movie_id) or Movie.query.filter_by(tmdb_id=movie_id).first() or abort(404)
    sid = session_id()
    item = MyListItem.query.filter_by(session_id=sid, movie_id=m.id).first()
    if item:
        db.session.delete(item)
        in_list = False
    else:
        db.session.add(MyListItem(session_id=sid, movie_id=m.id))
        in_list = True
    db.session.commit()
    count = MyListItem.query.filter_by(session_id=sid).count()
    return jsonify({"in_list": in_list, "count": count, "title": m.title})


@bp.app_errorhandler(404)
def not_found(_):
    return render_template("404.html", page="404"), 404

# React client API. Kept separate from the legacy server-rendered routes.
@bp.route("/api/home")
def api_home():
    total = Movie.query.count()
    top = Movie.query.order_by(Movie.popularity.desc(), Movie.rating.desc()).limit(1).all()
    featured = top[0] if top else None
    rows = []
    if total:
        rows.append({"title": "Popular on CinePhile", "movies": [m.to_dict() for m in Movie.query.order_by(Movie.popularity.desc(), Movie.rating.desc()).limit(24).all()]})
        rows.append({"title": "Top rated", "movies": [m.to_dict() for m in Movie.query.order_by(Movie.rating.desc(), Movie.vote_count.desc()).limit(24).all()]})
        recent = Movie.query.filter(Movie.year >= 2015).order_by(Movie.popularity.desc()).limit(24).all()
        if recent: rows.append({"title": "Modern hits", "movies": [m.to_dict() for m in recent]})
        for genre in HOME_GENRES:
            movies = Movie.query.filter(Movie.genres.ilike(f"%{genre}%")).order_by(Movie.popularity.desc(), Movie.rating.desc()).limit(20).all()
            if movies: rows.append({"title": genre, "movies": [m.to_dict() for m in movies]})
    ids = my_ids()
    if ids and recommender.ready:
        picks, sims = with_scores(recommender.for_profile(ids, 20))
        if picks:
            recs = []
            for rank, (x, s) in enumerate(zip(picks, sims)):
                d = x.to_dict()
                d["similarity"] = round(s, 4)
                # Realistic match percentage proportional to actual cosine similarity
                d["match_pct"] = int(min(96, max(42, round(46 + s * 115)))) if s > 0 else 45
                recs.append(d)
            rows.insert(0, {"title": "Picked for you", "movies": recs})
    return jsonify({"featured": featured.to_dict() if featured else None, "rows": rows,
                    "my_list": [m.to_dict() for m in movies_by_ids(ids)], "catalog_count": total})


@bp.route("/api/movie/<int:movie_id>")
def api_movie_detail(movie_id):
    # Lookup by primary key id first, then tmdb_id
    m = db.session.get(Movie, movie_id) or Movie.query.filter_by(tmdb_id=movie_id).first()

    # If not found in DB, check live TMDB API if key is available
    if not m:
        from .tmdb import fetch_movie_from_tmdb
        tmdb_data = fetch_movie_from_tmdb(movie_id)
        if tmdb_data:
            try:
                m = Movie(**tmdb_data)
                db.session.add(m)
                db.session.commit()
            except Exception:
                db.session.rollback()
                m = Movie.query.filter_by(tmdb_id=movie_id).first()

    if not m:
        abort(404)

    # Heal missing artwork if tmdb_id is present and TMDB API key is available
    if not m.poster_url and m.tmdb_id:
        from .tmdb import fetch_movie_from_tmdb
        info = fetch_movie_from_tmdb(m.tmdb_id)
        if info and info.get("poster_url"):
            m.poster_url = info["poster_url"]
            m.backdrop_url = info.get("backdrop_url") or m.poster_url
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    recs = []
    if recommender.ready:
        similar, sims = with_scores(recommender.similar(m.id, 18))
        for rank, (x, s) in enumerate(zip(similar, sims)):
            d = x.to_dict()
            d["similarity"] = round(s, 4)
            d["match_pct"] = int(min(96, max(42, round(46 + s * 115)))) if s > 0 else 45
            d["shared_reasons"] = shared_terms(m, x)
            recs.append(d)

    return jsonify({"movie": m.to_dict(), "recommendations": recs})


@bp.route("/api/metrics")
def api_metrics():
    from .evaluation import get_model_report
    k = min(max(request.args.get("k", 10, type=int), 3), 30)
    return jsonify(get_model_report(k=k))

