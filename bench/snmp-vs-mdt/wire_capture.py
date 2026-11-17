#!/usr/bin/env python3
"""Wire side: reads `tcpdump -e -tt -nn -l -s 96` on stdin (switch traffic only, see run.sh).

Frame length from tcpdump (-e) is the bytes on the wire for the frame, Ethernet header included, FCS excluded.
Classes by switch port: gnmi = tcp 57400, snmp = udp 161, ssh = tcp 22 (the CPU sampler), other.
Writes one JSONL row per minute, class and direction (to_switch / from_switch), with packets and bytes.

  tcpdump ... | wire_capture.py --switch IP --out wire.jsonl
"""
import argparse, collections, json, re, sys

LINE = re.compile(r"^(\d+\.\d+) .*?length (\d+): (\d+\.\d+\.\d+\.\d+)\.(\d+) > (\d+\.\d+\.\d+\.\d+)\.(\d+):")
CLASS = {57400: "gnmi", 161: "snmp", 22: "ssh"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--switch", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cur, agg = None, collections.defaultdict(lambda: [0, 0])

    def flush(out):
        for (cls, direction), (pk, by) in sorted(agg.items()):
            out.write(json.dumps({"minute": cur, "class": cls, "dir": direction, "packets": pk, "bytes": by}) + "\n")
        agg.clear()

    with open(a.out, "a") as out:
        for line in sys.stdin:
            m = LINE.match(line)
            if not m:
                continue
            minute = int(float(m.group(1))) // 60 * 60
            if cur is None:
                cur = minute
            if minute != cur:
                flush(out)
                out.flush()
                cur = minute
            src, sport, dst, dport = m.group(3), int(m.group(4)), m.group(5), int(m.group(6))
            port = dport if dst == a.switch else sport
            cls = CLASS.get(port, "other")
            direction = "from_switch" if src == a.switch else "to_switch"
            c = agg[(cls, direction)]
            c[0] += 1
            c[1] += int(m.group(2))
        if cur is not None:
            flush(out)


if __name__ == "__main__":
    main()
