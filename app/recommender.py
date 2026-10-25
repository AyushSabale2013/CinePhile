"""
CinePhile Enhanced Recommender System
======================================
Standard ML Pipeline with Train/Test Split, Feature Engineering, and Evaluation.

Pipeline:
  1. Data Ingestion  — load all movies from DB ordered by id
  2. Feature Engineering — build weighted TF-IDF document per film
  3. Train/Test Split — deterministic 75% train / 25% test stratified by genre
  4. Vectorization — TfidfVectorizer fitted on TRAINING set only (no test leakage)
  5. Similarity Matrix — cosine similarity via dot product (L2-normalized vectors)
  6. Bayesian Rating Blend — IMDB formula for vote-confidence weighting
  7. Inference — similar() and for_profile() use the fitted vectorizer
  8. Evaluation — Precision@K, Recall@K, NDCG@K via leave-one-out on test set
"""

import math
import re
import random

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

# ------------------------------------------------------------------ constants
WEIGHTS = {
    "genres":   3,   # most discriminative for content similarity
    "director": 3,   # strong stylistic signal
    "keywords": 2,   # thematic signal
    "cast":     2,   # star/actor signal
    # overview: 1x (appended as raw text)
}

RATING_BLEND     = 0.12   # 88% cosine + 12% Bayesian rating
MIN_VOTES        = 50     # Bayesian 'm' — votes threshold for confidence
TRAIN_RATIO      = 0.78   # 78% train (2,000+ films), 22% test (500+ films)


# ================================================================== FEATURE ENGINEERING
def _token(text: str) -> str:
    """Lowercase, strip non-alphanumeric, join with underscore.
    'Christopher Nolan' -> 'christopher_nolan', 'Sci-Fi' -> 'sci_fi'
    """
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def _stem_word(word: str) -> str:
    """Rule-based suffix normalizer (no external NLP deps).
    Handles: -ing, -ies/-y, -ed, -ness, -ment, -ly, plural -s
    """
    w = word.lower()
    if len(w) <= 3:
        return w
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


def _normalize_overview(text: str) -> str:
    """Tokenize, stem, and return normalized overview string."""
    if not text:
        return ""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return " ".join(_stem_word(w) for w in words)


def build_document(movie) -> str:
    """
    Feature Engineering: build weighted composite text document for a movie.

    Field weights (token repetition approach):
      genres   x3  — most relevant for content matching
      director x3  — strong auteur signal
      keywords x2  — thematic relevance
      cast     x2  — actor/star signal
      overview x1  — stemmed free-text synopsis
    """
    parts = []
    parts += [_token(g) for g in movie.genre_list]   * WEIGHTS["genres"]
    parts += [_token(k) for k in movie.keyword_list] * WEIGHTS["keywords"]
    if movie.director:
        parts += [_token(movie.director)]             * WEIGHTS["director"]
    parts += [_token(c) for c in movie.cast_list]    * WEIGHTS["cast"]
    norm_ov = _normalize_overview(movie.overview)
    if norm_ov:
        parts.append(norm_ov)
    return " ".join(p for p in parts if p)


# ================================================================== BAYESIAN RATING
def compute_bayesian_ratings(movies, min_votes: int = MIN_VOTES) -> np.ndarray:
    """
    IMDB Bayesian Weighted Rating:
        WR = (v / (v + m)) * R  +  (m / (v + m)) * C
    where:
        v = vote_count for the film
        m = minimum votes threshold (confidence floor)
        R = film's raw rating
        C = mean rating across all films in catalogue
    Returns array of WR values normalized to [0, 1].
    """
    if not movies:
        return np.zeros(0)
    ratings = np.array([float(m.rating or 0.0) for m in movies], dtype=np.float64)
    votes   = np.array([float(getattr(m, "vote_count", 0) or 0) for m in movies], dtype=np.float64)
    valid   = ratings[ratings > 0]
    C       = float(np.mean(valid)) if len(valid) > 0 else 5.5
    denom   = votes + min_votes
    wr      = (votes / denom) * ratings + (min_votes / denom) * C
    return np.clip(wr / 10.0, 0.0, 1.0)


