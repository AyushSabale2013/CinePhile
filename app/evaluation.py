"""Quantitative evaluation framework for CinePhile recommendation model.

Computes offline ranking, diversity, coverage, novelty, and explainability metrics:
  - Catalogue Coverage @ K
  - Intra-List Diversity (ILD) @ K
  - Novelty (Self-Information) @ K
  - Explainability Ratio @ K
  - Hit Rate @ K, Precision @ K, Recall @ K, NDCG @ K (Leave-One-Out Profile Validation)

Usage:
    python -m app.evaluation --k 10 --samples 100
"""
import argparse
import math
import random
import time
from typing import Dict, List, Any

import numpy as np
from sklearn.metrics.pairwise import linear_kernel

from . import create_app
from .extensions import db
from .models import Movie
from .recommender import recommender


def evaluate_catalogue_coverage(recommender, movie_ids: List[int], k: int = 10) -> float:
    """Fraction of total catalogue items recommended at least once in top-k."""
    if not recommender.ready or not movie_ids:
        return 0.0

    recommended_set = set()
    for mid in movie_ids:
        sims = recommender.similar(mid, k=k)
        for rec_id, _ in sims:
            recommended_set.add(rec_id)

    return len(recommended_set) / len(movie_ids)


def evaluate_intra_list_diversity(recommender, movie_ids: List[int], k: int = 10, sample_size: int = 100) -> float:
    """Mean pairwise cosine distance between recommended items in a recommendation list."""
    if not recommender.ready or len(movie_ids) < 2:
        return 0.0

    sampled = random.sample(movie_ids, min(sample_size, len(movie_ids)))
    diversity_scores = []

    for mid in sampled:
        sims = recommender.similar(mid, k=k)
        if len(sims) < 2:
            continue
        rec_ids = [r_id for r_id, _ in sims if r_id in recommender.pos]
        if len(rec_ids) < 2:
            continue

        rows = [recommender.pos[r_id] for r_id in rec_ids]
        submatrix = recommender.matrix[rows]
        sim_matrix = linear_kernel(submatrix, submatrix)

        n = len(rec_ids)
        pairwise_dists = []
        for i in range(n):
            for j in range(i + 1, n):
                pairwise_dists.append(1.0 - max(0.0, float(sim_matrix[i, j])))

        if pairwise_dists:
            diversity_scores.append(float(np.mean(pairwise_dists)))

    return float(np.mean(diversity_scores)) if diversity_scores else 0.0


def evaluate_novelty(recommender, movies: List[Movie], k: int = 10, sample_size: int = 100) -> float:
    """Mean self-information (bits) of recommended items: -log2(p(i)).

    Higher novelty indicates recommending long-tail, discovery items rather than only top blockbusters.
    """
    if not recommender.ready or not movies:
        return 0.0

    # Item probabilities based on popularity (or vote_count)
    pop_map = {m.id: max(1.0, float(m.popularity or 1.0)) for m in movies}
    total_pop = sum(pop_map.values())
    prob_map = {mid: pop / total_pop for mid, pop in pop_map.items()}

    movie_ids = [m.id for m in movies]
    sampled = random.sample(movie_ids, min(sample_size, len(movie_ids)))
    novelty_scores = []

    for mid in sampled:
        sims = recommender.similar(mid, k=k)
        if not sims:
            continue
        item_bits = [-math.log2(prob_map.get(rec_id, 1e-6)) for rec_id, _ in sims]
        novelty_scores.append(float(np.mean(item_bits)))

    return float(np.mean(novelty_scores)) if novelty_scores else 0.0


def evaluate_explainability(recommender, movie_dict: Dict[int, Movie], k: int = 10, sample_size: int = 100) -> float:
    """Percentage of recommendations that share at least one explicit attribute (genre, director, cast)."""
    if not recommender.ready or not movie_dict:
        return 0.0

    movie_ids = list(movie_dict.keys())
    sampled = random.sample(movie_ids, min(sample_size, len(movie_ids)))
    explainable_count = 0
    total_recs = 0

    for mid in sampled:
        source = movie_dict.get(mid)
        if not source:
            continue
        sims = recommender.similar(mid, k=k)
        for rec_id, _ in sims:
            candidate = movie_dict.get(rec_id)
            if not candidate:
                continue
            total_recs += 1
            # Check overlap in director, genres, keywords, or cast
            same_dir = bool(source.director and source.director == candidate.director)
            shared_genre = bool(set(source.genre_list) & set(candidate.genre_list))
            shared_cast = bool(set(source.cast_list) & set(candidate.cast_list))
            shared_kw = bool(set(source.keyword_list) & set(candidate.keyword_list))

            if same_dir or shared_genre or shared_cast or shared_kw:
                explainable_count += 1

    return (explainable_count / total_recs) if total_recs > 0 else 0.0


