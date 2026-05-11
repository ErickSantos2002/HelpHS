#!/bin/bash
set -e

echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations complete."

echo "Running database seeds..."
python -m app.seeds
echo "Seeds complete."

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
