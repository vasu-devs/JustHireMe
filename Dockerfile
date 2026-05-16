FROM python:3.11-slim

# Install weasyprint + system deps (PDF rendering)
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
    libffi-dev shared-mime-info fonts-liberation && rm -rf /var/lib/apt/lists/*

# Install uv for fast, efficient package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY backend/ ./backend/

ENV JHM_APP_DATA_DIR=/data/justhireme
ENV PYTHONPATH=/app/backend

EXPOSE 3006

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3006"]