# ================================================================== TRAIN / TEST SPLIT
def train_test_split_movies(movies, train_ratio: float = TRAIN_RATIO, seed: int = 42):
    """
    Deterministic 75/25 stratified split by primary genre.

    Strategy:
      - Group movies by their first genre label.
      - Within each genre group, shuffle with fixed seed and take 75% for train.
      - Remaining 25% go to test. Guarantees genre coverage in both sets.
      - Movies with no genre are allocated to train.

    Returns (train_movies, test_movies).
    """
    rng = random.Random(seed)

    # Group by primary genre
    genre_groups: dict[str, list] = {}
    no_genre = []
    for m in movies:
        genres = m.genre_list
        if genres:
            key = genres[0]
            genre_groups.setdefault(key, []).append(m)
        else:
            no_genre.append(m)

    train, test = list(no_genre), []  # no-genre movies always in train
    for group in genre_groups.values():
        shuffled = list(group)
        rng.shuffle(shuffled)
        split_idx = max(1, int(len(shuffled) * train_ratio))
        train.extend(shuffled[:split_idx])
        if len(shuffled) > 1:
            test.extend(shuffled[split_idx:])

    return train, test


# ================================================================== EVALUATION METRICS
def precision_at_k(recommended: list, relevant: set, k: int) -> float:
    """Precision@K = |relevant ∩ top-K| / K"""
    top_k = recommended[:k]
    hits  = sum(1 for r in top_k if r in relevant)
    return hits / k if k > 0 else 0.0


def recall_at_k(recommended: list, relevant: set, k: int) -> float:
    """Recall@K = |relevant ∩ top-K| / |relevant|"""
    if not relevant:
        return 0.0
    top_k = recommended[:k]
    hits  = sum(1 for r in top_k if r in relevant)
    return hits / len(relevant)


def ndcg_at_k(recommended: list, relevant: set, k: int) -> float:
    """
    NDCG@K — Normalised Discounted Cumulative Gain.
    Rewards finding relevant items AND finding them near the top.
    DCG  = Σ rel_i / log2(i+2)  for i in 0..K-1
    IDCG = ideal DCG (all relevant items ranked first)
    NDCG = DCG / IDCG
    """
    top_k  = recommended[:k]
    dcg    = sum((1.0 / math.log2(i + 2)) for i, r in enumerate(top_k) if r in relevant)
    # Ideal DCG: place all |relevant| hits at the top
    ideal  = sum((1.0 / math.log2(i + 2)) for i in range(min(len(relevant), k)))
    return (dcg / ideal) if ideal > 0 else 0.0


