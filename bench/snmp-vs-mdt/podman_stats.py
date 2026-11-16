#!/usr/bin/env python3
"""Collector cost: `podman stats --no-stream` every 60 s for the gnmic/NATS containers and the SNMP poller.

One JSONL row per container and sample: cpu_pct (podman's %, 100 = one core), mem_mib (working set).
  podman_stats.py --until EPOCH --out podman.jsonl
"""
import argparse, json, subprocess, time

NAMES = {"gnmic-1", "gnmic-2", "gnmic-output", "nats", "bench-snmp-poller"}
UNIT = {"B": 1 / 2**20, "kB": 1e3 / 2**20, "KB": 1e3 / 2**20, "KiB": 1 / 2**10, "MB": 1e6 / 2**20,
        "MiB": 1.0, "GB": 1e9 / 2**20, "GiB": 1024.0}


def mib(text):
    """'24.5MB / 3.9GB' -> 23.4 (MiB of the first figure)."""
    m = text.split("/")[0].strip()
    for unit in sorted(UNIT, key=len, reverse=True):
        if m.endswith(unit):
            return round(float(m[:-len(unit)]) * UNIT[unit], 2)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--period", type=float, default=60.0)
    a = ap.parse_args()
    nxt = time.time()
    with open(a.out, "a") as out:
        while nxt < a.until:
            ts = time.time()
            p = subprocess.run(["podman", "stats", "--no-stream", "--format", "json"],
                               capture_output=True, text=True, timeout=60)
            if p.returncode == 0 and p.stdout.strip():
                for c in json.loads(p.stdout):
                    if c.get("name") in NAMES:
                        out.write(json.dumps({"ts": round(ts, 3), "name": c["name"],
                                              "cpu_pct": float(c.get("cpu_percent", "0%").rstrip("%")),
                                              "mem_mib": mib(c.get("mem_usage", ""))}) + "\n")
                out.flush()
            nxt += a.period
            time.sleep(max(0.0, nxt - time.time()))


if __name__ == "__main__":
    main()
