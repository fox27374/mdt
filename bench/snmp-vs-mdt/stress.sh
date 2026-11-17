#!/usr/bin/env bash
# Stress run of the MDT-vs-SNMP bench (README, "Stress run"). Runs ON THE TEST HOST, detached. Phases run one after
# another, and never two bench loads at the same time:
#   baseline     nothing extra (live stack only)                                  --baseline-min (30)
#   mdt-double   bench gnmic: a second copy of all ten sw98 subscriptions         --double-min (30)
#   mdt-Ns       bench gnmic: xe_if_stats at N s, file output (not NATS)           --step-min (15)
#   snmp-Ns      SNMPv3 poller: xe_if_stats walked every N s                      --step-min (15)
#   for N in 30 10 5 1
# Every phase runs the same collectors: live NATS tap (passive), switch CPU sampler, wire capture, collector CPU.
# Output: $BENCH_RUNS/stress-<timestamp>/<phase>/..., then summary.json and summary.txt (analyze.py).
#
#   stress.sh [--baseline-min N] [--double-min N] [--step-min N]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
switch=${BENCH_SWITCH:-172.24.80.240}
envf=${BENCH_SNMP_ENV:-/home/claude/bench/snmp_env}
gnmic_env=${BENCH_GNMIC_ENV:-/opt/gnmic/gnmic_env}
mdt_yaml=${BENCH_MDT_YAML:-/home/claude/mdt/gnmic/config/mdt.yaml}
runs=${BENCH_RUNS:-/home/claude/bench/runs}
image=bench-snmp-poller:latest
gnmic_image=ghcr.io/openconfig/gnmic:0.46.0
collector_names=gnmic-1,gnmic-2,gnmic-output,nats,bench-gnmic,bench-snmp-poller
base_min=30 double_min=30 step_min=15
while [ $# -gt 0 ]; do
  case $1 in
    --baseline-min) base_min=$2; shift 2 ;;
    --double-min) double_min=$2; shift 2 ;;
    --step-min) step_min=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
for n in "$base_min" "$double_min" "$step_min"; do
  [[ $n =~ ^[1-9][0-9]*$ ]] || { echo "minutes must be a positive integer: $n" >&2; exit 2; }
done

run="$runs/stress-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run"
exec >>"$run/run.log" 2>&1
echo "run dir: $run"
iface=$(ip -o route get "$switch" | sed -n 's/.* dev \([^ ]*\).*/\1/p')
echo "switch $switch via $iface"
podman build -q --network host -t "$image" "$here"
podman image exists "$gnmic_image" || podman pull -q "$gnmic_image"

printf '{"switch":"%s","baseline_min":%s,"double_min":%s,"step_min":%s,"started":%s}\n' \
  "$switch" "$base_min" "$double_min" "$step_min" "$(date +%s)" > "$run/run.json"

# Bench processes of the running phase are killed on any exit, and the bench containers are removed.
bg=()
cleanup() {
  for p in "${bg[@]:-}"; do kill "$p" 2>/dev/null || true; done
  podman rm -f -t 5 bench-gnmic bench-snmp-poller >/dev/null 2>&1 || true
}
trap cleanup EXIT

# The poller phases need working SNMP: fail now, not after an hour of empty data.
podman run --rm --network host --env-file "$envf" "$image" python3 /app/poller.py --mode v3 --host "$switch" --check \
  >/dev/null || { echo "SNMPv3 check failed: is switch-snmp.sh apply in place?"; exit 1; }

# phase <name> <load: none|double|mdt|snmp> <minutes> [interval s]
phase() {
  local name=$1 load=$2 mins=$3 iv=${4:-} dir start end pids=() poll=none gargs=()
  dir="$run/$name"
  mkdir -p "$dir"
  start=$(date +%s)
  end=$((start + mins * 60))
  [ "$load" = snmp ] && poll=v3
  printf '{"name":"%s","load":"%s","poll":"%s","interval_s":%s,"start":%s,"end":%s,"minutes":%s}\n' \
    "$name" "$load" "$poll" "${iv:-null}" "$start" "$end" "$mins" > "$dir/phase.json"
  echo "phase $name: load=$load, $mins min, $(date -d "@$start" +%T) to $(date -d "@$end" +%T)"

  python3 "$here/nats_sub.py" --mgmt-ip "$switch" --until "$end" --out "$dir/nats.jsonl" & pids+=($!)
  python3 "$here/cpu_sampler.py" --switch "$switch" --until "$end" --out "$dir/cpu.jsonl" & pids+=($!)
  # timeout ends tcpdump on schedule with 124: that is success here (pipefail would report it).
  { rc=0; sudo timeout -s INT "$((mins * 60))" tcpdump -i "$iface" -e -tt -nn -l -s 96 \
    "host $switch and (tcp port 57400 or tcp port 22 or udp port 161)" 2>"$dir/tcpdump.err" || rc=$?; [ "$rc" = 0 ] || [ "$rc" = 124 ]; } \
    | python3 "$here/wire_capture.py" --switch "$switch" --out "$dir/wire.jsonl" & pids+=($!)
  python3 "$here/collector_cpu.py" --names "$collector_names" --until "$end" --out "$dir/collector.jsonl" & pids+=($!)

  case $load in
    mdt|double)
      if [ "$load" = mdt ]; then gargs=(--only xe_if_stats --interval "${iv}s"); else gargs=(--copies); fi
      python3 "$here/gen_gnmic.py" --mdt "$mdt_yaml" --switch "$switch" --out "$dir/gnmic.json" "${gargs[@]}"
      podman run -d --rm --name bench-gnmic --network host --env-file "$gnmic_env" \
        -v "$dir:/out:z" -v "$dir/gnmic.json:/app/gnmic.json:ro,z" "$gnmic_image" subscribe --config /app/gnmic.json \
        >/dev/null
      # tail -F follows the file gnmic writes; it is stopped 20 s after the bench gnmic, so the last lines are read.
      { timeout "$((mins * 60 + 20))" tail -n +1 -F "$dir/bench_events.jsonl" 2>/dev/null || true; } \
        | python3 "$here/bench_tail.py" --out "$dir/bench_mdt.jsonl" & pids+=($!)
      ( sleep $((end - $(date +%s))); podman stop -t 10 bench-gnmic >/dev/null 2>&1 ) & pids+=($!)
      ;;
    snmp)
      podman run --rm --name bench-snmp-poller --network host --env-file "$envf" -v "$dir:/out" "$image" \
        python3 /app/poller.py --mode v3 --host "$switch" --until "$end" --out /out/walks.jsonl \
        --only xe_if_stats --interval "$iv" > "$dir/poller.err" 2>&1 & pids+=($!)
      ;;
  esac

  bg+=("${pids[@]}")
  for p in "${pids[@]}"; do
    wait "$p" || echo "phase $name: process $p exited non-zero"
  done
  podman rm -f -t 5 bench-gnmic bench-snmp-poller >/dev/null 2>&1 || true
  echo "phase $name done at $(date +%T)"
}

phase baseline none "$base_min"
phase mdt-double double "$double_min"
for iv in 30 10 5 1; do
  phase "mdt-${iv}s" mdt "$step_min" "$iv"
  phase "snmp-${iv}s" snmp "$step_min" "$iv"
done

python3 "$here/analyze.py" "$run" > "$run/summary.stdout"
echo "analysis: $run/summary.txt"
echo "run complete $(date +%T)"
