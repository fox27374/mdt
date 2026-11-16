#!/usr/bin/env python3
"""Turns one bench run dir into summary.json and summary.txt (stdlib only).

  analyze.py RUNDIR          writes RUNDIR/summary.json and RUNDIR/summary.txt, prints the text
  analyze.py --selftest      checks the arithmetic on synthetic input

Phase dirs are the ones holding phase.json (baseline, snmp, snmp-v2c). Process and wire deltas are against baseline.
"""
import json, math, os, statistics, sys, tempfile


def jl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def pctl(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    return s[max(0, min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1))]


def mean(vals):
    return statistics.fmean(vals) if vals else None


def rnd(x, n=1):
    return None if x is None else round(x, n)


def walks_summary(rows, dur):
    by = {}
    for w in rows:
        by.setdefault(w["dataset"], []).append(w)
    out = {}
    for ds, ws in sorted(by.items()):
        durs = [w["duration_ms"] for w in ws]
        interval = ws[0]["interval_s"]
        out[ds] = {"walks": len(ws), "interval_s": interval,
                   "duration_ms_p50": rnd(pctl(durs, 50)), "duration_ms_p95": rnd(pctl(durs, 95)),
                   "duration_ms_max": rnd(max(durs)), "varbinds_mean": rnd(mean([w["varbinds"] for w in ws]), 0),
                   "vlans": ws[-1].get("vlans"), "errors": sum(w["errors"] for w in ws),
                   "lag_ms_max": rnd(max(w["lag_ms"] for w in ws)),
                   "busy_pct": rnd(sum(durs) / 1000 / dur * 100) if dur else None,
                   # a value changes on average every interval/2 + one walk after it was sampled
                   "staleness_est_s": rnd(interval / 2 + mean(durs) / 1000, 2)}
    one_pass = sum(v["duration_ms_p50"] or 0 for v in out.values())
    total = {"one_pass_ms_p50_sum": rnd(one_pass, 0),
             "busy_pct": rnd(sum(w["duration_ms"] for w in rows) / 1000 / dur * 100) if dur else None,
             "errors": sum(w["errors"] for w in rows)}
    return out, total


SYNCED_S = 5.0  # |offset| below this: switch clock taken as NTP-synced


def clock_summary(cpu_rows):
    offs = [r["clock_offset_s"] for r in cpu_rows if r.get("clock_offset_s") is not None]
    if not offs:
        return {"offset_s_median": None, "samples": 0}
    return {"offset_s_median": rnd(statistics.median(offs), 3), "offset_s_min": rnd(min(offs), 3),
            "offset_s_max": rnd(max(offs), 3), "samples": len(offs)}


def mdt_summary(rows, dur, offset_s):
    """Latency = host receive time - (switch sample time + clock offset). Without an offset it is the raw difference."""
    by = {}
    for m in rows:
        if m.get("switch_ts_ns") is None:
            continue
        by.setdefault(m["subscription"], []).append(m)
    hours = dur / 3600 if dur else None
    # show clock is only good to about 2 s (SSH timing). A smaller offset means the switch is NTP-synced: use its timestamps as they are.
    off_ns = (offset_s or 0.0) * 1e9 if abs(offset_s or 0.0) >= SYNCED_S else 0.0
    out = {}
    for sub, ms in sorted(by.items()):
        lat = [(m["recv_ns"] - m["switch_ts_ns"] - off_ns) / 1e6 for m in ms]
        out[sub] = {"messages": len(ms), "messages_per_hour": rnd(len(ms) / hours, 0) if hours else None,
                    "latency_ms_p50": rnd(pctl(lat, 50)), "latency_ms_p95": rnd(pctl(lat, 95)),
                    "latency_ms_max": rnd(max(lat)),
                    "bytes_per_msg_mean": rnd(mean([m["bytes"] for m in ms]), 0),
                    "bytes_per_hour": rnd(sum(m["bytes"] for m in ms) / hours, 0) if hours else None}
    return out


