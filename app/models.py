from datetime import datetime, timezone

from .extensions import db

SEP = "|"


def _split(value):
    return [p.strip() for p in (value or "").split(SEP) if p.strip()]


class Movie(db.Model):
    """One row per film. List-like fields are stored pipe-separated."""

    __tablename__ = "movies"
    __table_args__ = (db.UniqueConstraint("title", "year", name="uq_movie_title_year"),)

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    runtime = db.Column(db.Integer)                          # minutes
    rating = db.Column(db.Float, default=0.0, index=True)    # 0-10
    genres = db.Column(db.Text, default="")
    keywords = db.Column(db.Text, default="")
    cast = db.Column(db.Text, default="")
    director = db.Column(db.String(255), default="")
    overview = db.Column(db.Text, default="")
    poster_url = db.Column(db.String(500))
    backdrop_url = db.Column(db.String(500))
    tmdb_id = db.Column(db.Integer, unique=True, index=True)
    popularity = db.Column(db.Float, default=0.0)
    vote_count = db.Column(db.Integer, default=0)

    @property
    def genre_list(self):
        return _split(self.genres)

    @property
    def keyword_list(self):
        return _split(self.keywords)

    @property
    def cast_list(self):
        return _split(self.cast)

    @property
    def runtime_label(self):
        if not self.runtime:
            return ""
        h, m = divmod(self.runtime, 60)
        return f"{h}h {m:02d}m" if h else f"{m}m"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "rating": self.rating,
            "genres": self.genre_list,
            "director": self.director,
            "overview": self.overview or "",
            "runtime": self.runtime,
            "poster_url": self.poster_url or "",
            "backdrop_url": self.backdrop_url or "",
            "cast": self.cast_list,
            "popularity": self.popularity or 0,
            "vote_count": self.vote_count or 0,
        }


class MyListItem(db.Model):
    """A film saved by an (anonymous, cookie-identified) visitor."""

    __tablename__ = "my_list"
    __table_args__ = (db.UniqueConstraint("session_id", "movie_id", name="uq_list_session_movie"),)

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    movie_id = db.Column(db.Integer, db.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    added_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    movie = db.relationship("Movie")
