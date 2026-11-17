#!/usr/bin/env python3
"""Arrival side of the bench MDT (stress.sh): reads the gnmic file output from stdin and stamps each line with the host
time it was read. One row per gnmic message, with the fields nats_sub.py writes (recv_ns, switch_ts_ns, subscription,
bytes), so analyze.py reads both alike. Nothing is sent anywhere.

  tail -n +1 -F bench_events.jsonl | bench_tail.py --out bench_mdt.jsonl
"""
import argparse, json, sys, time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(a.out, "a") as out:
        for line in sys.stdin:
            recv_ns = time.time_ns()
            try:
                evs = json.loads(line)
            except ValueError:
                continue
            evs = evs if isinstance(evs, list) else [evs]
            if not evs or not isinstance(evs[0], dict):
                continue
            e = evs[0]
            out.write(json.dumps({
                "recv_ns": recv_ns,
                "switch_ts_ns": e.get("timestamp"),
                "subscription": (e.get("tags") or {}).get("subscription-name") or e.get("name"),
                "bytes": len(line.rstrip("\n").encode()),
                "events": len(evs)}) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
