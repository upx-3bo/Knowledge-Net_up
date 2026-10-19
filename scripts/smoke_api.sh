#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"

echo "== health =="
curl -sS "$BASE/health"; echo
echo "== stats =="
curl -sS "$BASE/stats"; echo
echo "== schema =="
curl -sS "$BASE/meta/schema"; echo
echo "== list technology =="
curl -sS "$BASE/vertices?tag=technology"; echo
echo "== create tech =="
CREATE=$(curl -sS -X POST "$BASE/vertices" -H "Content-Type: application/json" \
  -d '{"tag":"technology","props":{"name":"API冒烟技术点","description":"由 smoke_api 创建","keywords":"smoke","status":"draft"}}')
echo "$CREATE"
VID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['vid'])" <<<"$CREATE")
echo "VID=$VID"
echo "== get =="
curl -sS "$BASE/vertices/$VID"; echo
echo "== subgraph demo =="
curl -sS "$BASE/subgraph/tech_demo?depth=1"; echo
echo "== relate =="
curl -sS -X POST "$BASE/edges" -H "Content-Type: application/json" \
  -d "{\"edge_type\":\"relates_to\",\"src_vid\":\"$VID\",\"dst_vid\":\"tech_demo\",\"props\":{\"relation_type\":\"smoke\",\"weight\":0.5}}"; echo
echo "== search =="
curl -sS --get "$BASE/vertices" --data-urlencode "keyword=冒烟"; echo
echo "== delete created =="
curl -sS -X DELETE "$BASE/vertices/$VID"; echo
echo "SMOKE API OK"
