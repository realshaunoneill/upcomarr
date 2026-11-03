#!/usr/bin/env bash
# Container smoke test: fake arrs, the generator once, then the web image, all hardened the
# way compose.yaml runs them, checked from inside their network.
#
#   tests/smoke.sh <generator image> <web image>
set -euo pipefail

gen=$1
web=$2
id="upcomarr-smoke-$$"
here=$(cd "$(dirname "$0")" && pwd)

cleanup() {
  docker rm -f "$id-fake" "$id-web" >/dev/null 2>&1 || true
  docker volume rm "$id" >/dev/null 2>&1 || true
  docker network rm "$id" >/dev/null 2>&1 || true
}
trap cleanup EXIT

hardened=(--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true)

docker network create "$id" >/dev/null
docker volume create "$id" >/dev/null

# The fake arrs run from the generator image (it has Python) with the tests mounted.
docker run -d --name "$id-fake" --network "$id" "${hardened[@]}" \
  -v "$here:/app/tests:ro" --entrypoint python "$gen" -m tests.serve_fake >/dev/null
for _ in $(seq 1 30); do
  docker logs "$id-fake" 2>&1 | grep -q "fake arrs up" && break
  sleep 1
done

key=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import fixtures; print(fixtures.API_KEY)' "$here")
other=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import fixtures; print(fixtures.OTHER_KEY)' "$here")

docker run --rm --network "$id" "${hardened[@]}" -v "$id:/out" \
  -e SONARR_URL="http://$id-fake:8989" -e SONARR_API_KEY="$key" \
  -e RADARR_URL="http://$id-fake:7878" -e RADARR_API_KEY="$other" \
  -e TZ=Europe/Dublin "$gen" once

docker run -d --name "$id-web" --network "$id" "${hardened[@]}" -v "$id:/srv/site:ro" "$web" >/dev/null
# The image's own HEALTHCHECK command, run by hand: Docker's first check waits a full interval.
for _ in $(seq 1 30); do
  docker exec "$id-web" sh -c 'wget -q -O /dev/null http://127.0.0.1:8080/_status.json' && break
  sleep 1
done
docker exec "$id-web" sh -c 'wget -q -O /dev/null http://127.0.0.1:8080/_status.json' && echo "ok   web healthcheck passes"

docker run --rm --network "$id" "${hardened[@]}" -v "$here:/app/tests:ro" -v "$id:/site:ro" \
  --entrypoint python "$gen" -m tests.smoke_check "http://$id-web:8080" /site