def evaluate_model(
    recommender_obj,
    test_movies,
    k: int = 10,
    genre_groups: dict | None = None,
) -> dict:
    """
    Proper ML evaluation on the held-out TEST SET.

    Protocol (Leave-One-Out on genre groups):
      For each genre group with >= 3 test movies:
        - Pick one movie as the 'query' (held-out target).
        - The other movies in the same genre are 'relevant'.
        - Get top-K recommendations for the query using the FITTED model.
        - Measure Precision@K, Recall@K, NDCG@K.

    Also computes:
      - Catalogue Coverage: % of all catalogue movies ever recommended
      - Intra-List Diversity: mean pairwise cosine distance in recommendation lists
      - Explainability Ratio: % of recs sharing at least one attribute with query
    """
    if not recommender_obj.ready or len(test_movies) < 2:
        return _empty_metrics(k)

    rng = random.Random(99)

    # Build genre groups from test movies
    if genre_groups is None:
        genre_groups = {}
        for m in test_movies:
            for g in m.genre_list:
                genre_groups.setdefault(g, []).append(m.id)

    usable_genres = [g for g, ids in genre_groups.items() if len(ids) >= 3]
    if not usable_genres:
        return _empty_metrics(k)

    precisions, recalls, ndcgs = [], [], []
    recommended_ever = set()
    diversity_scores = []
    explainable, total_recs = 0, 0

    test_id_set = {m.id for m in test_movies}
    movie_dict  = {m.id: m for m in test_movies}

    num_trials = min(len(test_movies), 120)
    sampled_ids = rng.sample([m.id for m in test_movies if m.id in recommender_obj.pos], min(num_trials, len(test_movies)))

    for qid in sampled_ids:
        query_movie = movie_dict.get(qid)
        if not query_movie:
            continue

        # Relevant = test movies that share at least one genre with the query
        relevant = {
            m.id for m in test_movies
            if m.id != qid
            and set(m.genre_list) & set(query_movie.genre_list)
        }
        if not relevant:
            continue

        recs = recommender_obj.similar(qid, k=k)
        rec_ids = [r_id for r_id, _ in recs]

        # Ranking metrics (only count test-set recommendations)
        precisions.append(precision_at_k(rec_ids, relevant, k))
        recalls.append(recall_at_k(rec_ids, relevant, k))
        ndcgs.append(ndcg_at_k(rec_ids, relevant, k))

        recommended_ever.update(rec_ids)

        # Intra-list diversity
        valid_rows = [recommender_obj.pos[r] for r in rec_ids if r in recommender_obj.pos]
        if len(valid_rows) >= 2:
            sub = recommender_obj.matrix[valid_rows]
            sim_mat = linear_kernel(sub, sub)
            n = len(valid_rows)
            pairs = [(1.0 - float(sim_mat[i, j])) for i in range(n) for j in range(i + 1, n)]
            if pairs:
                diversity_scores.append(float(np.mean(pairs)))

        # Explainability (shared genre / director / cast / keyword)
        for r_id, _ in recs:
            cand = movie_dict.get(r_id)
            if not cand:
                continue
            total_recs += 1
            shared = (
                (query_movie.director and query_movie.director == cand.director)
                or bool(set(query_movie.genre_list)   & set(cand.genre_list))
                or bool(set(query_movie.cast_list)    & set(cand.cast_list))
                or bool(set(query_movie.keyword_list) & set(cand.keyword_list))
            )
            if shared:
                explainable += 1

    all_catalogue = set(recommender_obj.ids)
    coverage = len(recommended_ever & all_catalogue) / len(all_catalogue) if all_catalogue else 0.0

    return {
        "accuracy_at_k":            round(float(sum(1 for p in precisions if p > 0) / len(precisions)) if precisions else 0.0, 4),
        "precision_at_k":           round(float(np.mean(precisions)) if precisions else 0.0,  4),
        "recall_at_k":              round(float(np.mean(recalls))    if recalls    else 0.0,  4),
        "ndcg_at_k":                round(float(np.mean(ndcgs))      if ndcgs      else 0.0,  4),
        "catalogue_coverage_pct":   round(coverage * 100,                                      2),
        "intra_list_diversity":     round(float(np.mean(diversity_scores)) if diversity_scores else 0.0, 4),
        "explainability_pct":       round((explainable / total_recs * 100) if total_recs else 0.0, 2),
        "num_test_queries":         len(precisions),
        "k":                        k,
    }


def _empty_metrics(k):
    return {
        "accuracy_at_k": 0.0, "precision_at_k": 0.0, "recall_at_k": 0.0, "ndcg_at_k": 0.0,
        "catalogue_coverage_pct": 0.0, "intra_list_diversity": 0.0,
        "explainability_pct": 0.0, "num_test_queries": 0, "k": k,
    }


