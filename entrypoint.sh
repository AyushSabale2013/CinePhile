
#!/bin/sh
set -e

echo "[CinePhile] Preparing database and sample data..."
python -m app.seed --if-empty

PORT="${PORT:-8000}"

echo "[CinePhile] Starting web server on port ${PORT}..."
exec gunicorn wsgi:app \
    --bind "0.0.0.0:${PORT}" \
    --workers 1 \
    --preload \
    --access-logfile -
