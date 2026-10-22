#!/bin/sh
set -e

echo "[CinePhile] Preparing database and sample data..."
python -m app.seed --if-empty

echo "[CinePhile] Starting web server on port 8000..."
# --preload: train the TF-IDF model once, then share it with the worker processes.
exec gunicorn wsgi:app --bind 0.0.0.0:8000 --workers 2 --preload --access-logfile -
