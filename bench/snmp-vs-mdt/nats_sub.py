#!/usr/bin/env python3
"""MDT side, no switch load: a passive NATS core subscriber on gnmic's output subject.

gnmic-1/gnmic-2 publish every notification to NATS subject "mdt" (inputs/outputs in gnmic/config); nats:4222 is
published on the test host. This subscriber adds no gnmic subscription and no gnmic work: NATS fans the messages out.
One JSONL row per NATS message that carries events for --mgmt-ip:
  switch_ts_ns  device timestamp of the sample (ns)     recv_ns  when this subscriber got the message (ns)
  latency = recv - switch time, so it includes gnmic processing, NATS, and any clock offset between switch and host.
  bytes = NATS payload size (the JSON event array, not the gRPC/TLS bytes on the wire: see wire_capture.py).

  nats_sub.py --mgmt-ip IP --until EPOCH --out nats.jsonl
"""
import argparse, json, socket, sys, time


def connect(host, port, subject):
    s = socket.create_connection((host, port), timeout=5)
    s.settimeout(1.0)
    s.sendall(b'CONNECT {"verbose":false,"pedantic":false,"name":"mdt-bench","lang":"python3","version":"1",'
              b'"protocol":0}\r\n' + b"SUB " + subject.encode() + b" 1\r\nPING\r\n")
    return s


def events_of(payload):
    data = json.loads(payload)
    return data if isinstance(data, list) else [data]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4222)
    ap.add_argument("--subject", default="mdt")
    ap.add_argument("--mgmt-ip", required=True)
    ap.add_argument("--until", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    s = connect(a.host, a.port, a.subject)
    buf, skipped = b"", 0
    with open(a.out, "a") as out:
        while time.time() < a.until:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                raise SystemExit("nats closed the connection")
            buf += chunk
            while True:
                i = buf.find(b"\r\n")
                if i < 0:
                    break
                line = buf[:i]
                if line.startswith(b"MSG "):
                    size = int(line.split()[-1])
                    if len(buf) < i + 2 + size + 2:
                        break  # payload not complete yet; keep the header
                    payload = buf[i + 2:i + 2 + size]
                    buf = buf[i + 2 + size + 2:]
                    recv_ns = time.time_ns()
                    try:
                        evs = events_of(payload)
                    except ValueError:
                        skipped += 1
                        continue
                    mine = [e for e in evs if isinstance(e, dict) and (
                        (e.get("tags") or {}).get("mgmt_ip") == a.mgmt_ip
                        or str((e.get("tags") or {}).get("source", "")).split(":")[0] == a.mgmt_ip)]
                    if mine:
                        tags = mine[0].get("tags") or {}
                        out.write(json.dumps({
                            "recv_ns": recv_ns,
                            "switch_ts_ns": mine[0].get("timestamp"),
                            "subscription": tags.get("subscription-name") or mine[0].get("name"),
                            "bytes": size, "events": len(mine), "skipped_json": skipped}) + "\n")
                        out.flush()
                else:
                    buf = buf[i + 2:]
                    if line == b"PING":
                        s.sendall(b"PONG\r\n")
                    elif line.startswith(b"-ERR"):
                        print(line.decode(errors="replace"), file=sys.stderr)


if __name__ == "__main__":
    main()
