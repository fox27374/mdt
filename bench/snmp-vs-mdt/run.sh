#!/usr/bin/env bash
# MDT-vs-SNMP bench for ibk-lab-sw98. Runs ON THE TEST HOST, detached (see README). Phases run one after another:
#   baseline   MDT only: NATS tap, switch CPU sampler, wire capture, collector stats
#   snmp       the same, plus the SNMPv3 poller (one walk per MDT subscription at its interval)
#   snmp-v2c   optional side run (--v2c): the same with the v2c community
# Output: $BENCH_RUNS/<timestamp>/<phase>/{phase,nats,cpu,wire,podman,walks}.jsonl, then summary.json/summary.txt.
#
#   run.sh [--baseline-min N] [--snmp-min N] [--v2c] [--v2c-min N]      minutes default 60 each
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
switch=${BENCH_SWITCH:-172.24.80.240}
envf=${BENCH_SNMP_ENV:-/home/claude/bench/snmp_env}
runs=${BENCH_RUNS:-/home/claude/bench/runs}
image=bench-snmp-poller:latest
base_min=60 snmp_min=60 v2c=0 v2c_min=""
while [ $# -gt 0 ]; do
  case $1 in
    --baseline-min) base_min=$2; shift 2 ;;
    --snmp-min) snmp_min=$2; shift 2 ;;
    --v2c) v2c=1; shift ;;
    --v2c-min) v2c_min=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
v2c_min=${v2c_min:-$snmp_min}
for n in "$base_min" "$snmp_min" "$v2c_min"; do
  [[ $n =~ ^[1-9][0-9]*$ ]] || { echo "minutes must be a positive integer: $n" >&2; exit 2; }
done

run="$runs/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run"
exec >>"$run/run.log" 2>&1
echo "run dir: $run"
iface=$(ip -o route get "$switch" | sed -n 's/.* dev \([^ ]*\).*/\1/p')
echo "switch $switch via $iface"
podman build -q --network host -t "$image" "$here"

printf '{"switch":"%s","baseline_min":%s,"snmp_min":%s,"v2c":%s,"v2c_min":%s,"started":%s}\n' \
  "$switch" "$base_min" "$snmp_min" "$v2c" "$v2c_min" "$(date +%s)" > "$run/run.json"

# The poller phases need working SNMP: fail now, not after an hour of empty data.
poll_check() {
  podman run --rm --network host --env-file "$envf" "$image" python3 /app/poller.py --mode "$1" --host "$switch" --check
}
poll_check v3 >/dev/null || { echo "SNMPv3 check failed: is switch-snmp.sh apply in place?"; exit 1; }
if [ "$v2c" = 1 ]; then poll_check v2c >/dev/null || { echo "SNMPv2c check failed"; exit 1; }; fi

phase() {  # phase <name> <minutes> <none|v3|v2c>
  local name=$1 mins=$2 poll=$3 dir pids=() start end
  dir="$run/$name"
  mkdir -p "$dir"
  start=$(date +%s)
  end=$((start + mins * 60))
  printf '{"name":"%s","poll":"%s","start":%s,"end":%s,"minutes":%s}\n' "$name" "$poll" "$start" "$end" "$mins" \
    > "$dir/phase.json"
  echo "phase $name: $mins min, poll=$poll, $(date -d "@$start" +%T) to $(date -d "@$end" +%T)"

  python3 "$here/nats_sub.py" --mgmt-ip "$switch" --until "$end" --out "$dir/nats.jsonl" & pids+=($!)
  python3 "$here/cpu_sampler.py" --switch "$switch" --until "$end" --out "$dir/cpu.jsonl" & pids+=($!)
  # timeout ends tcpdump on schedule with 124: that is success here (pipefail would report it).
  { rc=0; sudo timeout -s INT "$((mins * 60))" tcpdump -i "$iface" -e -tt -nn -l -s 96 \
    "host $switch and (tcp port 57400 or tcp port 22 or udp port 161)" 2>"$dir/tcpdump.err" || rc=$?; [ "$rc" = 0 ] || [ "$rc" = 124 ]; } \
    | python3 "$here/wire_capture.py" --switch "$switch" --out "$dir/wire.jsonl" & pids+=($!)
  python3 "$here/collector_cpu.py" --names gnmic-1,gnmic-2,gnmic-output,nats,bench-snmp-poller --until "$end" \
    --out "$dir/collector.jsonl" & pids+=($!)
  if [ "$poll" != none ]; then
    podman run --rm --name bench-snmp-poller --network host --env-file "$envf" -v "$dir:/out" "$image" \
      python3 /app/poller.py --mode "$poll" --host "$switch" --until "$end" --out /out/walks.jsonl \
      > "$dir/poller.err" 2>&1 & pids+=($!)
  fi
  for p in "${pids[@]}"; do
    wait "$p" || echo "phase $name: process $p exited non-zero"
  done
  echo "phase $name done at $(date +%T)"
}

phase baseline "$base_min" none
phase snmp "$snmp_min" v3
if [ "$v2c" = 1 ]; then phase snmp-v2c "$v2c_min" v2c; fi

python3 "$here/analyze.py" "$run" > "$run/summary.stdout"
echo "analysis: $run/summary.txt"
echo "run complete $(date +%T)"
