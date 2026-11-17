#!/usr/bin/env bash
# SNMP side of the MDT-vs-SNMP bench, on ibk-lab-sw98 only. Runs on the test host (kof-ibk-debian4), not on a laptop.
#   switch-snmp.sh apply    push the read-only SNMPv3 user and the v2c community below (both behind one ACL: test host)
#   switch-snmp.sh remove   take exactly the same config off again (run after the report)
#   switch-snmp.sh show     read back the bench config (no secrets are printed)
#
# Credentials are generated on the first apply into $BENCH_SNMP_ENV (default /home/claude/bench/snmp_env, mode 600).
# They are never printed. Nothing else on the switch is changed.
#
#   scripts/mdthost 'bench/snmp-vs-mdt/switch-snmp.sh apply'     (or run it from /home/claude/bench/snmp-vs-mdt)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
ip=${BENCH_SWITCH:-172.24.80.240}
src=${BENCH_SRC_IP:-172.24.89.69}          # the only source the ACL permits: the test host
envf=${BENCH_SNMP_ENV:-/home/claude/bench/snmp_env}
action=${1:?usage: switch-snmp.sh apply|remove|show}
acl=BENCH-SNMP view=BENCH-VIEW group=BENCH-V3

if [ ! -f "$envf" ]; then
  [ "$action" = apply ] || { echo "no $envf: nothing to $action" >&2; exit 1; }
  umask 077; mkdir -p "$(dirname "$envf")"
  printf 'SNMP_USER=benchsnmp\nSNMP_AUTH_PASS=%s\nSNMP_PRIV_PASS=%s\nSNMP_COMMUNITY=%s\n' \
    "$(openssl rand -hex 12)" "$(openssl rand -hex 12)" "$(openssl rand -hex 8)" > "$envf"
fi
chmod 600 "$envf"
set -a; . "$envf"; set +a

case $action in
apply)
cfg=$(cat <<CLI
terminal length 0
configure terminal
no ip access-list standard $acl
ip access-list standard $acl
 remark bench: SNMP vs MDT measurement, test host only
 10 permit $src
exit
snmp-server view $view iso included
snmp-server group $group v3 priv read $view access $acl
snmp-server group $group v3 priv context vlan- match prefix read $view access $acl
snmp-server user $SNMP_USER $group v3 auth sha $SNMP_AUTH_PASS priv aes 128 $SNMP_PRIV_PASS access $acl
snmp-server community $SNMP_COMMUNITY view $view RO $acl
end
exit
CLI
)
;;
remove)
cfg=$(cat <<CLI
terminal length 0
configure terminal
no snmp-server community $SNMP_COMMUNITY
no snmp-server user $SNMP_USER $group v3
no snmp-server group $group v3 priv context vlan- match prefix
no snmp-server group $group v3 priv
no snmp-server view $view iso
no ip access-list standard $acl
end
exit
CLI
)
;;
show)
cfg=""
;;
*) echo "usage: switch-snmp.sh apply|remove|show" >&2; exit 2;;
esac

# IOS echoes every typed line, and the echo of a password is garbled, so no line filter can hide it. The config
# session output is therefore discarded. What is printed: the switch's view of our user, group and ACL (no secrets).
if [ -n "$cfg" ]; then
  printf '%s\n' "$cfg" | "$here/switch_ssh.sh" "$ip" >/dev/null 2>&1 || { echo "switch session failed ($action)" >&2; exit 1; }
  echo "$action sent to $ip (switch output not shown: it echoes the credentials)"
fi
printf 'terminal length 0\nshow snmp user\nshow snmp group\nshow ip access-lists %s\nexit\n' "$acl" \
  | "$here/switch_ssh.sh" "$ip" 2>/dev/null \
  | grep -i -E -A4 "^(User name: $SNMP_USER|groupname: $group |standard IP access list $acl)" || echo "no BENCH config found on $ip"
