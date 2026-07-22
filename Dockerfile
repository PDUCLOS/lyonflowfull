# =============================================================================
# LyonFlowFull — Dockerfile (multi-service)
# =============================================================================
# Image de base commune pour : API, Streamlit
# L'image Airflow utilise son propre Dockerfile (Dockerfile.airflow) basé
# sur apache/airflow:2.9.3.
# =============================================================================

FROM python:3.12-slim

# Locale FR
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgeos-dev \
    libproj-dev \
    libgdal-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libffi-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Créer utilisateur non-root
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

WORKDIR /app

# Install Python deps (cacheable layer)
COPY requirements-base.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements-base.txt

# Copier le code
COPY . .

# Permissions
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000 8501

# Healthcheck par défaut (override dans compose)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# CMD par défaut = None, sera override par docker-compose
CMD ["python", "-c", "print('LyonFlowFull image ready')"]
