#!/usr/bin/env bash
# Read-only exposure audit for a Linux jump host / edge management box.
# Makes no changes. Run with sudo for complete results.
#
# Exit codes: 0 = no FAIL findings, 1 = at least one FAIL.
set -uo pipefail

fails=0; warns=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$*"; }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$*"; warns=$((warns + 1)); }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; fails=$((fails + 1)); }

sshd_value() {
  # Effective value from sshd -T when available, else the config file.
  local key=$1
  if command -v sshd >/dev/null 2>&1 && sshd -T >/dev/null 2>&1; then
    sshd -T 2>/dev/null | awk -v k="$key" 'tolower($1)==tolower(k){print tolower($2); exit}'
  elif [[ -r /etc/ssh/sshd_config ]]; then
    awk -v k="$key" 'tolower($1)==tolower(k){print tolower($2); exit}' /etc/ssh/sshd_config
  fi
}

echo "== SSH configuration"
if [[ -e /etc/ssh/sshd_config ]]; then
  [[ "$(sshd_value PermitRootLogin)" == "no" ]] && pass "Root login disabled" || fail "PermitRootLogin is not 'no'"
  [[ "$(sshd_value PasswordAuthentication)" == "no" ]] && pass "Password authentication disabled" || fail "PasswordAuthentication is not 'no'"
  [[ "$(sshd_value X11Forwarding)" == "no" ]] && pass "X11 forwarding disabled" || warn "X11Forwarding is enabled"
  mat=$(sshd_value MaxAuthTries)
  [[ -n "$mat" && "$mat" -le 4 ]] && pass "MaxAuthTries=$mat" || warn "MaxAuthTries is ${mat:-default} (recommend <= 4)"
else
  pass "No SSH server installed"
fi

echo "== Listening services"
if command -v ss >/dev/null 2>&1; then
  public=$(ss -H -tulpn 2>/dev/null | awk '{print $5}' | grep -Ev '^(127\.|\[::1\]|::1)' || true)
  count=$(printf '%s\n' "$public" | grep -c . || true)
  if [[ "$count" -eq 0 ]]; then
    pass "No services listening on non-loopback addresses"
  else
    warn "$count service(s) listening on non-loopback addresses:"
    # shellcheck disable=SC2086  # split one address per line
    printf '        %s\n' $public
  fi
  for risky in ':23$' ':21$' ':161$' ':2049$'; do
    printf '%s\n' "$public" | grep -Eq "$risky" && fail "Legacy/cleartext service exposed on port ${risky//[:$]/}"
  done
else
  warn "'ss' not available; skipped port check"
fi

echo "== Patching"
if command -v apt-get >/dev/null 2>&1; then
  n=$(apt-get -s upgrade 2>/dev/null | grep -c '^Inst' || true)
  sec=$(apt-get -s upgrade 2>/dev/null | grep '^Inst' | grep -ci security || true)
  [[ "$sec" -gt 0 ]] && fail "$sec pending security update(s) ($n total)" || pass "No pending security updates ($n other updates)"
elif command -v dnf >/dev/null 2>&1; then
  sec=$(dnf -q updateinfo list --security 2>/dev/null | wc -l)
  [[ "$sec" -gt 0 ]] && fail "$sec pending security update(s)" || pass "No pending security updates"
else
  warn "Unknown package manager; skipped patch check"
fi

echo "== Accounts and files"
uid0=$(awk -F: '$3==0{print $1}' /etc/passwd | grep -vx root || true)
[[ -z "$uid0" ]] && pass "Only root has UID 0" || fail "Extra UID 0 account(s): $uid0"
if [[ -r /etc/shadow ]]; then
  empty=$(awk -F: '$2==""{print $1}' /etc/shadow)
  [[ -z "$empty" ]] && pass "No accounts with empty passwords" || fail "Empty password: $empty"
else
  warn "Cannot read /etc/shadow (run with sudo)"
fi
ww=$(find /etc -xdev -type f -perm -0002 2>/dev/null | head -5)
[[ -z "$ww" ]] && pass "No world-writable files in /etc" || fail "World-writable files in /etc: $ww"

echo "== Logging"
if systemctl is-active --quiet auditd 2>/dev/null; then pass "auditd running"; else warn "auditd not running"; fi

echo
echo "Summary: $fails FAIL, $warns WARN"
[[ $fails -eq 0 ]]
