#!/bin/bash
# Start Celery worker in the background
celery -A app.worker.celery_app worker --pool=solo --loglevel=info &

# Start Uvicorn in the foreground (PORT environment variable is supplied by Render/Railway/Koyeb)
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
