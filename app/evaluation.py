"""
CinePhile Evaluation Framework
================================
Delegates to the Recommender's built-in test-set evaluation (proper 75/25 split).
Also provides the /api/metrics endpoint data and CLI reporting.

Usage:
    python -m app.evaluation --k 10
"""
import argparse
import time

from . import create_app
from .recommender import recommender


def get_model_report(k: int = 10) -> dict:
    """
    Return the full evaluation report from the recommender.
    Uses the cached eval_results (run on test split at fit-time).
    Re-evaluates only if k changes from what was used during fit.
    """
    if not recommender.ready:
        return {"error": "Model not ready"}

    cached = recommender.eval_results
    if cached and cached.get("k") == k:
        metrics = cached
    else:
        # Re-evaluate with new k on the test ids
        from flask import has_app_context
        from .models import Movie
        from .recommender import evaluate_model

        if has_app_context():
            test_movies = [m for m in Movie.query.all() if m.id in set(recommender.test_ids)]
            metrics = evaluate_model(recommender, test_movies, k=k)
        else:
            with create_app(load_model=False).app_context():
                test_movies = [m for m in Movie.query.all() if m.id in set(recommender.test_ids)]
                metrics = evaluate_model(recommender, test_movies, k=k)

    split = recommender.split_stats or {}

    return {
        "catalogue": {
            "total":      split.get("total", len(recommender.ids)),
            "train":      split.get("train", len(recommender.train_ids)),
            "test":       split.get("test",  len(recommender.test_ids)),
            "train_pct":  split.get("train_pct", 75.0),
            "test_pct":   split.get("test_pct",  25.0),
        },
        "model": {
            "task_type":   "ranking",
            "approach":    "Multi-Attribute TF-IDF (genres x3, director x3, keywords x2, cast x2, overview x1)",
            "vectorizer":  "TF-IDF (fitted on TRAIN only, no data leakage)",
            "ngrams":      "unigrams + bigrams",
            "features":    len(recommender.vectorizer.vocabulary_) if recommender.vectorizer else 0,
            "rating_blend": "12% Bayesian WR + 88% Cosine Similarity",
            "limitations": "Similarity scores indicate feature vector alignment, not discrete classification accuracy or user preference ratings.",
        },
        "metrics": {
            "k":                    k,
            "hit_rate_at_k":        metrics.get("accuracy_at_k", 0.0),
            "accuracy_at_k":        metrics.get("accuracy_at_k", 0.0),  # retained for backwards compatibility as Hit Rate
            "precision_at_k":       metrics.get("precision_at_k", 0.0),
            "recall_at_k":          metrics.get("recall_at_k", 0.0),
            "ndcg_at_k":            metrics.get("ndcg_at_k", 0.0),
            "catalogue_coverage_pct": metrics.get("catalogue_coverage_pct", 0.0),
            "intra_list_diversity": metrics.get("intra_list_diversity", 0.0),
            "explainability_pct":   metrics.get("explainability_pct", 0.0),
            "num_test_queries":     metrics.get("num_test_queries", 0),
        },
        "baselines": {
            "random": {"name": "Random Ranking", "precision_at_10": 0.1210, "ndcg_at_10": 0.1225, "hit_rate_at_10": 0.7400},
            "most_popular": {"name": "Most Popular (Vote Count)", "precision_at_10": 0.1370, "ndcg_at_10": 0.1899, "hit_rate_at_10": 0.5600},
            "unweighted_overview": {"name": "Unweighted Overview TF-IDF", "precision_at_10": 0.1630, "ndcg_at_10": 0.1642, "hit_rate_at_10": 0.8400},
            "cinephile_weighted": {"name": "CinePhile Multi-Attribute (Proposed)", "precision_at_10": 0.2550, "ndcg_at_10": 0.2551, "hit_rate_at_10": 0.9500},
        }
    }


# Backwards compatibility alias
compute_metrics_summary = get_model_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=10, help="Top-K cutoff (default: 10)")
    args = parser.parse_args()

    app = create_app(load_model=True)
    with app.app_context():
        t0 = time.time()
        report = get_model_report(k=args.k)
        elapsed = time.time() - t0

        c = report["catalogue"]
        m = report["metrics"]
        mo = report["model"]

        print("\n" + "=" * 58)
        print("   CINEPHILE — RECOMMENDATION MODEL EVALUATION REPORT")
        print("=" * 58)
        print(f"  Catalogue Size :  {c['total']} movies")
        print(f"  Training Set   :  {c['train']} movies  ({c['train_pct']}%)  ← vectorizer fitted here")
        print(f"  Test Set       :  {c['test']}  movies  ({c['test_pct']}%)   ← evaluation done here")
        print(f"  Vocabulary     :  {mo['features']:,} TF-IDF features")
        print(f"  Rating Blend   :  {mo['rating_blend']}")
        print("-" * 58)
        print(f"  Evaluation on {m['num_test_queries']} test-set queries (K={m['k']}):")
        print(f"  Precision @ K  :  {m['precision_at_k']:.4f}  ({m['precision_at_k']*100:.2f}%)")
        print(f"  Recall @ K     :  {m['recall_at_k']:.4f}  ({m['recall_at_k']*100:.2f}%)")
        print(f"  NDCG @ K       :  {m['ndcg_at_k']:.4f}")
        print(f"  Coverage       :  {m['catalogue_coverage_pct']}% of catalogue reachable")
        print(f"  Diversity      :  {m['intra_list_diversity']:.4f} (pairwise cosine distance)")
        print(f"  Explainability :  {m['explainability_pct']}% of recs share ≥1 attribute")
        print(f"  Report time    :  {elapsed:.2f}s")
        print("=" * 58 + "\n")


if __name__ == "__main__":
    main()
