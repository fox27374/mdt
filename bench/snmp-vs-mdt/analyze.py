#!/usr/bin/env python3
"""Turns one bench run dir into summary.json and summary.txt (stdlib only).

  analyze.py RUNDIR          writes RUNDIR/summary.json and RUNDIR/summary.txt, prints the text
  analyze.py --selftest      checks the arithmetic on synthetic input

Phase dirs are the ones holding phase.json. Process and wire deltas are against the baseline phase.
Stress runs (stress.sh) add: bench MDT rows (bench_mdt.jsonl, gnmic file output stamped on arrival), collector CPU
from cgroups (collector.jsonl), rate accuracy (README, "Rate accuracy"), the sweep (mdt-<N>s / snmp-<N>s pairs) and
the mdt-double deltas. Run dirs from run.sh still analyse; their collector lines come from the old podman.jsonl,
which is no longer read.
"""
import json, math, os, re, statistics, sys, tempfile

LATE_FRAC = 0.1            # a walk that started more than this share of its interval late counts as late
SYNCED_S = 5.0             # |switch clock offset| below this: the switch clock is taken as NTP-synced
LIVE_IF_STATS_S = 30       # sample-interval of xe_if_stats in gnmic/config/mdt.yaml (the live stream)
MDT_KEYS = ["iosd_total", "platform_total", "ndbmand", "pubd", "gnmib"]
SNMP_KEYS = ["iosd_total", "platform_total", "SNMP ENGINE", "IP SNMP", "PDU DISPATCHER"]
SWEEP_INTERVALS = (30, 10, 5, 1)


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


def pct(a, b):
    return rnd(100 * a / b, 1) if b else None


def err_stats(errs):
    if not errs:
        return None
    return {"n": len(errs), "p50": rnd(pctl(errs, 50), 2), "p95": rnd(pctl(errs, 95), 2), "max": rnd(max(errs), 2)}


# ---- SNMP walks ----------------------------------------------------------------------------------------------------

def missed_slots(starts, interval):
    """Nominal slots skipped in a sequence of walk starts: a gap of k intervals between two starts skips k-1 slots."""
    return sum(max(0, round((b - a) / interval) - 1) for a, b in zip(starts, starts[1:]))


def walks_summary(rows, dur):
    by = {}
    for w in rows:
        by.setdefault(w["dataset"], []).append(w)
    out = {}
    for ds, ws in sorted(by.items()):
        ws.sort(key=lambda w: w.get("start", 0))
        durs = [w["duration_ms"] for w in ws]
        interval = ws[0]["interval_s"]
        late = sum(1 for w in ws if w["lag_ms"] > LATE_FRAC * interval * 1000)
        out[ds] = {"walks": len(ws), "interval_s": interval,
                   "duration_ms_p50": rnd(pctl(durs, 50)), "duration_ms_p95": rnd(pctl(durs, 95)),
                   "duration_ms_max": rnd(max(durs)), "varbinds_mean": rnd(mean([w["varbinds"] for w in ws]), 0),
                   "vlans": ws[-1].get("vlans"), "errors": sum(w["errors"] for w in ws),
                   "lag_ms_max": rnd(max(w["lag_ms"] for w in ws)),
                   "late_pct": pct(late, len(ws)),
                   "missed_slots": missed_slots([w["start"] for w in ws], interval) if "start" in ws[0] else None,
                   "busy_pct": rnd(sum(durs) / 1000 / dur * 100) if dur else None,
                   # a value changes on average every interval/2 + one walk after it was sampled
                   "staleness_est_s": rnd(interval / 2 + mean(durs) / 1000, 2)}
    one_pass = sum(v["duration_ms_p50"] or 0 for v in out.values())
    total = {"one_pass_ms_p50_sum": rnd(one_pass, 0),
             "busy_pct": rnd(sum(w["duration_ms"] for w in rows) / 1000 / dur * 100) if dur else None,
             "errors": sum(w["errors"] for w in rows)}
    return out, total


