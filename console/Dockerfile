# The console. Next.js standalone output, non-root.
#
# The console is a server, not a static bundle, and that is load-bearing: every API call
# happens server-side so the bearer token never reaches the browser. A static export
# would move the token into JavaScript and take CORS with it.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci


FROM node:20-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# OFFICE_API_URL is read at request time, not baked in, so one image runs in staging and
# production. Nothing secret is available at build time and nothing secret is needed:
# the bearer token arrives per-request in a cookie.
RUN npm run build


FROM node:20-slim AS runtime
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
USER node

# `output: "standalone"` traces exactly the files the server needs, so this stage
# carries no node_modules tree and no build toolchain.
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public

EXPOSE 3000

# /login renders without a session, which makes it the one page that proves the server
# is answering rather than that it merely accepted a connection.
HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/login || exit 1

CMD ["node", "server.js"]
