# syntax=docker/dockerfile:1.7

# Stage 1: build the Next.js static export
FROM node:20-slim AS frontend-build
WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# Stage 2: install backend dependencies with uv and assemble runtime image
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    PATH=/app/backend/.venv/bin:$PATH

# uv installs into /usr/local/bin
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY backend/pyproject.toml backend/uv.lock /app/backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev --no-install-project

# Copy backend source
COPY backend/ /app/backend/

# Install the project itself now that the source is present
RUN uv sync --frozen --no-dev

# Copy frontend static export into the location FastAPI serves from
COPY --from=frontend-build /build/frontend/out /app/backend/static

# SQLite database lives in /app/db (volume-mounted in production)
RUN mkdir -p /app/db

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
