#!/usr/bin/env python3
"""SNMP side of the bench: walks one data set per MDT subscription at that subscription's interval.

Runs inside the bench-snmp-poller container (net-snmp snmpbulkwalk, default -Cr10 max-repetitions, -t 5 -r 1).
Serial scheduler: a walk that overruns delays the next one, and lag_ms records how late each walk started.
Credentials come from the environment (SNMP_USER, SNMP_AUTH_PASS, SNMP_PRIV_PASS, SNMP_COMMUNITY) and are never logged.

  poller.py --mode v3|v2c --host IP --until EPOCH --out walks.jsonl     walk until EPOCH
  poller.py --mode v3|v2c --host IP --check                             one sysDescr walk, exit 0 if it answers
"""
import argparse, json, os, re, subprocess, sys, tempfile, time

# data set (= MDT subscription): MDT interval s, MIB subtrees (numeric OIDs), walk once per VLAN?
DATASETS = {
    # IF-MIB ifTable + ifXTable (HC counters), EtherLike dot3 (CRC), RMON etherStats (oversize, undersize, jabber...)
    "xe_if_stats": (30, ["1.3.6.1.2.1.2.2", "1.3.6.1.2.1.31.1.1", "1.3.6.1.2.1.10.7.2", "1.3.6.1.2.1.16.1.1"], False),
    # CISCO-PROCESS-MIB cpmCPUTotalTable
    "xe_cpu_stats": (60, ["1.3.6.1.4.1.9.9.109.1.1.1"], False),
    # CISCO-MEMORY-POOL-MIB ciscoMemoryPoolTable, CISCO-ENHANCED-MEMPOOL-MIB
    "xe_mem_stats": (300, ["1.3.6.1.4.1.9.9.48.1.1.1", "1.3.6.1.4.1.9.9.221.1.1.1"], False),
    # POWER-ETHERNET-MIB (pethPsePortTable, pethMainPseTable), CISCO-POWER-ETHERNET-EXT-MIB
    "xe_poe_stats": (300, ["1.3.6.1.2.1.105", "1.3.6.1.4.1.9.9.402"], False),
    # ifTable (admin/oper/last-change/mtu), dot3 duplex, MAU-MIB (auto-negotiation)
    "xe_if_info": (300, ["1.3.6.1.2.1.2.2", "1.3.6.1.2.1.10.7.2", "1.3.6.1.2.1.26"], False),
    # CISCO-CDP-MIB cdpCacheTable
    "xe_cdp_info": (60, ["1.3.6.1.4.1.9.9.23.1.2.1"], False),
    # BRIDGE-MIB dot1dTpFdbTable per VLAN (context vlan-N / community@N); dot1dBasePortTable once in the default context
    "xe_mac_info": (300, ["1.3.6.1.2.1.17.4.3"], True),
    # IP-MIB ipNetToMediaTable (default context only: MDT covers all VRFs)
    "xe_arp_info": (300, ["1.3.6.1.2.1.4.22"], False),
    # IEEE8023-LAG-MIB, CISCO-VLAN-MEMBERSHIP-MIB vmVlan, CISCO-VTP-MIB vlanTrunkPortTable
    "xe_lag_info": (300, ["1.2.840.10006.300.43", "1.3.6.1.4.1.9.9.68.1.2.2.1.2", "1.3.6.1.4.1.9.9.46.1.6.1.1"], False),
    # ENTITY-MIB entPhysicalTable
    "xe_inventory": (3600, ["1.3.6.1.2.1.47.1.1.1"], False),
}
VLAN_STATE = "1.3.6.1.4.1.9.9.46.1.3.1.1.2"  # CISCO-VTP-MIB vtpVlanState (management domain 1)
BRIDGE_PORTS = "1.3.6.1.2.1.17.1.4"          # BRIDGE-MIB dot1dBasePortTable
SYSDESCR = "1.3.6.1.2.1.1.1"
LINE = re.compile(r"^\.?([\d.]+)\s+(?:=\s*)?(.*)$")  # -Oq prints "oid value"; "oid = value" too


