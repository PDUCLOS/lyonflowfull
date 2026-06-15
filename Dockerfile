# =============================================================================
# LyonFlowFull — Dockerfile (multi-service) — SLIM
# =============================================================================
# Image de base commune pour : API, Streamlit
# =============================================================================
# Sprint P2-ter (2026-06-15) — Allègement:
#   - Retrait de build-essential, libgdal-dev, libpango, libcairo2, libffi-dev
#     (1 GB de deps apt) car weasyprint + geopandas retirés des deps Python.
#   - requirements-base-light.txt (~25 deps) au lieu de requirements.txt
#     monolithique (~99 deps).
#   - Image streamlit cible : 14.3 GB → 2-3 GB.
# =============================================================================

FROM python:3.12-slim

# Locale FR
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Deps système minimales — uniquement ce qu'il faut pour psycopg2-binary
# (libpq-dev) et compiler les wheels pip si nécessaire (build-essential + gcc).
# geopandas/gdal/pango/cairo retirés (pas utilisés en runtime api+streamlit).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Créer utilisateur non-root
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

WORKDIR /app

# Install Python deps (cacheable layer)
COPY requirements-base-light.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements-base-light.txt

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
