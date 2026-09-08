# Local dev target — what docker-compose runs (hot reload over a bind mount).
# `docker build` with no --target skips straight past this to `production`
# below, so CI's image scan never sees the dev toolchain at all.
FROM node:20-alpine AS dev

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---------------------------------------------------------------------- build

FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ------------------------------------------------------------------- production
#
# The dev target above ships the whole npm toolchain — npm's own bundled
# dependencies (tar, minimatch, sigstore...) and a vendored native compiler
# binary — none of which is ours to patch and all of which showed up as
# Trivy findings once that image got scanned as if it were a production
# artifact. It never was one: the real frontend deploys straight from source
# to Vercel. This stage is what an image tagged `rentflow-frontend` should
# actually contain if anyone ever does ship it — the static build output
# behind a plain web server, nothing else.
FROM nginx:1.27-alpine AS production

# The image's own Alpine packages (openssl, libxml2, zlib...) lag the distro's
# security fixes between nginx's own release cycles; pull current patches at
# build time rather than waiting on the next upstream nginx image bump.
RUN apk update && apk upgrade --no-cache

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/security-headers.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -qO- http://localhost/ || exit 1
