FROM oven/bun:1 AS builder

WORKDIR /web

COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile

COPY . .
RUN bun run build

FROM nginxinc/nginx-unprivileged:alpine

USER root
RUN apk upgrade --no-cache

COPY --from=builder --chown=101:101 /web/dist/ /usr/share/nginx/html/

USER 101:101

EXPOSE 8080
