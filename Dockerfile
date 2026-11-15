FROM node:22.16.0-alpine AS frontend
WORKDIR /frontend
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.8.17 AS uv
FROM python:3.12.11-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    PATH="/app/.venv/bin:$PATH" MPLCONFIGDIR=/tmp/jupiter-matplotlib \
    SERVE_WEB=1 SECURE_COOKIES=1 PRIVATE_STORAGE=/private
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project \
    && playwright install --with-deps chromium \
    && python -c "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); Path('/usr/local/bin/chromium').symlink_to(p.chromium.executable_path); p.stop()" \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV BROWSER_PATH=/usr/local/bin/chromium
COPY backend/ backend/
COPY scripts/power.py scripts/power.py
COPY data/reference/ data/reference/
COPY web/public/favicon.svg web/public/favicon.svg
COPY --from=frontend /frontend/dist web/dist
EXPOSE 10000
CMD ["python", "-m", "jupiter.hosted"]