def snmp_conf():
    """net-snmp takes the v3 passphrases from snmp.conf, not from the environment: write them to a private temp dir
    that the container discards on exit, and point SNMPCONFPATH at it."""
    d = tempfile.mkdtemp(prefix="snmpconf-")
    fd = os.open(os.path.join(d, "snmp.conf"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"defSecurityName {os.environ['SNMP_USER']}\ndefAuthType SHA\ndefPrivType AES\n"
                f"defAuthPassphrase {os.environ['SNMP_AUTH_PASS']}\n"
                f"defPrivPassphrase {os.environ['SNMP_PRIV_PASS']}\n")
    os.environ["SNMPCONFPATH"] = d


def auth(mode, host, vlan=None):
    if mode == "v3":
        args = ["-v3", "-l", "authPriv", "-u", os.environ["SNMP_USER"], "-a", "SHA", "-x", "AES"]
        return args + (["-n", f"vlan-{vlan}"] if vlan is not None else [])
    comm = os.environ["SNMP_COMMUNITY"]
    return ["-v2c", "-c", comm if vlan is None else f"{comm}@{vlan}"]


def walk(mode, host, oids, vlan=None):
    """One snmpbulkwalk call over several subtrees. Returns (lines, error or None)."""
    cmd = ["snmpbulkwalk", *auth(mode, host, vlan), "-On", "-Oq", "-m", "", "-t", "5", "-r", "1", host, *oids]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    err = None
    if p.returncode:
        last = [l for l in p.stderr.splitlines() if l.strip()]
        err = last[-1] if last else f"exit {p.returncode}"
    return lines, err


def run_dataset(name, mode, host, due):
    interval, subtrees, per_vlan = DATASETS[name]
    t0 = time.time()
    varbinds, calls, errors, vlans = 0, 0, [], None

    def do(oids, vlan=None):
        nonlocal varbinds, calls
        lines, err = walk(mode, host, oids, vlan)
        calls += 1
        varbinds += len(lines)
        if err:
            errors.append(err)
        return lines

    if per_vlan:
        do([BRIDGE_PORTS])
        vlans = []
        for line in do([VLAN_STATE]):
            m = LINE.match(line)
            val = m.group(2).strip() if m else ""
            if val in ("1", "INTEGER: 1") or val.endswith("(1)"):  # operational
                vlans.append(int(m.group(1).split(".")[-1]))
        # 1002-1005 are the reserved FDDI/Token Ring VLANs: no bridge context, so the walk would only fail
        for v in (v for v in vlans if not 1002 <= v <= 1005):
            do(subtrees, v)
    else:
        do(subtrees)
    t1 = time.time()
    return {"dataset": name, "mode": mode, "interval_s": interval, "due": round(due, 3), "start": round(t0, 3),
            "end": round(t1, 3), "lag_ms": round((t0 - due) * 1000, 1), "duration_ms": round((t1 - t0) * 1000, 1),
            "varbinds": varbinds, "calls": calls, "vlans": None if vlans is None else len(vlans),
            "errors": len(errors), "error_sample": errors[:2], "requests": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["v3", "v2c"], required=True)
    ap.add_argument("--host", required=True)
    ap.add_argument("--until", type=float)
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.mode == "v3":
        snmp_conf()
    if a.check:
        lines, err = walk(a.mode, a.host, [SYSDESCR])
        print("ok" if lines and not err else f"fail: {err or 'no answer'}")
        return 0 if lines and not err else 1
    names = list(DATASETS)
    due = {n: time.time() for n in names}  # every data set is due at start
    with open(a.out, "a") as out:
        while True:
            n = min(names, key=lambda k: due[k])
            if due[n] >= a.until:
                break
            time.sleep(max(0.0, due[n] - time.time()))
            rec = run_dataset(n, a.mode, a.host, due[n])
            out.write(json.dumps(rec) + "\n")
            out.flush()
            due[n] += DATASETS[n][0]
            due[n] = max(due[n], time.time())  # overran: next walk now, lag_ms shows it
    return 0


if __name__ == "__main__":
    sys.exit(main())
