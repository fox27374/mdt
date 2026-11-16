#!/usr/bin/env python3
"""Switch CPU sampler: one SSH session per sample (switch_ssh.sh), every 60 s until --until.

Per process, 5 s / 1 min / 5 min CPU %:
  iosd      `show processes cpu sorted`: IOSd processes matching WATCH (SNMP, PDU DISPATCHER, gRPC/MDT/telemetry)
  platform  `show processes cpu platform sorted`: Linux-side processes in PLATFORM (gnmib, pubd, ndbmand, ...)
The raw output is kept in each row. The SSH session itself costs switch CPU, and both phases pay that cost.
`show clock` gives the switch's clock offset from the host (clock_offset_s), which analyze.py uses to correct the MDT
latency: the lab switch clock is not NTP-synced.

  cpu_sampler.py --switch IP --until EPOCH --out cpu.jsonl
"""
import argparse, calendar, json, os, re, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
WATCH = re.compile(r"SNMP|PDU DISPATCHER|gRPC|GRPC|MDT|Telemetry|YANG|NETCONF|Trap")
PLATFORM = {"pubd", "ndbmand", "dmiauthd", "gnmib", "confd"}
CLI = "terminal length 0\nshow clock\nshow processes cpu sorted\nshow processes cpu platform sorted\nexit\n"
CLOCK = re.compile(r"^\*?(\d{2}:\d{2}:\d{2}(?:\.\d+)?) (\S+) \w{3} (\w{3}) (\d{1,2}) (\d{4})", re.M)
TOTAL = re.compile(r"five seconds: ([\d.]+)%(?:/[\d.]+%)?[;,] one minute: ([\d.]+)%[;,] five minutes: ([\d.]+)%")
IOS_ROW = re.compile(r"^\s*\d+\s+\d+\s+\d+\s+\d+\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%\s+\S+\s+(.+?)\s*$")


def parse(text):
    """Returns (iosd_total, iosd, platform_total, platform); each process maps to [5s, 1m, 5m] percentages."""
    section, totals = None, {}
    iosd, plat = {}, {}
    for line in text.splitlines():
        if "#show processes cpu platform" in line:
            section = "platform"
            continue
        if "#show processes cpu" in line:
            section = "iosd"
            continue
        if section is None:
            continue
        m = TOTAL.search(line)
        if m and section not in totals:
            totals[section] = [float(x) for x in m.groups()]
        if section == "iosd":
            r = IOS_ROW.match(line)
            if r and WATCH.search(r.group(4)):
                name = r.group(4)
                cur = iosd.setdefault(name, [0.0, 0.0, 0.0])
                for k in range(3):
                    cur[k] += float(r.group(k + 1))
        else:
            tokens = line.split()
            names = [t for t in tokens if t in PLATFORM]
            pcts = [float(p) for p in re.findall(r"([\d.]+)%", line)]
            if names and len(pcts) >= 3:
                cur = plat.setdefault(names[0], [0.0, 0.0, 0.0])
                for k in range(3):
                    cur[k] += pcts[k]
    return totals.get("iosd"), iosd, totals.get("platform"), plat


def switch_epoch(text):
    """Epoch seconds of `show clock` (the switch's own clock, not NTP-synced in the lab: the '*' flag), or None when
    the zone is neither UTC nor the host's zone."""
    m = CLOCK.search(text)
    if not m:
        return None
    hms, tz, mon, day, year = m.groups()
    t = time.strptime(f"{year} {mon} {day} {hms.split('.')[0]}", "%Y %b %d %H:%M:%S")
    frac = float("0" + hms[hms.index("."):]) if "." in hms else 0.0
    if tz == "UTC":
        return calendar.timegm(t) + frac
    if tz in time.tzname:
        return time.mktime(t) + frac
    return None


def sample(ip):
    t = time.time()
    p = subprocess.run([os.path.join(HERE, "switch_ssh.sh"), ip], input=CLI, capture_output=True, text=True, timeout=120)
    t_end = time.time()
    row = {"ts": round(t, 3), "switch": ip, "ok": p.returncode == 0}
    if p.returncode:
        row["error"] = (p.stderr.strip().splitlines() or [f"exit {p.returncode}"])[0]
        return row
    it, iosd, pt, plat = parse(p.stdout)
    se = switch_epoch(p.stdout)
    # host time at the middle of the session minus the switch clock: the offset NATS latency needs to be corrected by
    row.update({"iosd_total": it, "iosd": iosd, "platform_total": pt, "platform": plat,
                "switch_epoch": se, "clock_offset_s": None if se is None else round((t + t_end) / 2 - se, 3),
                "duration_s": round(t_end - t, 2), "raw": p.stdout})
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--switch", required=True)
    ap.add_argument("--until", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--period", type=float, default=60.0)
    a = ap.parse_args()
    nxt = time.time()
    with open(a.out, "a") as out:
        while nxt < a.until:
            out.write(json.dumps(sample(a.switch)) + "\n")
            out.flush()
            nxt += a.period
            time.sleep(max(0.0, nxt - time.time()))


if __name__ == "__main__":
    main()
