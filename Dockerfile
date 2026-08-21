# ---- web build stage (node present only here) ----
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build   # -> /web/build (vite-pwa SW with NetworkFirst /data/app.json)
# SECURITY (#51): web/static/data/*.json is a LOCAL dev fixture that adapter-static copies
# into build/data/. In the container the real data comes off the PVC through the explicit
# /data/* routes, so a baked copy is at best stale and at worst whatever financial data
# happened to be in the build context - sitting inside the public static mount. Drop it.
RUN rm -rf build/data

# ---- python runtime (no node) ----
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
# pipeline scripts (run as subprocesses by the runner)
COPY parse.py insights.py dashboard.py export_data.py remind_bills.py fetch_mail.py llm_cats.py web_push.py ./
COPY server/ ./server/
# baked PWA build -> served by StaticFiles
COPY --from=web /web/build ./web_build
ENV DATA_DIR=/data WEB_DIR=/app/web_build PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
