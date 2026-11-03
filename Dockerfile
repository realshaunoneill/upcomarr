# syntax=docker/dockerfile:1
# upcomarr generator: holds the arr API keys, renders the static site into /out.
FROM python:3.13.18-alpine3.24@sha256:7984cf56ceaddebe4fefeb75d64000b9f45d8b77b11a09b24524da6cdc3af0c8

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    OUT_DIR=/out

WORKDIR /app
COPY src/upcomarr ./upcomarr

# zoneinfo has no fallback if the tz database is missing, so prove it is there.
# /out is owned by the image's user so a fresh named volume is writable.
RUN python -c "import zoneinfo; [zoneinfo.ZoneInfo(z) for z in ('Europe/Dublin', 'America/Los_Angeles', 'Australia/Sydney')]" \
 && python -m compileall -q upcomarr \
 && mkdir -p /out \
 && chown 10001:10001 /out

USER 10001:10001
EXPOSE 9708
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD ["python", "-m", "upcomarr", "healthcheck"]
ENTRYPOINT ["python", "-m", "upcomarr"]
CMD ["run"]
