#!/usr/bin/env python3
"""Collector cost from cgroup v2, once a minute: CPU time (cpu.stat usage_usec) and memory.current per container.

The cgroup comes from the container's init PID (/proc/<pid>/cgroup). Rootless podman owns that cgroup, so no sudo.
Rows hold the running counter; analyze.py turns the difference between two rows into CPU % (100 = one core).
A name that is not running is skipped.

  collector_cpu.py --names gnmic-1,nats --until EPOCH --out collector.jsonl
"""
import argparse, json, subprocess, time

ROOT = "/sys/fs/cgroup"


def cgroup_dir(name):
    p = subprocess.run(["podman", "inspect", "-f", "{{.State.Pid}}", name], capture_output=True, text=True, timeout=30)
    pid = p.stdout.strip()
    if p.returncode or pid in ("", "0"):
        return None
    with open(f"/proc/{pid}/cgroup") as f:
        for line in f:
            hier, _, path = line.rstrip("\n").split(":", 2)
            if hier == "0":
                return ROOT + path
    return None


def read_counters(d):
    with open(f"{d}/cpu.stat") as f:
        usage = next(int(line.split()[1]) for line in f if line.startswith("usage_usec "))
    with open(f"{d}/memory.current") as f:
        mem = int(f.read())
    return usage, mem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", required=True, help="comma-separated container names")
    ap.add_argument("--until", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--period", type=float, default=60.0)
    a = ap.parse_args()
    names = [n for n in a.names.split(",") if n]
    nxt = time.time()
    with open(a.out, "a") as out:
        while nxt < a.until:
            ts = time.time()
            for n in names:
                try:
                    d = cgroup_dir(n)
                    if d is None:
                        continue
                    usage, mem = read_counters(d)
                except (OSError, StopIteration, ValueError):
                    continue  # container gone or not yet running: no row this minute
                out.write(json.dumps({"ts": round(ts, 3), "name": n, "usage_usec": usage, "mem_bytes": mem}) + "\n")
            out.flush()
            nxt += a.period
            time.sleep(max(0.0, nxt - time.time()))


if __name__ == "__main__":
    main()
