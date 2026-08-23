# The Operations API, and the image the sweep job runs.
#
# One image for both on purpose. A scheduled verification job running a *different*
# build from the API is a job verifying a system that is not deployed, and the two would
# drift the first time a deploy half-succeeded.

FROM python:3.11-slim AS build

# Build wheels in a stage that can be thrown away, so the runtime image carries no
# compiler and nothing that needs one.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY broker/ broker/
COPY client/ client/
COPY generators/ generators/

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip wheel --no-cache-dir --wheel-dir /wheels .


FROM python:3.11-slim AS runtime

# Migrations run from this image too, so alembic and the migration scripts ship with it.
# The alternative is a second image that must be kept in step with the first, and a
# deploy where they disagree is a deploy that migrates to a schema the API does not
# expect - which is exactly what /api/ready exists to refuse.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 office

WORKDIR /app

COPY --from=build /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl alembic \
    && rm -rf /wheels

COPY alembic.ini ./
COPY db/ db/
COPY packs/ packs/

# Non-root from here down. The API needs no write access to anything in the image; it
# writes to Postgres and to stdout.
USER office

EXPOSE 8080

# Liveness, not readiness. A container whose database is briefly unreachable is not a
# container to restart - restarting it does nothing about the database and turns an
# outage in one system into an outage in two. The compose file wires /api/ready to the
# thing that should actually gate traffic.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/live || exit 1

# 0.0.0.0 because the process is alone in a container; the port is published to the
# compose network only, never to the host - Caddy is the only thing that binds one.
CMD ["python", "-m", "broker", "serve", "--host", "0.0.0.0", "--port", "8080"]
