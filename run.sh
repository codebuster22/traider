#!/bin/bash
# Run script for the Fabric Inventory Service using UV
# Usage: ./run.sh

# Default values
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export RELOAD="${RELOAD:-true}"

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL environment variable is not set"
    echo "Example: export DATABASE_URL=postgresql://user:pass@localhost:5432/inventory"
    exit 1
fi

# Run the FastAPI application using UV
uv run traider-server