def snmp_rate_error(walks):
    """% error bound on a rate from walk start times (host clock), one value per walk after the first:
    (duration_i + |start_i - start_(i-1) - nominal|) / nominal. duration_i is the spread of the counter read."""
    nominal = walks[0]["interval_s"]
    ws = sorted(walks, key=lambda w: w["start"])
    errs = [(w["duration_ms"] / 1000 + abs(w["start"] - p["start"] - nominal)) / nominal * 100
            for p, w in zip(ws, ws[1:])]
    return err_stats(errs)


# ---- MDT ------------------------------------------------------------------------------------------------------------

def distinct_samples(rows, nominal):
    """(switch_ts_ns, first arrival_ns) per switch sample, by switch time. One sample reaches the host as a burst of
    messages a few tens of ms apart (IOS-XE splits it by leaf group), so a new sample starts only after a gap longer
    than half the nominal interval."""
    msgs = sorted((m["switch_ts_ns"], m["recv_ns"]) for m in rows if m.get("switch_ts_ns") is not None)
    out, last = [], None
    for ts, rx in msgs:
        if last is not None and ts - last <= nominal * 1e9 / 2:
            out[-1][1] = min(out[-1][1], rx)
        else:
            out.append([ts, rx])
        last = ts
    return [tuple(x) for x in out]


def host_rate_error(rows, nominal):
    """% error bound on a rate computed from host arrival times, one value per sample after the first:
    |(arrival_i - arrival_(i-1)) - (switch_i - switch_(i-1))| / nominal. The switch timestamps are the true spacing,
    so a rate on switch time has 0 error by construction."""
    s = distinct_samples(rows, nominal)
    errs = [abs((r1 - r0) - (s1 - s0)) / 1e9 / nominal * 100 for (s0, r0), (s1, r1) in zip(s, s[1:])]
    return err_stats(errs)


def rate_accuracy(walks, mdt_rows, mdt_nominal):
    snmp_nominal = walks[0]["interval_s"] if walks else None
    return {"snmp_nominal_s": snmp_nominal, "snmp": snmp_rate_error(walks) if walks else None,
            "mdt_nominal_s": mdt_nominal,
            "mdt_host_arrival": host_rate_error(mdt_rows, mdt_nominal) if mdt_rows and mdt_nominal else None}


def bench_summary(rows, dur, nominal):
    """Bench gnmic (file output) per subscription. samples = distinct switch sample times; expected = dur / nominal."""
    by = {}
    for m in rows:
        by.setdefault(m.get("subscription"), []).append(m)
    hours = dur / 3600 if dur else None
    out = {}
    for sub, ms in sorted(by.items(), key=lambda kv: str(kv[0])):
        s = distinct_samples(ms, nominal) if nominal else []
        gap_sw = [(b[0] - a[0]) / 1e6 for a, b in zip(s, s[1:])]
        gap_rx = [(b[1] - a[1]) / 1e6 for a, b in zip(s, s[1:])]
        exp = dur / nominal if nominal else None
        out[str(sub)] = {"messages": len(ms), "samples": len(s) if nominal else None,
                         "samples_expected": rnd(exp, 0), "received_pct": pct(len(s), exp) if exp else None,
                         "gap_switch_ms_p50": rnd(pctl(gap_sw, 50)), "gap_switch_ms_p95": rnd(pctl(gap_sw, 95)),
                         "gap_switch_ms_max": rnd(max(gap_sw)) if gap_sw else None,
                         "gap_arrival_ms_p50": rnd(pctl(gap_rx, 50)), "gap_arrival_ms_p95": rnd(pctl(gap_rx, 95)),
                         "gap_arrival_ms_max": rnd(max(gap_rx)) if gap_rx else None,
                         "bytes_per_hour": rnd(sum(m["bytes"] for m in ms) / hours, 0) if hours else None}
    return out


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


# ---- switch, wire, collector ----------------------------------------------------------------------------------------

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


