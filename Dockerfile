# ---------- Stage 1: build the React frontend ----------
FROM node:22-alpine AS frontend
ARG APP_VERSION=dev
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_APP_VERSION=$APP_VERSION
RUN npm run build

# ---------- Stage 2: Python API serving the built frontend ----------
FROM python:3.12-slim AS runtime
ARG APP_VERSION=dev
ARG BUILD_TIME=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_VERSION=$APP_VERSION \
    BUILD_TIME=$BUILD_TIME \
    DATABASE_URL=sqlite:////data/family.db

WORKDIR /app

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/app /app/app
RUN pip install --no-cache-dir . && mkdir -p /data

COPY --from=frontend /build/dist /app/static
COPY docs /app/docs
COPY VERSION /app/VERSION

EXPOSE 8080
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
