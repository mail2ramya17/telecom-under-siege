#!/usr/bin/env bash
# Check that every toolchain used in this repo is installed.
set -uo pipefail

missing=0
check() {
  local cmd=$1 why=$2
  if command -v "$cmd" >/dev/null 2>&1; then
    printf '  [ok]      %-18s %s\n' "$cmd" "$why"
  else
    printf '  [missing] %-18s %s\n' "$cmd" "$why"
    missing=$((missing + 1))
  fi
}

echo "Toolchain preflight"
check python3          "video + music rendering"
check ffmpeg           "video encoding and muxing"
check node             "TypeScript attack-path explorer"
check tsc              "TypeScript compiler (npm i -g typescript)"
check javac            "Java CDR exfiltration detector"
check ansible-playbook "render-host / hardening playbooks"

if python3 -c 'import numpy, scipy, PIL' 2>/dev/null; then
  echo "  [ok]      python libs        numpy, scipy, pillow"
else
  echo "  [missing] python libs        pip install numpy scipy pillow"
  missing=$((missing + 1))
fi

if [[ $missing -gt 0 ]]; then
  echo "$missing dependency(ies) missing. Run: ansible-playbook ansible/playbooks/render-host.yml"
  exit 1
fi
echo "All dependencies present."
