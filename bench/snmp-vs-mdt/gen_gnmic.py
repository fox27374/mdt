#!/usr/bin/env python3
"""Config for the bench gnmic container (stress.sh). One target, the switch's subscriptions copied from the live gnmic
config, and a file output instead of NATS: nothing goes to the live `mdt` subject.

  gen_gnmic.py --mdt live/mdt.yaml --switch IP --out gnmic.json [--only NAME] [--interval 1s] [--copies]

  --only NAME   keep one subscription (the sweep: xe_if_stats); --interval overrides its sample-interval
  --copies      keep all of them, plus an identical second copy of each (NAME_copy): the mdt-double phase

The config is JSON, which gnmic reads as YAML. No credentials go in it: it refers to ${SWITCH_USERNAME} and
${SWITCH_PASSWORD}, which the container gets from --env-file (the live gnmic_env, read only).
"""
import argparse, json, sys

import yaml

KEEP = ("mode", "encoding", "stream-mode", "sample-interval", "paths")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mdt", required=True)
    ap.add_argument("--switch", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only")
    ap.add_argument("--interval")
    ap.add_argument("--copies", action="store_true")
    a = ap.parse_args()
    with open(a.mdt) as f:
        live = yaml.safe_load(f)
    target = (live.get("targets") or {}).get(f"{a.switch}:57400")
    if target is None:
        sys.exit(f"{a.switch}:57400 is not a target in {a.mdt}")
    subs = {}
    for name in target["subscriptions"]:
        if a.only and name != a.only:
            continue
        subs[name] = {k: live["subscriptions"][name][k] for k in KEEP if k in live["subscriptions"][name]}
        if a.only and a.interval:
            subs[name]["sample-interval"] = a.interval
    if not subs:
        sys.exit(f"no subscription {a.only!r} on {a.switch}")
    if a.copies:
        subs.update({n + "_copy": dict(s) for n, s in list(subs.items())})
    cfg = {
        "username": "${SWITCH_USERNAME}",
        "password": "${SWITCH_PASSWORD}",
        "insecure": False,
        "skip-verify": True,
        "targets": {f"{a.switch}:57400": {"name": target["name"], "event-tags": target.get("event-tags", {}),
                                          "subscriptions": list(subs)}},
        "subscriptions": {n: dict(s, outputs=["bench"]) for n, s in subs.items()},
        "outputs": {"bench": {"type": "file", "filename": "/out/bench_events.jsonl", "format": "event"}},
    }
    with open(a.out, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"{len(subs)} subscriptions for {a.switch} -> {a.out}")


if __name__ == "__main__":
    main()