def cpu_summary(rows):
    ok = [r for r in rows if r.get("ok")]
    out = {"samples": len(ok), "failed": len(rows) - len(ok)}
    if not ok:
        return out
    for key in ("iosd", "platform"):
        names = {n for r in ok for n in r.get(key, {})}
        out[key] = {}
        for n in sorted(names):
            vals = [r[key][n][1] for r in ok if n in r.get(key, {})]  # 1-minute column
            out[key][n] = {"mean_1m": rnd(mean(vals), 2), "max_1m": rnd(max(vals), 2)}
    for key in ("iosd_total", "platform_total"):
        vals = [r[key][1] for r in ok if r.get(key)]
        if vals:
            out[key] = {"mean_1m": rnd(mean(vals), 2), "max_1m": rnd(max(vals), 2)}
    return out


def wire_summary(rows, dur):
    hours = dur / 3600 if dur else None
    agg = {}
    for r in rows:
        k = f"{r['class']}:{r['dir']}"
        a = agg.setdefault(k, {"bytes": 0, "packets": 0})
        a["bytes"] += r["bytes"]
        a["packets"] += r["packets"]
    out = {k: {"bytes_per_hour": rnd(v["bytes"] / hours, 0), "packets_per_hour": rnd(v["packets"] / hours, 0)}
           for k, v in sorted(agg.items())} if hours else {}
    out["total_bytes_per_hour"] = rnd(sum(v["bytes"] for v in agg.values()) / hours, 0) if hours else None
    return out


def podman_summary(rows):
    out = {}
    for n in sorted({r["name"] for r in rows}):
        c = [r["cpu_pct"] for r in rows if r["name"] == n]
        m = [r["mem_mib"] for r in rows if r["name"] == n and r.get("mem_mib") is not None]
        out[n] = {"samples": len(c), "cpu_pct_mean": rnd(mean(c), 2), "cpu_pct_max": rnd(max(c), 2),
                  "mem_mib_mean": rnd(mean(m), 1), "mem_mib_max": rnd(max(m), 1) if m else None}
    return out


def analyze(run):
    phases = {}
    for name in sorted(os.listdir(run)):
        pj = os.path.join(run, name, "phase.json")
        if os.path.isfile(pj):
            with open(pj) as f:
                meta = json.load(f)
            d = os.path.join(run, name)
            dur = meta["end"] - meta["start"]
            walks, wtot = walks_summary(jl(os.path.join(d, "walks.jsonl")), dur)
            cpu_rows = jl(os.path.join(d, "cpu.jsonl"))
            clock = clock_summary(cpu_rows)
            phases[name] = {"poll": meta["poll"], "minutes": meta["minutes"],
                            "snmp": walks, "snmp_total": wtot, "switch_clock": clock,
                            "mdt": mdt_summary(jl(os.path.join(d, "nats.jsonl")), dur, clock["offset_s_median"]),
                            "cpu": cpu_summary(cpu_rows),
                            "wire": wire_summary(jl(os.path.join(d, "wire.jsonl")), dur),
                            "collector": podman_summary(jl(os.path.join(d, "podman.jsonl")))}
    summary = {"run": os.path.abspath(run), "phases": phases}
    if "baseline" in phases:
        base = phases["baseline"]
        for name, ph in phases.items():
            if name == "baseline":
                continue
            delta = {}
            for key in ("iosd", "platform"):
                for n in sorted(set(base["cpu"].get(key, {})) | set(ph["cpu"].get(key, {}))):
                    b = base["cpu"].get(key, {}).get(n, {}).get("mean_1m")
                    p = ph["cpu"].get(key, {}).get(n, {}).get("mean_1m")
                    delta[n] = rnd(None if b is None or p is None else p - b, 2)
            for key in ("iosd_total", "platform_total"):
                b, p = base["cpu"].get(key, {}).get("mean_1m"), ph["cpu"].get(key, {}).get("mean_1m")
                delta[key] = rnd(None if b is None or p is None else p - b, 2)
            wire_d = {}
            for k in set(base["wire"]) | set(ph["wire"]):
                if k == "total_bytes_per_hour" or not isinstance(base["wire"].get(k, {}), dict):
                    continue
                b = base["wire"].get(k, {}).get("bytes_per_hour") or 0
                p = ph["wire"].get(k, {}).get("bytes_per_hour") or 0
                wire_d[k] = rnd(p - b, 0)
            ph["cpu_delta_vs_baseline_1m"] = delta
            ph["wire_delta_vs_baseline_bytes_per_hour"] = wire_d
    return summary


