# Parcel Reconciliation Console (SIH26013): one-command run
#   docker compose up --build      ->  http://localhost:8000
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# geopandas/pyogrio, shapely, pyproj and rasterio ship manylinux wheels with GDAL/GEOS/PROJ inside,
# so no system GIS packages are needed. libgomp is for XGBoost.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY config ./config
COPY src ./src
COPY scripts ./scripts
COPY ui ./ui
# prebuilt results (synthetic benchmark, real T. Nagar comparison, matcher); state files are created on first run
COPY demo ./demo

RUN useradd --create-home --uid 1000 recon && chown -R recon:recon /app
USER recon

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
CMD ["python", "scripts/serve.py", "--host", "0.0.0.0", "--port", "8000"]
