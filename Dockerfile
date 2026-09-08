# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN addgroup --system arbiter && adduser --system --ingroup arbiter arbiter
COPY backend/requirements.txt backend/requirements-production.txt /app/backend/
RUN pip install -r /app/backend/requirements-production.txt
COPY backend/ /app/backend/
COPY --from=frontend /src/backend/dist /app/backend/dist
COPY scripts/ /app/scripts/
COPY *.md /app/
RUN chown -R arbiter:arbiter /app
USER arbiter
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers"]
