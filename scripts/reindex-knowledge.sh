#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

curl -s -X POST "${API_BASE_URL}/api/knowledge/reindex"
echo
