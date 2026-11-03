# syntax=docker/dockerfile:1
# upcomarr-web: serves the generator's output read-only. It holds no key and needs no network
# access of its own; only whatever fronts it (a tunnel, a reverse proxy) needs to reach it.
FROM nginxinc/nginx-unprivileged:1.31.7-alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e

COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/headers.conf /etc/nginx/upcomarr/headers.conf
RUN nginx -t

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/_status.json || exit 1
# Run nginx directly: the base image's entrypoint scripts rewrite files under /etc/nginx,
# which a read-only root filesystem does not allow.
ENTRYPOINT ["nginx", "-g", "daemon off;"]
