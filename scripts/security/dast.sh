#!/usr/bin/env bash
# Disposable target only. No argument can select a production URL or Compose project.
set -euo pipefail
mode="${1:-baseline}"
case "$mode" in baseline|active|https) ;; *) echo "Use baseline, active or https" >&2; exit 2 ;; esac
repo="$(cd "$(dirname "$0")/../.." && pwd)"
report_dir="${SPECHELPER_SECURITY_REPORT_DIR:-$repo/.local/security-reports}"
mkdir -p "$report_dir"
report_dir="$(cd "$report_dir" && pwd)"
secret_dir="$(mktemp -d)"
project="spechelper-security-$(date +%s)-$$"
export SPECHELPER_DAST_PASSWORD_FILE="$secret_dir/access-password"
python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > "$SPECHELPER_DAST_PASSWORD_FILE"
chmod 600 "$SPECHELPER_DAST_PASSWORD_FILE"
compose=(docker compose -p "$project" -f "$repo/security/compose.dast.yml")
cleanup() {
  "${compose[@]}" logs --no-color > "$report_dir/target.log" 2>&1 || true
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -f "$SPECHELPER_DAST_PASSWORD_FILE"
  rmdir "$secret_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ "$mode" == https ]]; then
  export SPECHELPER_DAST_REQUIRE_HTTPS=1 SPECHELPER_DAST_TRUST_PROXY=1
  export SPECHELPER_DAST_ORIGINS=https://localhost:8443
fi
"${compose[@]}" up --build -d --wait --wait-timeout 180
network="${project}_scan"
if [[ "$mode" == https ]]; then
  image="$("${compose[@]}" images -q backend)"
  docker run --rm --network "$network" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,nodev,size=32m \
    -v "${project}_scan-auth:/auth:ro" \
    -v "$repo/scripts/security/https_probe.py:/probe.py:ro" \
    "$image" python /probe.py > "$report_dir/https.json"
  exit 0
fi
scan="zap-baseline.py"
if [[ "$mode" == active ]]; then
  scan="zap-full-scan.py"
fi
arguments=("$scan" -t http://frontend:3000 -m 1 -T 6 -c /zap/rules.tsv
  -J "$mode.json" -r "$mode.html" -w "$mode.md"
  --hook /zap/hooks.py -z '-config connection.timeoutInSecs=10')
if [[ "$mode" == baseline ]]; then arguments+=(--autooff); fi
set +e
docker run --rm --network "$network" --user 0:0 \
  --memory 2g --cpus 2 --pids-limit 256 \
  -e SPECHELPER_DAST_MODE="$mode" \
  -v "$report_dir:/zap/wrk:rw" \
  -v "$repo/security/zap-rules.tsv:/zap/rules.tsv:ro" \
  -v "$repo/scripts/security/zap_hooks.py:/zap/hooks.py:ro" \
  -v "$SPECHELPER_DAST_PASSWORD_FILE:/run/secrets/access-password:ro" \
  ghcr.io/zaproxy/zaproxy:2.16.1 "${arguments[@]}"
status=$?
set -e
if [[ ! -s "$report_dir/authentication.json" ]]; then
  echo "Authenticated scan evidence is missing" >&2
  exit 3
fi
# Exit2 records untriaged warnings and stays a failing review gate.
exit "$status"