def collector_summary(rows):
    """CPU % per minute from the cgroup counters: (usage_usec delta / 1e6) / seconds * 100, 100 = one core."""
    by = {}
    for r in rows:
        if "usage_usec" in r:
            by.setdefault(r["name"], []).append(r)
    out = {}
    for n, rs in sorted(by.items()):
        rs.sort(key=lambda r: r["ts"])
        pcts = []
        for a, b in zip(rs, rs[1:]):
            dt = b["ts"] - a["ts"]
            if 0 < dt <= 300 and b["usage_usec"] >= a["usage_usec"]:  # a counter that went back: container restarted
                pcts.append((b["usage_usec"] - a["usage_usec"]) / 1e6 / dt * 100)
        mem = [r["mem_bytes"] / 2**20 for r in rs]
        out[n] = {"samples": len(pcts), "cpu_pct_mean": rnd(mean(pcts), 2), "cpu_pct_max": rnd(max(pcts), 2) if pcts else None,
                  "mem_mib_mean": rnd(mean(mem), 1), "mem_mib_max": rnd(max(mem), 1)}
    return out


# ---- phases, deltas, sweep ------------------------------------------------------------------------------------------

def add_deltas(base, ph):
    """Switch CPU (1-min mean) and wire rates of a phase minus the baseline phase."""
    def diff(b, p):
        return rnd(None if b is None or p is None else p - b, 2)
    delta = {}
    for key in ("iosd", "platform"):
        for n in sorted(set(base["cpu"].get(key, {})) | set(ph["cpu"].get(key, {}))):
            delta[n] = diff(base["cpu"].get(key, {}).get(n, {}).get("mean_1m"), ph["cpu"].get(key, {}).get(n, {}).get("mean_1m"))
    for key in ("iosd_total", "platform_total"):
        delta[key] = diff(base["cpu"].get(key, {}).get("mean_1m"), ph["cpu"].get(key, {}).get("mean_1m"))
    ph["cpu_delta_vs_baseline_1m"] = delta
    for field, name in (("bytes_per_hour", "wire_delta_vs_baseline_bytes_per_hour"),
                        ("packets_per_hour", "wire_delta_vs_baseline_packets_per_hour")):
        keys = {k for k in set(base["wire"]) | set(ph["wire"]) if k != "total_bytes_per_hour"}
        ph[name] = {k: rnd((ph["wire"].get(k, {}).get(field) or 0) - (base["wire"].get(k, {}).get(field) or 0), 0)
                    for k in sorted(keys)}


def class_delta(ph, cls, key):
    """Sum of a wire delta over both directions of one class (gnmi, snmp, ssh, other)."""
    return rnd(sum(v for k, v in (ph.get(key) or {}).items() if k.startswith(cls + ":") and v is not None), 0)


def sweep_rows(phases):
    rows = []
    if "baseline" not in phases:
        return rows
    for n in SWEEP_INTERVALS:
        for mode in ("mdt", "snmp"):
            ph = phases.get(f"{mode}-{n}s")
            if ph is None:
                continue
            cls, coll, keys = ("gnmi", "bench-gnmic", MDT_KEYS) if mode == "mdt" else ("snmp", "bench-snmp-poller", SNMP_KEYS)
            dur = ph["duration_s"]
            row = {"interval_s": n, "mode": mode, "minutes": ph["minutes"],
                   "cpu_delta_1m": {k: ph["cpu_delta_vs_baseline_1m"].get(k) for k in keys},
                   "wire_bytes_per_hour_delta": class_delta(ph, cls, "wire_delta_vs_baseline_bytes_per_hour"),
                   "wire_packets_per_hour_delta": class_delta(ph, cls, "wire_delta_vs_baseline_packets_per_hour"),
                   "collector": ph["collector"].get(coll),
                   "rate_error_pct": ph["rate_accuracy"]["mdt_host_arrival" if mode == "mdt" else "snmp"]}
            if mode == "mdt":
                v = ph["bench_mdt"].get("xe_if_stats") or {}
                row.update(received=v.get("samples"), expected=v.get("samples_expected"),
                           received_pct=v.get("received_pct"), gap_switch_ms_p50=v.get("gap_switch_ms_p50"),
                           gap_switch_ms_max=v.get("gap_switch_ms_max"))
            else:
                v = ph["snmp"].get("xe_if_stats") or {}
                exp = dur / n
                row.update(received=v.get("walks"), expected=rnd(exp, 0), received_pct=pct(v.get("walks", 0), exp),
                           walk_ms={"p50": v.get("duration_ms_p50"), "p95": v.get("duration_ms_p95"),
                                    "max": v.get("duration_ms_max")},
                           late_pct=v.get("late_pct"), missed_slots=v.get("missed_slots"))
            rows.append(row)
    return rows


