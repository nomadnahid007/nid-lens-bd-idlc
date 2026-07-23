#!/usr/bin/env bash
# End-to-end smoke test for NID Lens BD. Assumes the API is already running
# (e.g. `docker compose up`) and reachable at BASE_URL.
#
# Usage: BASE_URL=http://localhost:8000 ./scripts/smoke_test.sh
#
# The documented, deterministic way to run this is against a container in
# demo mode (APP_MODE=demo, the default) — that path has zero external
# dependencies and will always pass. If the container is in live mode, the
# full-extraction check depends on Gemini actually being reachable; a
# PROVIDER_UNAVAILABLE response there is reported as a WARN, not a FAIL,
# since it reflects external network/API conditions, not a defect in this
# codebase — any other unexpected response in live mode still fails loudly.

set -u

BASE_URL="${BASE_URL:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLES_DIR="$SCRIPT_DIR/../fixtures/samples"
FRONT="$SAMPLES_DIR/nid_front_synthetic.png"
BACK="$SAMPLES_DIR/nid_back_synthetic.png"

# On Git Bash for Windows, curl is typically a native mingw-w64 build that
# can't read POSIX-style (/c/...) paths for local file uploads — convert to
# a Windows path when cygpath is available; no-op on real POSIX systems.
to_curl_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s' "$1"
  fi
}

CURL_FRONT="$(to_curl_path "$FRONT")"
CURL_BACK="$(to_curl_path "$BACK")"

PASS=0
FAIL=0
WARN=0

check() {
  local name="$1"
  local expected_code="$2"
  local actual_code="$3"
  local body_check="${4:-}"
  local body="${5:-}"

  if [ "$actual_code" != "$expected_code" ]; then
    echo "FAIL  $name (expected HTTP $expected_code, got $actual_code)"
    FAIL=$((FAIL + 1))
    return
  fi

  if [ -n "$body_check" ] && ! grep -q "$body_check" <<<"$body"; then
    echo "FAIL  $name (HTTP $actual_code OK, but response missing '$body_check')"
    FAIL=$((FAIL + 1))
    return
  fi

  echo "PASS  $name (HTTP $actual_code)"
  PASS=$((PASS + 1))
}

warn() {
  echo "WARN  $1"
  WARN=$((WARN + 1))
}

echo "NID Lens BD smoke test — target: $BASE_URL"
echo

if [ ! -f "$FRONT" ] || [ ! -f "$BACK" ]; then
  echo "Sample images not found at $SAMPLES_DIR."
  echo "Run: python scripts/generate_samples.py"
  exit 1
fi

# 1. Health check
body=$(curl -s -w '\n%{http_code}' "$BASE_URL/health")
code=$(tail -n1 <<<"$body")
resp=$(sed '$d' <<<"$body")
check "GET /health" "200" "$code" '"status"' "$resp"

mode=$(grep -o '"mode":"[a-z]*"' <<<"$resp" | sed -E 's/"mode":"([a-z]*)"/\1/')
echo "  (detected mode: ${mode:-unknown})"

# 2. Full extraction, both images present
body=$(curl -s -w '\n%{http_code}' -X POST "$BASE_URL/api/v1/nid/extract" \
  -F "front=@${CURL_FRONT};type=image/png" \
  -F "back=@${CURL_BACK};type=image/png")
code=$(tail -n1 <<<"$body")
resp=$(sed '$d' <<<"$body")

if [ "$mode" = "live" ] && [ "$code" = "503" ] && grep -q '"code":"PROVIDER_UNAVAILABLE"' <<<"$resp"; then
  warn "POST /api/v1/nid/extract (full) — live mode, Gemini unreachable (network/quota/key issue, not a code defect): $resp"
elif [ "$mode" = "demo" ]; then
  check "POST /api/v1/nid/extract (full)" "200" "$code" '"status":"complete"' "$resp"
else
  check "POST /api/v1/nid/extract (full)" "200" "$code" '"status"' "$resp"
fi

# 3. Missing back image -> 422
body=$(curl -s -w '\n%{http_code}' -X POST "$BASE_URL/api/v1/nid/extract" \
  -F "front=@${CURL_FRONT};type=image/png")
code=$(tail -n1 <<<"$body")
resp=$(sed '$d' <<<"$body")
check "POST /api/v1/nid/extract (missing back)" "422" "$code" '' "$resp"

# 4. Sample image routes used by the UI
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/v1/samples/front")
check "GET /api/v1/samples/front" "200" "$code"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/v1/samples/back")
check "GET /api/v1/samples/back" "200" "$code"

echo
echo "Results: $PASS passed, $FAIL failed, $WARN warned"
[ "$FAIL" -eq 0 ]
