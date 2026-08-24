# VERSION (#62): one string, two stages. An ARG does NOT cross a stage boundary, so each
# FROM re-declares it - the shell and the server are separately baked and can legitimately
# disagree (the PWA caches), which is exactly the thing the UI shows. `dev` is the default
# so a bare `docker build` is honestly unversioned rather than a stale semver; CI passes
# --build-arg APP_VERSION=<steps.meta.outputs.version>.
ARG APP_VERSION=dev

# ---- web build stage (node present only here) ----
# #99: pinned to $BUILDPLATFORM, so a multi-arch build runs `npm ci` + `npm run build` ONCE
# natively instead of once per target under QEMU emulation. Sound because the output is
# static HTML/JS/CSS with no native addon - the COPY --from below is the same bytes either
# way. The runtime stage below is deliberately NOT platform-pinned: it installs
# cryptography, which resolves a per-architecture wheel and must build for the target.
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim@sha256:d649c27dae7ba0137b3cef5dd75baa422c08dc3d9e3fc0c23dfb172dc3cc6436 AS web
ARG APP_VERSION
ENV VITE_APP_VERSION=$APP_VERSION
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
# #62: static/healthz is the same kind of dev fixture - it exists so `vite preview` (which
# serves the built PWA with no API behind it) answers the version probe instead of logging
# a 404 that audit-responsive.mjs counts as an error. In the container the real /healthz
# route is registered before the static mount and would shadow it anyway; drop it so there
# is exactly one answer.
RUN rm -f build/healthz

# ---- python runtime (no node) ----
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a AS runtime
ARG APP_VERSION
WORKDIR /app
COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
# pipeline scripts (run as subprocesses by the runner)
COPY parse.py insights.py dashboard.py export_data.py remind_bills.py fetch_mail.py llm_cats.py web_push.py ./
COPY server/ ./server/
# baked PWA build -> served by StaticFiles
COPY --from=web /web/build ./web_build
ENV DATA_DIR=/data WEB_DIR=/app/web_build PYTHONUNBUFFERED=1 APP_VERSION=$APP_VERSION
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