def text(s):
    L = []
    w = L.append
    w(f"Run: {s['run']}")
    for name, ph in s["phases"].items():
        w(f"\n== phase {name} (poll={ph['poll']}, {ph['minutes']} min) ==")
        if ph["snmp"]:
            w("SNMP walks   dataset        int  n  p50ms   p95ms   maxms  varbinds  vlans  errs  lagmax  busy%  stale_s")
            for ds, v in ph["snmp"].items():
                w(f"               {ds:<14} {v['interval_s']:>4} {v['walks']:>3} {v['duration_ms_p50']!s:>7} "
                  f"{v['duration_ms_p95']!s:>7} {v['duration_ms_max']!s:>7} {v['varbinds_mean']!s:>9} "
                  f"{v['vlans']!s:>5} {v['errors']:>5} {v['lag_ms_max']!s:>7} {v['busy_pct']!s:>6} "
                  f"{v['staleness_est_s']!s:>8}")
            t = ph["snmp_total"]
            w(f"               one full pass (sum of p50s): {t['one_pass_ms_p50_sum']} ms; poller busy "
              f"{t['busy_pct']}%; errors {t['errors']}")
        if ph["mdt"]:
            sc = ph["switch_clock"]
            if abs(sc["offset_s_median"] or 0.0) < SYNCED_S:
                w(f"MDT latency from switch timestamps as sent (clock offset {sc['offset_s_median']} s: NTP-synced, no correction)")
            else:
                w(f"MDT latency corrected by switch clock offset {sc['offset_s_median']} s "
                  f"(min {sc.get('offset_s_min')}, max {sc.get('offset_s_max')}, {sc['samples']} samples)")
            w("MDT (gNMI)   subscription     msgs/h   lat p50ms  p95ms  bytes/msg  bytes/h")
            for sub, v in ph["mdt"].items():
                w(f"               {sub:<16} {v['messages_per_hour']!s:>6} {v['latency_ms_p50']!s:>9} "
                  f"{v['latency_ms_p95']!s:>6} {v['bytes_per_msg_mean']!s:>10} {v['bytes_per_hour']!s:>9}")
        c = ph["cpu"]
        if c.get("samples"):
            w(f"Switch CPU (1-min %, {c['samples']} samples, {c['failed']} failed)")
            for key in ("iosd_total", "platform_total"):
                if key in c:
                    w(f"               {key:<16} mean {c[key]['mean_1m']}  max {c[key]['max_1m']}")
            for key in ("iosd", "platform"):
                for n, v in c.get(key, {}).items():
                    w(f"               {n:<16} mean {v['mean_1m']}  max {v['max_1m']}")
        if ph["wire"]:
            w(f"Wire bytes/hour: total {ph['wire'].get('total_bytes_per_hour')}")
            for k, v in ph["wire"].items():
                if k != "total_bytes_per_hour":
                    w(f"               {k:<22} {v['bytes_per_hour']!s:>12} B/h  {v['packets_per_hour']!s:>9} pkt/h")
        for n, v in ph["collector"].items():
            w(f"Collector      {n:<18} cpu% mean {v['cpu_pct_mean']} max {v['cpu_pct_max']}  "
              f"mem MiB mean {v['mem_mib_mean']} max {v['mem_mib_max']}")
        for k in ("cpu_delta_vs_baseline_1m", "wire_delta_vs_baseline_bytes_per_hour"):
            if k in ph:
                w(f"Delta vs baseline ({k}): {json.dumps(ph[k])}")
    return "\n".join(L) + "\n"


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        t0 = 1_000_000.0
        def dump(path, rows):
            with open(path, "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
        for name, poll in (("baseline", "none"), ("snmp", "v3")):
            d = os.path.join(tmp, name)
            os.makedirs(d)
            with open(os.path.join(d, "phase.json"), "w") as f:
                json.dump({"poll": poll, "minutes": 60, "start": t0, "end": t0 + 3600}, f)
        walks = [{"dataset": "xe_cpu_stats", "interval_s": 60, "duration_ms": d, "varbinds": 10, "vlans": None,
                  "errors": 0, "lag_ms": 0.0} for d in (100.0, 200.0, 300.0, 400.0)]
        dump(os.path.join(tmp, "snmp", "walks.jsonl"), walks)
        nats = [{"recv_ns": int((t0 + i) * 1e9) + 5_000_000, "switch_ts_ns": int((t0 + i) * 1e9),
                 "subscription": "xe_cpu_stats", "bytes": 1000} for i in range(10)]
        nats = [dict(m, switch_ts_ns=m["switch_ts_ns"] - 770 * 10**9) for m in nats]  # switch clock 770 s slow
        dump(os.path.join(tmp, "baseline", "nats.jsonl"), nats)
        dump(os.path.join(tmp, "snmp", "nats.jsonl"), nats)
        dump(os.path.join(tmp, "baseline", "cpu.jsonl"),
             [{"ok": True, "iosd": {"SNMP ENGINE": [0.1, 1.0, 1.0]}, "iosd_total": [5, 4, 3],
               "clock_offset_s": 770.0}] * 2)
        dump(os.path.join(tmp, "snmp", "cpu.jsonl"),
             [{"ok": True, "iosd": {"SNMP ENGINE": [0.5, 3.0, 2.0]}, "iosd_total": [6, 5, 4]},
              {"ok": False, "error": "timeout"}])
        dump(os.path.join(tmp, "baseline", "wire.jsonl"), [{"minute": t0, "class": "gnmi", "dir": "from_switch",
                                                             "packets": 1, "bytes": 3600}])
        dump(os.path.join(tmp, "snmp", "wire.jsonl"), [{"minute": t0, "class": "gnmi", "dir": "from_switch",
                                                         "packets": 2, "bytes": 7200}])
        dump(os.path.join(tmp, "snmp", "podman.jsonl"), [{"ts": t0, "name": "bench-snmp-poller", "cpu_pct": 2.0,
                                                           "mem_mib": 30.0},
                                                          {"ts": t0 + 60, "name": "bench-snmp-poller",
                                                           "cpu_pct": 4.0, "mem_mib": 40.0}])
        s = analyze(tmp)
        ph = s["phases"]
        cpu = ph["snmp"]["snmp"]["xe_cpu_stats"]
        assert cpu["walks"] == 4 and cpu["duration_ms_p50"] == 200.0 and cpu["duration_ms_max"] == 400.0, cpu
        assert cpu["errors"] == 0 and cpu["vlans"] is None
        assert abs(cpu["staleness_est_s"] - (30 + 0.25)) < 1e-6, cpu
        lat = ph["baseline"]["mdt"]["xe_cpu_stats"]
        assert lat["latency_ms_p50"] == 5.0 and lat["bytes_per_msg_mean"] == 1000, lat
        assert ph["baseline"]["switch_clock"]["offset_s_median"] == 770.0
        assert ph["snmp"]["cpu"]["samples"] == 1 and ph["snmp"]["cpu"]["failed"] == 1
        assert ph["snmp"]["cpu"]["iosd"]["SNMP ENGINE"]["mean_1m"] == 3.0
        assert ph["snmp"]["cpu_delta_vs_baseline_1m"]["SNMP ENGINE"] == 2.0
        assert ph["baseline"]["wire"]["gnmi:from_switch"]["bytes_per_hour"] == 3600.0
        assert ph["snmp"]["wire_delta_vs_baseline_bytes_per_hour"]["gnmi:from_switch"] == 3600.0
        assert ph["snmp"]["collector"]["bench-snmp-poller"]["cpu_pct_max"] == 4.0
        assert ph["snmp"]["collector"]["bench-snmp-poller"]["mem_mib_mean"] == 35.0
        out = text(s)
        assert "xe_cpu_stats" in out and "SNMP ENGINE" in out
        with open(os.path.join(tmp, "summary.json"), "w") as f:
            json.dump(s, f)
    print("selftest ok")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
        return
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    run = sys.argv[1]
    s = analyze(run)
    with open(os.path.join(run, "summary.json"), "w") as f:
        json.dump(s, f, indent=2)
    t = text(s)
    with open(os.path.join(run, "summary.txt"), "w") as f:
        f.write(t)
    sys.stdout.write(t)


if __name__ == "__main__":
    main()
