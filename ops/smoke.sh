#!/usr/bin/env bash
set -euo pipefail

compose="docker compose -f ops/docker-compose.yml"

echo "===> Checking core health"
$compose exec -T api curl -sSf http://localhost:8080/health >/dev/null && echo "OK /health"

echo "===> Listing extensions"
$compose exec -T api curl -sSf http://localhost:8080/extensions | jq 'map(.id)'

echo "===> Lazy-load webui"
code=$($compose exec -T api sh -lc "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ext/webui/")
echo "webui first hit: $code"
$compose exec -T api curl -sSf http://localhost:8080/ext/webui/ >/dev/null && echo "webui mounted"

echo "===> Lazy-load mcp_http"
code=$($compose exec -T api sh -lc "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ext/mcp_http/meta")
echo "mcp first hit: $code"
$compose exec -T api curl -sSf http://localhost:8080/ext/mcp_http/meta | jq '.server'

echo "===> Metrics endpoint"
$compose exec -T api curl -sSf http://localhost:8080/metrics | head -n 5
$compose exec -T api curl -sSf http://localhost:8080/ext/observability/metrics | head -n 3

echo "===> Events demo (requires Redis)"
set +e
$compose exec -T api sh -lc "curl -sSf -X POST http://localhost:8080/ext/events_demo/publish/test?ns=custom -H 'Content-Type: application/json' -d '{}'" && echo "published"
$compose exec -T api curl -sSf "http://localhost:8080/extensions/events_demo/events/health?namespace=custom" | jq '.streams|keys' && echo "events health OK"
set -e

echo "===> Smoke complete"
