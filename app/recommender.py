"""Content-based recommender: TF-IDF vectors + cosine similarity (scikit-learn).

Each film becomes a weighted text document built from genres, keywords, director, cast,
and normalized synopsis text. Structured entities are underscore-linked to preserve multi-word
tokens (e.g. 'christopher_nolan', 'science_fiction').

Includes:
  - Text normalization with suffix-based stemming for plot synopses
  - IMDB Bayesian weighted rating blending (votes confidence threshold)
  - Exponential recency decay for profile centroid personalization
"""
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

# Relative importance multiplier for structured metadata
WEIGHTS = {
    "genres": 3,
    "director": 3,
    "keywords": 2,
    "cast": 2,
}

RATING_BLEND = 0.12  # 88% content cosine similarity + 12% Bayesian rating confidence
MIN_VOTES_THRESHOLD = 20  # Minimum votes 'm' for Bayesian average calculation


def _token(text: str) -> str:
    """Sanitize and join multi-word entities with underscores."""
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def _stem_word(word: str) -> str:
    """Lightweight rule-based suffix normalizer for plot synopses without external NLP dependencies."""
    w = word.lower()
    if len(w) <= 3:
        return w
    # Common English inflectional suffixes
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    if w.endswith("ness") and len(w) > 6:
        return w[:-4]
    if w.endswith("ment") and len(w) > 6:
        return w[:-4]
    if w.endswith("ly") and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _normalize_overview(overview: str) -> str:
    """Extract and stem words from free-text overview."""
    if not overview:
        return ""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", overview.lower())
    return " ".join(_stem_word(w) for w in words)


def build_document(movie) -> str:
    """Build a composite document representation for a movie."""
    parts = []
    # Weighted structured entities
    parts += [_token(g) for g in movie.genre_list] * WEIGHTS["genres"]
    parts += [_token(k) for k in movie.keyword_list] * WEIGHTS["keywords"]
    if movie.director:
        parts += [_token(movie.director)] * WEIGHTS["director"]
    parts += [_token(c) for c in movie.cast_list] * WEIGHTS["cast"]
    # Normalized plot synopsis
    norm_overview = _normalize_overview(movie.overview)
    if norm_overview:
        parts.append(norm_overview)
    return " ".join(p for p in parts if p)


def compute_bayesian_ratings(movies, min_votes: int = MIN_VOTES_THRESHOLD) -> np.ndarray:
    """Calculate IMDB Bayesian weighted average rating WR = (v / (v + m)) * R + (m / (v + m)) * C."""
    if not movies:
        return np.zeros(0)

    ratings = np.array([float(m.rating or 0.0) for m in movies], dtype=np.float64)
    votes = np.array([float(getattr(m, "vote_count", 0) or 0) for m in movies], dtype=np.float64)

    # Global mean rating C across items with non-zero ratings
    valid_ratings = ratings[ratings > 0]
    c = float(np.mean(valid_ratings)) if len(valid_ratings) > 0 else 5.5

    # Bayesian weighted rating
    denom = votes + min_votes
    wr = (votes / denom) * ratings + (min_votes / denom) * c

    # Normalize to 0.0 - 1.0 range
    return np.clip(wr / 10.0, 0.0, 1.0)


class Recommender:
    def __init__(self):
        self.ids = []
        self.pos = {}
        self.ratings = np.zeros(0)
        self.matrix = None
        self.vectorizer = None

    @property
    def ready(self) -> bool:
        return self.matrix is not None and len(self.ids) > 1

    def fit(self, movies):
        movies = list(movies)
        self.ids = [m.id for m in movies]
        self.pos = {mid: i for i, mid in enumerate(self.ids)}
        self.ratings = compute_bayesian_ratings(movies)

        if len(movies) < 2:
            self.matrix = None
            return self

        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            sublinear_tf=True,
            ngram_range=(1, 2),  # capture single tokens and bigrams like 'sci_fi', 'mind_bending'
            min_df=1,
            max_df=0.95,
        )
        self.matrix = self.vectorizer.fit_transform([build_document(m) for m in movies])
        return self

    def fit_from_db(self):
        from .models import Movie

        return self.fit(Movie.query.order_by(Movie.id).all())

    # ------------------------------------------------------------------ queries
    def similar(self, movie_id: int, k: int = 12):
        """Films most like `movie_id` -> [(movie_id, cosine_similarity)]."""
        if not self.ready or movie_id not in self.pos:
            return []
        i = self.pos[movie_id]
        sims = linear_kernel(self.matrix[i], self.matrix).ravel()
        sims[i] = -1.0
        return self._top(sims, k)

    def for_profile(self, liked_ids: list, k: int = 16, decay_factor: float = 0.90):
        """Personalised picks: exponential recency decay centroid over user watchlist."""
        valid_indices = [(i, self.pos[mid]) for i, mid in enumerate(liked_ids) if mid in self.pos]
        if not self.ready or not valid_indices:
            return []

        # Exponential recency weights: w_i = decay_factor^rank
        rows = [pos for _, pos in valid_indices]
        weights = np.array([decay_factor**rank for rank, _ in valid_indices], dtype=np.float64)
        weights /= weights.sum()

        submatrix = self.matrix[rows].toarray()
        weighted_centroid = np.sum(submatrix * weights[:, np.newaxis], axis=0)

        norm = np.linalg.norm(weighted_centroid)
        if norm == 0:
            return []

        normalized_centroid = weighted_centroid / norm
        sims = np.asarray(self.matrix @ normalized_centroid).ravel()

        for _, pos in valid_indices:
            sims[pos] = -1.0

        return self._top(sims, k)

    def _top(self, sims: np.ndarray, k: int):
        score = (1 - RATING_BLEND) * sims + RATING_BLEND * self.ratings
        score[sims < 0] = -1.0  # keep excluded items out
        order = np.argsort(-score)[:k]
        return [(self.ids[j], float(sims[j])) for j in order if sims[j] >= 0]


recommender = Recommender()

