# ---- web build stage (node present only here) ----
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build   # -> /web/build (vite-pwa SW with NetworkFirst /data/app.json)

# ---- python runtime (no node) ----
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
# pipeline scripts (run as subprocesses by the runner)
COPY parse.py insights.py dashboard.py export_data.py ./
COPY server/ ./server/
# baked PWA build -> served by StaticFiles
COPY --from=web /web/build ./web_build
ENV DATA_DIR=/data WEB_DIR=/app/web_build PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