def double_summary(phases):
    ph = phases.get("mdt-double")
    if ph is None or "baseline" not in phases:
        return None
    d = ph["cpu_delta_vs_baseline_1m"]
    return {"minutes": ph["minutes"],
            "cpu_delta_1m_one_set": {k: d.get(k) for k in MDT_KEYS},
            "wire_bytes_per_hour_delta": class_delta(ph, "gnmi", "wire_delta_vs_baseline_bytes_per_hour"),
            "wire_packets_per_hour_delta": class_delta(ph, "gnmi", "wire_delta_vs_baseline_packets_per_hour"),
            "collector_bench_gnmic": ph["collector"].get("bench-gnmic"),
            "bench_samples": {k: v.get("samples") for k, v in ph["bench_mdt"].items()}}


def analyze(run):
    phases = {}
    for name in sorted(os.listdir(run)):
        pj = os.path.join(run, name, "phase.json")
        if not os.path.isfile(pj):
            continue
        with open(pj) as f:
            meta = json.load(f)
        d = os.path.join(run, name)
        dur = meta["end"] - meta["start"]
        walk_rows = jl(os.path.join(d, "walks.jsonl"))
        walks, wtot = walks_summary(walk_rows, dur)
        cpu_rows = jl(os.path.join(d, "cpu.jsonl"))
        clock = clock_summary(cpu_rows)
        xe_walks = [w for w in walk_rows if w["dataset"] == "xe_if_stats"]
        bench = jl(os.path.join(d, "bench_mdt.jsonl"))
        live = jl(os.path.join(d, "nats.jsonl"))
        # the bench stream runs at the phase's interval; the live stream at its own 30 s
        mdt_src, mdt_nominal = (bench, meta.get("interval_s")) if bench else (live, LIVE_IF_STATS_S)
        phases[name] = {"load": meta.get("load") or ("snmp" if meta["poll"] != "none" else "none"),
                        "poll": meta["poll"], "minutes": meta["minutes"], "interval_s": meta.get("interval_s"),
                        "duration_s": dur,
                        "snmp": walks, "snmp_total": wtot, "switch_clock": clock,
                        "mdt": mdt_summary(live, dur, clock["offset_s_median"]),
                        "bench_mdt": bench_summary(bench, dur, meta.get("interval_s")),
                        "rate_accuracy": rate_accuracy(xe_walks, [m for m in mdt_src if m.get("subscription") == "xe_if_stats"],
                                                       mdt_nominal),
                        "cpu": cpu_summary(cpu_rows),
                        "wire": wire_summary(jl(os.path.join(d, "wire.jsonl")), dur),
                        "collector": collector_summary(jl(os.path.join(d, "collector.jsonl")))}
    summary = {"run": os.path.abspath(run), "phases": phases}
    if "baseline" in phases:
        for name, ph in phases.items():
            if name != "baseline":
                add_deltas(phases["baseline"], ph)
    summary["sweep"] = sweep_rows(phases)
    summary["double"] = double_summary(phases)
    return summary


# ---- text -----------------------------------------------------------------------------------------------------------

