#!/usr/bin/env bash
set -euo pipefail

BASE="http://localhost:8210"

echo "=== [1/4] demo/status ==="
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
curl --noproxy '*' -sf "$BASE/demo/status" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('llm_model:', d.get('llm_model'))
print('llm_max_tokens:', d.get('llm_max_tokens'))
print('embed_backend:', d.get('embed_backend'))
print('openai_api_key_set:', d.get('openai_api_key_set'))
assert d.get('llm_model') == 'MiniMax-M2.5', 'FAIL: wrong model'
assert d.get('openai_api_key_set') == True, 'FAIL: OPENAI_API_KEY not set'
assert d.get('embed_backend') == 'local', 'FAIL: EMBED_BACKEND is not local'
print('PASS')
"

echo "=== [2/4] embed + CN→EN translation ==="
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
curl --noproxy '*' -sf -X POST "$BASE/user_api" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo_user_004","query":"心理悬疑惊悚小说","session_id":"hc-embed","constraints":{"scenario":"cold_start","top_k":1}}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
sq = d.get('intent', {}).get('search_query', '')
print('search_query:', sq)
assert sq, 'FAIL: empty search_query'
assert not any('\u4e00' <= c <= '\u9fff' for c in sq), f'FAIL: Chinese in search_query: {sq}'
em = (d.get('partner_results', {}).get('engine', {}) or {}).get('engine_meta', {}) or {}
print('embed_meta:', em)
print('PASS')
"

echo "=== [3/4] recommendation quality ==="
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
curl --noproxy '*' -sf -X POST "$BASE/user_api" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo_user_002","query":"犯罪推理刑侦小说","session_id":"hc-quality","constraints":{"scenario":"warm","top_k":3}}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
recs = d.get('recommendations', [])
assert len(recs) >= 1, 'FAIL: no recommendations'
for r in recs:
    j = r.get('justification', '')
    src = r.get('source', '')
    print(f'rank={r.get(\"rank\")} source={src} len={len(j)}')
    print(f'  title: {r.get(\"title_display\", \"\")[:60]}')
    print(f'  justification[:80]: {j[:80]}')
    assert '根据您的偏好' not in j, 'FAIL: template prefix found'
    assert len(j) >= 60, f'FAIL: justification too short ({len(j)} chars)'
print('PASS')
"

echo "=== [4/4] profile api ==="
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
curl --noproxy '*' -sf "$BASE/api/profile?user_id=demo_user_002" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('confidence:', d.get('confidence'))
print('behavior_genres:', d.get('behavior_genres'))
assert d.get('user_id') == 'demo_user_002', 'FAIL: wrong user_id'
print('PASS')
"

echo ""
echo "=== ALL CHECKS PASSED ==="
