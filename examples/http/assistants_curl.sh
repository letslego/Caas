#!/usr/bin/env bash
# HTTP samples: personal / team / organization assistant read+write.
# Prerequisites:
#   export CAAS_UNSAFE_DEV_HEADERS=1
#   export CAAS_DATABASE_URL=postgresql://caas:caas@127.0.0.1:5432/caas   # optional
#   caas-api --host 127.0.0.1 --port 8080
# Usage: bash examples/http/assistants_curl.sh
set -euo pipefail

BASE="${CAAS_BASE_URL:-http://127.0.0.1:8080}"
H_ALICE=(-H "X-Verified-Tenant: acme" -H "X-Verified-Subject: alice" -H "X-Verified-Groups: platform" -H "Content-Type: application/json")
H_BOB=(-H "X-Verified-Tenant: acme" -H "X-Verified-Subject: bob" -H "X-Verified-Groups: platform" -H "Content-Type: application/json")
H_SAM=(-H "X-Verified-Tenant: acme" -H "X-Verified-Subject: sam" -H "X-Verified-Groups: security,platform" -H "Content-Type: application/json")

echo "== health =="
curl -sS "$BASE/healthz" | tee /tmp/caas-health.json
echo

echo "== PERSONAL: create scope + write + read =="
curl -sS -X POST "$BASE/v1/scopes" "${H_ALICE[@]}" \
  -d '{"kind":"personal","scope_id":"alice"}' || true
PERSONAL=$(curl -sS -X POST "$BASE/v1/memories" "${H_ALICE[@]}" \
  -d '{"kind":"personal","scope_id":"alice","content":"Prefers short design reviews","source":"conversation","memory_type":"preference"}')
echo "$PERSONAL"
curl -sS -X POST "$BASE/v1/context:retrieve" "${H_ALICE[@]}" \
  -d '{"query":"design reviews","scopes":[["personal","alice"]],"mode":"hybrid"}'
echo
echo "== PERSONAL isolation: bob should see empty =="
curl -sS -X POST "$BASE/v1/context:retrieve" "${H_BOB[@]}" \
  -d '{"query":"design reviews","scopes":[["personal","alice"]]}'
echo

echo "== TEAM: scope, grants, write, read =="
curl -sS -X POST "$BASE/v1/scopes" "${H_ALICE[@]}" \
  -d '{"kind":"team","scope_id":"platform"}' || true
curl -sS -X POST "$BASE/v1/grants" "${H_ALICE[@]}" \
  -d '{"kind":"team","scope_id":"platform","subject":"group:platform","permission":"read"}'
curl -sS -X POST "$BASE/v1/grants" "${H_ALICE[@]}" \
  -d '{"kind":"team","scope_id":"platform","subject":"user:alice","permission":"write"}'
TEAM=$(curl -sS -X POST "$BASE/v1/memories" "${H_ALICE[@]}" \
  -d '{"kind":"team","scope_id":"platform","content":"Platform review is Thursdays for Orion","source":"meeting"}')
echo "$TEAM"
curl -sS -X POST "$BASE/v1/admin/outbox:drain" "${H_ALICE[@]}" || true
curl -sS -X POST "$BASE/v1/context:retrieve" "${H_BOB[@]}" \
  -d '{"query":"Orion Thursday","scopes":[["team","platform"]],"mode":"hybrid"}'
echo

echo "== ORGANIZATION: confidential policy write/read =="
curl -sS -X POST "$BASE/v1/scopes" "${H_SAM[@]}" \
  -d '{"kind":"organization","scope_id":"acme-corp","classification":"confidential"}' || true
curl -sS -X POST "$BASE/v1/grants" "${H_SAM[@]}" \
  -d '{"kind":"organization","scope_id":"acme-corp","subject":"group:platform","permission":"read"}'
curl -sS -X POST "$BASE/v1/grants" "${H_SAM[@]}" \
  -d '{"kind":"organization","scope_id":"acme-corp","subject":"user:sam","permission":"write"}'
curl -sS -X POST "$BASE/v1/memories" "${H_SAM[@]}" \
  -d '{"kind":"organization","scope_id":"acme-corp","content":"Production CaaS must use OIDC identity","source":"security-review","classification":"confidential","memory_type":"policy"}'
echo
# Note: alice default clearance is internal; confidential org rows require sufficient clearance.
curl -sS -X POST "$BASE/v1/context:retrieve" "${H_SAM[@]}" \
  -d '{"query":"OIDC identity","scopes":[["organization","acme-corp"]]}'
echo

echo "== GRAPH relate + path (Postgres only) =="
curl -sS -X POST "$BASE/v1/graph/relate" "${H_ALICE[@]}" \
  -d '{"src_label":"Orion","relation":"reviewed_on","dst_label":"Thursdays"}' || true
curl -sS -X POST "$BASE/v1/graph/path" "${H_ALICE[@]}" \
  -d '{"src_label":"Orion","dst_label":"Thursdays"}' || true
echo
echo "Done."
