#!/bin/bash
# Simple run script for the Fabric Inventory Service
# Usage: ./run.sh

# Default values
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL environment variable is not set"
    echo "Example: export DATABASE_URL=postgresql://user:pass@localhost:5432/inventory"
    exit 1
fi

# Run the FastAPI application
uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