def text(s):
    L = []
    w = L.append
    w(f"Run: {s['run']}")
    for name, ph in s["phases"].items():
        iv = f", interval {ph['interval_s']} s" if ph["interval_s"] else ""
        w(f"\n== phase {name} (load={ph['load']}{iv}, {ph['minutes']} min) ==")
        if ph["snmp"]:
            w("SNMP walks   dataset        int  n  p50ms   p95ms   maxms  varbinds  vlans  errs  lagmax  late%  missed  busy%  stale_s")
            for ds, v in ph["snmp"].items():
                w(f"               {ds:<14} {v['interval_s']:>4} {v['walks']:>3} {v['duration_ms_p50']!s:>7} "
                  f"{v['duration_ms_p95']!s:>7} {v['duration_ms_max']!s:>7} {v['varbinds_mean']!s:>9} "
                  f"{v['vlans']!s:>5} {v['errors']:>5} {v['lag_ms_max']!s:>7} {v['late_pct']!s:>6} "
                  f"{v['missed_slots']!s:>7} {v['busy_pct']!s:>6} {v['staleness_est_s']!s:>8}")
            t = ph["snmp_total"]
            w(f"               one full pass (sum of p50s): {t['one_pass_ms_p50_sum']} ms; poller busy "
              f"{t['busy_pct']}%; errors {t['errors']}")
        if ph["bench_mdt"]:
            w("MDT bench   subscription     samples/expected  gap switch p50/p95/max ms  gap arrival p50/p95/max ms  bytes/h")
            for sub, v in ph["bench_mdt"].items():
                w(f"               {sub:<16} {v['samples']!s:>7}/{v['samples_expected']!s:<7} "
                  f"{v['gap_switch_ms_p50']!s}/{v['gap_switch_ms_p95']!s}/{v['gap_switch_ms_max']!s}  "
                  f"{v['gap_arrival_ms_p50']!s}/{v['gap_arrival_ms_p95']!s}/{v['gap_arrival_ms_max']!s}  "
                  f"{v['bytes_per_hour']!s}")
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
        ra = ph["rate_accuracy"]
        if ra["snmp"]:
            r = ra["snmp"]
            w(f"Rate error bound, SNMP (nominal {ra['snmp_nominal_s']} s, walk starts): p50 {r['p50']}% p95 {r['p95']}% "
              f"max {r['max']}% (n={r['n']})")
        if ra["mdt_host_arrival"]:
            r = ra["mdt_host_arrival"]
            w(f"Rate error bound, MDT host arrival (nominal {ra['mdt_nominal_s']} s): p50 {r['p50']}% p95 {r['p95']}% "
              f"max {r['max']}% (n={r['n']}); on switch timestamps 0 by construction")
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
    if s["sweep"]:
        w("\n== sweep: MDT vs SNMP, deltas vs baseline (collector CPU: 100 = one core) ==")
        for r in s["sweep"]:
            w(f"interval {r['interval_s']} s  {r['mode'].upper()} ({r['minutes']} min)")
            w("  switch dCPU 1m  " + "  ".join(f"{k} {v}" for k, v in r["cpu_delta_1m"].items()))
            w(f"  wire delta      {r['wire_bytes_per_hour_delta']} B/h  {r['wire_packets_per_hour_delta']} pkt/h")
            c = r["collector"]
            w(f"  collector       {'bench-gnmic' if r['mode'] == 'mdt' else 'bench-snmp-poller'} "
              + (f"cpu% mean {c['cpu_pct_mean']} max {c['cpu_pct_max']}, mem MiB {c['mem_mib_mean']}" if c else "n/a"))
            if r["mode"] == "mdt":
                w(f"  msgs            samples {r['received']} of {r['expected']} expected ({r['received_pct']}%), "
                  f"gap p50 {r['gap_switch_ms_p50']} ms max {r['gap_switch_ms_max']} ms (switch time)")
            else:
                wk = r["walk_ms"]
                w(f"  walks           {r['received']} of {r['expected']} expected ({r['received_pct']}%), "
                  f"walk p50 {wk['p50']} p95 {wk['p95']} max {wk['max']} ms, late {r['late_pct']}%, "
                  f"missed slots {r['missed_slots']}")
            rr = r["rate_error_pct"]
            w(f"  rate error %    " + (f"p50 {rr['p50']} p95 {rr['p95']} max {rr['max']} (n={rr['n']})" if rr else "n/a"))
    if s["double"]:
        d = s["double"]
        w(f"\n== mdt-double ({d['minutes']} min): cost of one extra MDT set of sw98 subscriptions ==")
        w("  switch dCPU 1m  " + "  ".join(f"{k} {v}" for k, v in d["cpu_delta_1m_one_set"].items()))
        w(f"  wire delta      {d['wire_bytes_per_hour_delta']} B/h  {d['wire_packets_per_hour_delta']} pkt/h (gnmi)")
        w(f"  collector       bench-gnmic {d['collector_bench_gnmic']}")
    return "\n".join(L) + "\n"