def evaluate_leave_one_out_profiles(recommender, movies: List[Movie], k: int = 10, num_profiles: int = 60) -> Dict[str, float]:
    """Simulate cluster-based multi-item user watchlists and evaluate Leave-One-Out retrieval.

    For a synthetic user profile liking [m1, m2, m3, target], we hide 'target',
    compute profile recommendations on [m1, m2, m3], and check if 'target' is in top-k.
    """
    if not recommender.ready or len(movies) < 5:
        return {"hit_rate": 0.0, "precision": 0.0, "recall": 0.0, "ndcg": 0.0}

    # Group movies by primary genre
    genre_groups: Dict[str, List[int]] = {}
    for m in movies:
        for g in m.genre_list:
            genre_groups.setdefault(g, []).append(m.id)

    valid_genres = [g for g, mids in genre_groups.items() if len(mids) >= 5]
    if not valid_genres:
        return {"hit_rate": 0.0, "precision": 0.0, "recall": 0.0, "ndcg": 0.0}

    hits = 0
    ndcg_sum = 0.0
    evaluated = 0

    for _ in range(num_profiles):
        g = random.choice(valid_genres)
        mids = genre_groups[g]
        selected = random.sample(mids, 4)
        history = selected[:3]
        target = selected[3]

        recs = recommender.for_profile(history, k=k)
        rec_ids = [r_id for r_id, _ in recs]

        if target in rec_ids:
            hits += 1
            rank = rec_ids.index(target) + 1
            ndcg_sum += 1.0 / math.log2(rank + 1)
        evaluated += 1

    hit_rate = hits / evaluated if evaluated > 0 else 0.0
    ndcg = ndcg_sum / evaluated if evaluated > 0 else 0.0
    precision = hit_rate / k
    recall = hit_rate  # 1 relevant target held out

    return {
        "hit_rate": round(hit_rate, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "ndcg": round(ndcg, 4),
    }


def compute_metrics_summary(k: int = 10, sample_size: int = 80) -> Dict[str, Any]:
    """Execute complete metrics suite and return structured dictionary."""
    movies = Movie.query.all()
    if not movies or not recommender.ready:
        recommender.fit(movies)

    movie_dict = {m.id: m for m in movies}
    movie_ids = [m.id for m in movies]

    t0 = time.time()
    coverage = evaluate_catalogue_coverage(recommender, movie_ids, k=k)
    ild = evaluate_intra_list_diversity(recommender, movie_ids, k=k, sample_size=sample_size)
    novelty = evaluate_novelty(recommender, movies, k=k, sample_size=sample_size)
    explainability = evaluate_explainability(recommender, movie_dict, k=k, sample_size=sample_size)
    profile_metrics = evaluate_leave_one_out_profiles(recommender, movies, k=k, num_profiles=min(60, len(movies)))
    elapsed = time.time() - t0

    return {
        "catalogue_size": len(movies),
        "k": k,
        "evaluation_time_seconds": round(elapsed, 2),
        "metrics": {
            "catalogue_coverage_pct": round(coverage * 100, 2),
            "intra_list_diversity": round(ild, 4),
            "novelty_score_bits": round(novelty, 3),
            "explainability_pct": round(explainability * 100, 2),
            "hit_rate_at_k": profile_metrics["hit_rate"],
            "precision_at_k": profile_metrics["precision"],
            "recall_at_k": profile_metrics["recall"],
            "ndcg_at_k": profile_metrics["ndcg"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=10, help="Top-K cutoff for evaluation (default: 10)")
    parser.add_argument("--samples", type=int, default=80, help="Sample size for pairwise metrics")
    args = parser.parse_args()

    app = create_app(load_model=True)
    with app.app_context():
        print(f"\n[CinePhile] Running Recommender Evaluation Suite (K={args.k})...")
        summary = compute_metrics_summary(k=args.k, sample_size=args.samples)
        m = summary["metrics"]

        print("\n" + "=" * 55)
        print("RECOMMENDATION MODEL EVALUATION REPORT")
        print("=" * 55)
        print(f"Catalogue Size:        {summary['catalogue_size']} movies")
        print(f"Top-K Cutoff:          K = {summary['k']}")
        print(f"Evaluation Latency:    {summary['evaluation_time_seconds']}s")
        print("-" * 55)
        print(f"Catalogue Coverage:    {m['catalogue_coverage_pct']}% of catalogue reached")
        print(f"Intra-List Diversity:  {m['intra_list_diversity']:.4f} (Pairwise Cosine Distance)")
        print(f"Novelty (Entropy):     {m['novelty_score_bits']:.3f} bits")
        print(f"Explainability Ratio:  {m['explainability_pct']}% with shared features")
        print("-" * 55)
        print(f"Hit Rate @ {args.k}:         {m['hit_rate_at_k'] * 100:.2f}%")
        print(f"Precision @ {args.k}:        {m['precision_at_k'] * 100:.2f}%")
        print(f"Recall @ {args.k}:           {m['recall_at_k'] * 100:.2f}%")
        print(f"NDCG @ {args.k}:             {m['ndcg_at_k']:.4f}")
        print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
