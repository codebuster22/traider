FROM python:3.11-slim

WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Create empty README.md for hatchling build
RUN touch README.md

# Install dependencies
RUN uv sync --no-dev

# Expose port
EXPOSE 8000

# Run the server
CMD ["uv", "run", "traider-server"]
