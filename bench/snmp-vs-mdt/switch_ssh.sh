#!/usr/bin/env bash
# Runs IOS-XE CLI on one switch, from the test host: commands on stdin, end with exit. The SSH is the one scripts/swcli
# uses, minus the outer hop (this script already runs on the test host). Credentials: /opt/gnmic/gnmic_env, read only.
#   switch_ssh.sh <switch ip> < commands
set -euo pipefail
ip=${1:?usage: switch_ssh.sh <switch ip> < commands}
[[ $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not an IP address: $ip" >&2; exit 2; }
export LC_ALL=C
set -a; . /opt/gnmic/gnmic_env; set +a
ap=$(mktemp); trap 'rm -f "$ap"' EXIT
printf '#!/bin/sh\necho "$SWITCH_PASSWORD"\n' > "$ap"; chmod 700 "$ap"
SSH_ASKPASS=$ap SSH_ASKPASS_REQUIRE=force DISPLAY=x setsid -w ssh -T -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=15 -o KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group-exchange-sha1 \
  -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAuthentication=no "$SWITCH_USERNAME@$ip" \
  2> >(grep -v -E 'setlocale|Warning: Permanently' >&2)
