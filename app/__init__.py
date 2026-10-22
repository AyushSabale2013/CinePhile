import time

from flask import Flask
from sqlalchemy.exc import OperationalError
from sqlalchemy import inspect, text

from .config import Config
from .extensions import db
from .recommender import recommender


def create_app(config=None, load_model=True):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    db.init_app(app)

    from .routes import bp, hue

    app.jinja_env.globals["hue"] = hue  # also visible inside imported macros
    app.register_blueprint(bp)

    with app.app_context():
        for attempt in range(30):  # tolerate a database that is still starting up
            try:
                db.create_all()
                break
            except OperationalError:
                if attempt == 29:
                    raise
                time.sleep(2)
        # Additive migration for databases created by earlier CinePhile versions.
        inspector = inspect(db.engine)
        if "movies" in inspector.get_table_names():
            existing = {column["name"] for column in inspector.get_columns("movies")}
            additions = {"backdrop_url": "VARCHAR(500)", "tmdb_id": "INTEGER", "popularity": "FLOAT DEFAULT 0", "vote_count": "INTEGER DEFAULT 0"}
            for name, sql_type in additions.items():
                if name not in existing:
                    db.session.execute(text(f"ALTER TABLE movies ADD COLUMN {name} {sql_type}"))
            db.session.commit()
        if load_model:
            recommender.fit_from_db()
            # Release DB connections before gunicorn forks workers (--preload).
            db.session.remove()
            db.engine.dispose()

    return app