# ---- selftest -------------------------------------------------------------------------------------------------------

def selftest():
    # the arithmetic, on hand-made numbers
    assert missed_slots([0, 10, 30, 40], 10) == 1 and missed_slots([0, 10.5, 20], 10) == 0
    walks3 = [{"start": 0.0, "duration_ms": 200.0, "interval_s": 10},
              {"start": 10.5, "duration_ms": 300.0, "interval_s": 10},
              {"start": 20.0, "duration_ms": 100.0, "interval_s": 10}]
    e = snmp_rate_error(walks3)  # (0.3 + 0.5)/10 = 8 %, (0.1 + 0.5)/10 = 6 %
    assert e["n"] == 2 and e["max"] == 8.0 and e["p50"] == 6.0, e
    t = 1e9  # switch samples 10 s apart, arrivals 10 s apart except one sample 100 ms late
    mrows = [{"switch_ts_ns": int((t + 10e9 * k) ), "recv_ns": int(t + 10e9 * k + 5e6 + (1e8 if k == 5 else 0))}
             for k in range(10)]
    e = host_rate_error(mrows, 10)  # two pairs off by 0.1 s: 1 % each, the other 7 pairs 0
    assert e["n"] == 9 and e["max"] == 1.0 and e["p50"] == 0.0, e
    assert host_rate_error([dict(m, recv_ns=m["switch_ts_ns"] + 5) for m in mrows], 10)["max"] == 0.0
    # bursts: 3 messages 20 ms apart per sample, samples 1 s apart -> 5 samples, arrival spacing exact -> 0 error
    burst = [{"switch_ts_ns": int(1e9 + 1e9 * k + 2e7 * j), "recv_ns": int(1e9 + 1e9 * k + 2e7 * j + 5e6)}
             for k in range(5) for j in range(3)]
    assert len(distinct_samples(burst, 1)) == 5 and host_rate_error(burst, 1)["max"] == 0.0

    with tempfile.TemporaryDirectory() as tmp:
        t0 = 1_000_000.0

        def dump(path, rows):
            with open(path, "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")

        def phase(name, meta):
            d = os.path.join(tmp, name)
            os.makedirs(d)
            with open(os.path.join(d, "phase.json"), "w") as f:
                json.dump(dict({"start": t0, "minutes": meta.get("minutes", 60), "end": t0 + 60 * meta.get("minutes", 60)},
                               **{k: v for k, v in meta.items() if k != "minutes"}), f)
            return d

        d = phase("baseline", {"poll": "none"})
        phase_snmp = phase("snmp", {"poll": "v3"})
        walks = [{"dataset": "xe_cpu_stats", "interval_s": 60, "start": t0 + i, "duration_ms": dd, "varbinds": 10,
                  "vlans": None, "errors": 0, "lag_ms": 0.0} for i, dd in enumerate((100.0, 200.0, 300.0, 400.0))]
        dump(os.path.join(phase_snmp, "walks.jsonl"), walks)
        nats = [{"recv_ns": int((t0 + i) * 1e9) + 5_000_000, "switch_ts_ns": int((t0 + i) * 1e9),
                 "subscription": "xe_cpu_stats", "bytes": 1000} for i in range(10)]
        nats = [dict(m, switch_ts_ns=m["switch_ts_ns"] - 770 * 10**9) for m in nats]  # switch clock 770 s slow
        dump(os.path.join(d, "nats.jsonl"), nats)
        dump(os.path.join(phase_snmp, "nats.jsonl"), nats)
        dump(os.path.join(d, "cpu.jsonl"),
             [{"ok": True, "iosd": {"SNMP ENGINE": [0.1, 1.0, 1.0]}, "iosd_total": [5, 4, 3],
               "clock_offset_s": 770.0}] * 2)
        dump(os.path.join(phase_snmp, "cpu.jsonl"),
             [{"ok": True, "iosd": {"SNMP ENGINE": [0.5, 3.0, 2.0]}, "iosd_total": [6, 5, 4]},
              {"ok": False, "error": "timeout"}])
        dump(os.path.join(d, "wire.jsonl"), [{"minute": t0, "class": "gnmi", "dir": "from_switch", "packets": 1,
                                              "bytes": 3600}])
        dump(os.path.join(phase_snmp, "wire.jsonl"), [{"minute": t0, "class": "gnmi", "dir": "from_switch",
                                                       "packets": 2, "bytes": 7200}])
        # collector: 60 s of CPU in 60 s is one core (100 %), then 30 s in 60 s (50 %); memory in MiB
        dump(os.path.join(phase_snmp, "collector.jsonl"),
             [{"ts": t0, "name": "bench-snmp-poller", "usage_usec": 0, "mem_bytes": 30 * 2**20},
              {"ts": t0 + 60, "name": "bench-snmp-poller", "usage_usec": 60_000_000, "mem_bytes": 40 * 2**20},
              {"ts": t0 + 120, "name": "bench-snmp-poller", "usage_usec": 90_000_000, "mem_bytes": 40 * 2**20}])

        # sweep pair at 10 s: MDT bench (10 samples in 120 s, one 100 ms late) and SNMP walks 10.5 s apart
        dm = phase("mdt-10s", {"load": "mdt", "interval_s": 10, "poll": "none", "minutes": 2})
        dump(os.path.join(dm, "bench_mdt.jsonl"),
             [{"recv_ns": m["recv_ns"], "switch_ts_ns": m["switch_ts_ns"], "subscription": "xe_if_stats",
               "bytes": 500} for m in mrows])
        dump(os.path.join(dm, "wire.jsonl"), [{"minute": t0, "class": "gnmi", "dir": "from_switch", "packets": 5,
                                               "bytes": 9000}])
        ds = phase("snmp-10s", {"load": "snmp", "interval_s": 10, "poll": "v3", "minutes": 1})
        dump(os.path.join(ds, "walks.jsonl"),
             [dict(w, dataset="xe_if_stats", varbinds=10, errors=0, vlans=None, lag_ms=1500.0 if i == 2 else 0.0)
              for i, w in enumerate(walks3)])
        dump(os.path.join(ds, "wire.jsonl"), [{"minute": t0, "class": "snmp", "dir": "from_switch", "packets": 6,
                                               "bytes": 6000}])

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
        assert ph["snmp"]["wire_delta_vs_baseline_packets_per_hour"]["gnmi:from_switch"] == 1, ph["snmp"]
        cc = ph["snmp"]["collector"]["bench-snmp-poller"]
        assert cc["cpu_pct_max"] == 100.0 and cc["cpu_pct_mean"] == 75.0 and cc["samples"] == 2, cc
        assert cc["mem_mib_mean"] == 36.7, cc
        # bench MDT: 10 of 12 expected samples, gaps 10 s on the switch clock
        b = ph["mdt-10s"]["bench_mdt"]["xe_if_stats"]
        assert b["samples"] == 10 and b["samples_expected"] == 12 and b["received_pct"] == 83.3, b
        assert b["gap_switch_ms_p50"] == 10000.0 and b["gap_switch_ms_max"] == 10000.0, b
        assert ph["mdt-10s"]["rate_accuracy"]["mdt_host_arrival"]["max"] == 1.0
        assert ph["snmp-10s"]["rate_accuracy"]["snmp"]["max"] == 8.0
        assert ph["snmp-10s"]["snmp"]["xe_if_stats"]["late_pct"] == 33.3
        assert ph["snmp-10s"]["snmp"]["xe_if_stats"]["missed_slots"] == 0
        rows = {(r["interval_s"], r["mode"]): r for r in s["sweep"]}
        assert rows[(10, "mdt")]["received_pct"] == 83.3 and rows[(10, "snmp")]["walk_ms"]["max"] == 300.0
        assert rows[(10, "snmp")]["late_pct"] == 33.3
        # 9000 B in 120 s is 270000 B/h, against 3600 B/h in the baseline
        assert rows[(10, "mdt")]["wire_bytes_per_hour_delta"] == 266400, rows[(10, "mdt")]
        out = text(s)
        assert "xe_cpu_stats" in out and "SNMP ENGINE" in out and "sweep" in out and "MDT bench" in out
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