# ================================================================== RECOMMENDER CLASS
class Recommender:
    """
    Content-Based Recommender with proper Train/Test ML Pipeline.

    Attributes exposed for the /api/metrics endpoint:
        train_ids      — list of movie IDs used to fit the vectorizer
        test_ids       — list of held-out movie IDs
        split_stats    — dict with counts and percentages
        eval_results   — cached evaluation metrics dict
    """

    def __init__(self):
        self.ids          = []       # ALL movie ids (train + test)
        self.pos          = {}       # id -> matrix row index
        self.ratings      = np.zeros(0)
        self.matrix       = None     # TF-IDF matrix for ALL movies (train transform on train; transform on test)
        self.vectorizer   = None     # fitted on TRAIN only

        # Split tracking
        self.train_ids    = []
        self.test_ids     = []
        self.split_stats  = {}
        self.eval_results = {}

        self._similar_cache: dict = {}

    @property
    def ready(self) -> bool:
        return self.matrix is not None and len(self.ids) > 1

    # -------------------------------------------------------------- fit
    def fit(self, movies):
        """
        Full ML Pipeline:
          1. Train/test split (75/25 stratified by genre)
          2. Feature engineering (build_document per movie)
          3. Fit TfidfVectorizer on TRAIN set only
          4. Transform ALL movies (train + test) using fitted vectorizer
          5. Compute Bayesian ratings for blending
          6. Evaluate on TEST set
          7. Cache results in self.eval_results
        """
        movies = list(movies)
        if len(movies) < 4:
            self._reset()
            return self

        # Step 1: Train/Test Split
        train_movies, test_movies = train_test_split_movies(movies, TRAIN_RATIO)
        self.train_ids = [m.id for m in train_movies]
        self.test_ids  = [m.id for m in test_movies]

        n_total = len(movies)
        self.split_stats = {
            "total":      n_total,
            "train":      len(train_movies),
            "test":       len(test_movies),
            "train_pct":  round(len(train_movies) / n_total * 100, 1),
            "test_pct":   round(len(test_movies)  / n_total * 100, 1),
        }

        # Step 2: Feature Engineering — build documents for all movies
        all_docs        = [build_document(m) for m in movies]
        train_docs      = [build_document(m) for m in train_movies]

        # Step 3: Fit vectorizer on TRAIN ONLY (prevent data leakage)
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            sublinear_tf=True,          # log(1+tf) to dampen high frequencies
            ngram_range=(1, 2),         # unigrams + bigrams
            min_df=2,                   # ignore extremely rare tokens
            max_df=0.90,                # ignore overly common tokens
        )
        self.vectorizer.fit(train_docs)

        # Step 4: Transform ALL movies using the FITTED vectorizer
        self.matrix = self.vectorizer.transform(all_docs)

        # Build index lookup over ALL movies
        self.ids  = [m.id for m in movies]
        self.pos  = {mid: i for i, mid in enumerate(self.ids)}
        self.ratings = compute_bayesian_ratings(movies)
        self._similar_cache.clear()

        # Step 5: Evaluate on TEST set
        self.eval_results = evaluate_model(self, test_movies, k=10)

        print(
            f"[Recommender] Fit complete. "
            f"Train={len(train_movies)} | Test={len(test_movies)} | "
            f"Vocab={len(self.vectorizer.vocabulary_)} | "
            f"P@10={self.eval_results['precision_at_k']:.4f} | "
            f"R@10={self.eval_results['recall_at_k']:.4f} | "
            f"NDCG@10={self.eval_results['ndcg_at_k']:.4f}"
        )
        return self

    def fit_from_db(self):
        from .models import Movie
        return self.fit(Movie.query.order_by(Movie.id).all())

    def _reset(self):
        self.ids = []; self.pos = {}; self.ratings = np.zeros(0)
        self.matrix = None; self.vectorizer = None
        self.train_ids = []; self.test_ids = []; self.split_stats = {}
        self.eval_results = {}; self._similar_cache = {}

    # -------------------------------------------------------------- inference
    def similar(self, movie_id: int, k: int = 12, movie=None):
        """Top-K similar films for a given movie id (cosine + Bayesian blend). Cached."""
        if not self.ready:
            return []
        cache_key = (movie_id, k)
        if cache_key in self._similar_cache:
            return self._similar_cache[cache_key]

        if movie_id in self.pos:
            i = self.pos[movie_id]
            sims = linear_kernel(self.matrix[i], self.matrix).ravel()
            sims[i] = -1.0
        else:
            if movie is None:
                from .models import Movie
                from .extensions import db
                movie = db.session.get(Movie, movie_id)
            if not movie:
                return []
            doc = build_document(movie)
            if not doc.strip():
                return []
            vec = self.vectorizer.transform([doc])
            sims = linear_kernel(vec, self.matrix).ravel()

        result = self._top(sims, k)
        if len(self._similar_cache) > 2000:
            self._similar_cache.clear()
        self._similar_cache[cache_key] = result
        return result

    def for_profile(self, liked_ids: list, k: int = 16, decay_factor: float = 0.90):
        """
        Personalised recommendations via exponential recency-decay centroid.
        Most-recently added movie has weight 1.0, next 0.9, then 0.81, etc.
        """
        valid = [(i, self.pos[mid]) for i, mid in enumerate(liked_ids) if mid in self.pos]
        if not self.ready or not valid:
            return []
        rows    = [pos for _, pos in valid]
        weights = np.array([decay_factor**rank for rank, _ in valid], dtype=np.float64)
        weights /= weights.sum()
        sub     = self.matrix[rows].toarray()
        centroid = np.sum(sub * weights[:, np.newaxis], axis=0)
        norm    = np.linalg.norm(centroid)
        if norm == 0:
            return []
        sims = np.asarray(self.matrix @ (centroid / norm)).ravel()
        for _, pos in valid:
            sims[pos] = -1.0
        return self._top(sims, k)

    def _top(self, sims: np.ndarray, k: int):
        score = (1 - RATING_BLEND) * sims + RATING_BLEND * self.ratings
        score[sims < 0] = -1.0
        order = np.argsort(-score)[:k]
        return [(self.ids[j], float(sims[j])) for j in order if sims[j] >= 0]


recommender = Recommender()
