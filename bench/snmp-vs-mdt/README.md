# MDT vs SNMP measurement bench

Measures what it costs to collect the same data from one switch over SNMPv3 (and optionally v2c) and over the
existing gNMI/MDT streaming: collection time, switch CPU per process, bytes and packets on the wire, collector
CPU and memory, and how fresh the data is at the collector.

Scope: one switch, `ibk-lab-sw98` (172.24.80.240, Catalyst IOS-XE 17.18, gnmic dial-in on :57400). Other switches
are a config change (see "Running on another switch"). No Splunk, no dashboard, no report page: the output is
`summary.json` and `summary.txt`.

Report of the 16 Nov 2026 runs: [REPORT.md](REPORT.md).

## What runs where

Everything runs on the test host `kof-ibk-debian4` (172.24.89.69, user `claude`). The switches are reachable only
from there. The bench is deployed to `/home/claude/bench/snmp-vs-mdt` (not the `mdthost` work copy, which is wiped on
every `mdthost` call).

| File | Runs on | Does |
|---|---|---|
| `switch-snmp.sh` | host | `apply` / `remove` / `show` the SNMP config on the switch (ACL: test host only) |
| `switch_ssh.sh` | host | IOS-XE CLI over SSH, same method as `scripts/swcli`, used by the sampler and the SNMP script |
| `Dockerfile`, `poller.py` | container `bench-snmp-poller` | net-snmp `snmpbulkwalk`, one walk per MDT data set at its interval |
| `nats_sub.py` | host | passive NATS subscriber on gnmic's `mdt` subject, records sw98 messages |
| `cpu_sampler.py` | host | one SSH session per minute: switch clock and CPU per process |
| `wire_capture.py` | host | reads `tcpdump` on stdin, bytes and packets per minute per class and direction |
| `collector_cpu.py` | host | cgroup v2 CPU time and memory of gnmic-1, gnmic-2, gnmic-output, nats, bench-gnmic, bench-snmp-poller, once a minute |
| `run.sh` | host, detached | the phases, starts every collector, writes the run dir, then runs `analyze.py` |
| `stress.sh` | host, detached | the stress run: sweep, mdt-double and baseline phases (see "Stress run") |
| `gen_gnmic.py` | host | writes the bench gnmic config from the live `mdt.yaml` (stress run) |
| `bench_tail.py` | host | stamps each line of the bench gnmic file output with its arrival time (stress run) |
| `analyze.py` | host | run dir to `summary.json` and `summary.txt`; `--selftest` checks the arithmetic |

## Prerequisites

- Test host: `podman`, `podman-compose` stack (the live gnmic stack is not touched), `tcpdump`, `python3` (3.9+),
  passwordless `sudo` for `tcpdump` and `timeout`, `openssl`, `/opt/gnmic/gnmic_env` (read only, for the switch login).
- The gnmic stack publishes NATS on host port 4222 (`gnmic/compose.yaml`); the subscriber reads subject `mdt`.
- Deploy: from the repo root on the laptop

  ```
  tar -C bench/snmp-vs-mdt --exclude=__pycache__ -cf - . | ssh claude@172.24.89.69 \
    'mkdir -p /home/claude/bench/snmp-vs-mdt && tar -C /home/claude/bench/snmp-vs-mdt -xf - && chmod +x /home/claude/bench/snmp-vs-mdt/*.sh /home/claude/bench/snmp-vs-mdt/*.py'
  ```

## Switch SNMP config

`switch-snmp.sh apply` pushes exactly this, all names prefixed `BENCH-` or `benchsnmp`:

```
ip access-list standard BENCH-SNMP            ! 10 permit 172.24.89.69 (the test host) only
snmp-server view BENCH-VIEW iso included       ! read-only
snmp-server group BENCH-V3 v3 priv read BENCH-VIEW access BENCH-SNMP
snmp-server group BENCH-V3 v3 priv context vlan- match prefix read BENCH-VIEW access BENCH-SNMP
snmp-server user benchsnmp BENCH-V3 v3 auth sha <auth> priv aes 128 <priv> access BENCH-SNMP
snmp-server community <community> view BENCH-VIEW RO BENCH-SNMP
```

- Credentials are random, generated on the first apply, and stored only in `/home/claude/bench/snmp_env` (mode 600
  on the host). They are never printed and never in git. The switch's CLI echoes typed commands, so the script
  discards the config session output and prints only the switch's view of the user, group and ACL.
- The `vlan-` context line lets SNMPv3 read the per-VLAN bridge tables (`vlan-<id>`, which is how IOS-XE indexes
  them). Without it the switch answers "authorizationError" for those contexts.
- `show`, `apply`, `remove`:

  ```
  scripts/mdthost 'bench/snmp-vs-mdt/switch-snmp.sh apply'     # from the repo; or run it in /home/claude/bench/snmp-vs-mdt
  ```
- `remove` takes exactly the same lines off again. Run it after the report.
- Nothing else is changed, and `write memory` is not run.

## Running

Smoke run (5 min baseline + 5 min SNMP):

```
ssh claude@172.24.89.69 'cd /home/claude/bench/snmp-vs-mdt && setsid nohup ./run.sh --baseline-min 5 --snmp-min 5 >/home/claude/bench/smoke-launch.log 2>&1 </dev/null &'
```

Full run, 60 min each (about 2 h), detached so it survives the session:

```
ssh claude@172.24.89.69 'cd /home/claude/bench/snmp-vs-mdt && setsid nohup ./run.sh >/home/claude/bench/full-launch.log 2>&1 </dev/null &'
```

Options: `--baseline-min N`, `--snmp-min N`, `--v2c` (adds an `snmp-v2c` phase, needs the community in the config),
`--v2c-min N` (default: `--snmp-min`). `run.sh` checks SNMPv3 (and v2c with `--v2c`) before starting and aborts if
the switch does not answer.

Progress: `/home/claude/bench/runs/<timestamp>/run.log`. Results: `/home/claude/bench/runs/<timestamp>/`:

```
run.json  run.log  summary.json  summary.txt
<phase>/phase.json       start, end, poll mode
<phase>/nats.jsonl       one row per NATS message for sw98: switch and receive time, bytes, subscription
<phase>/cpu.jsonl        one row per minute: switch clock offset, CPU per process (raw output kept)
<phase>/wire.jsonl       one row per minute, class (gnmi/snmp/ssh/other) and direction: packets, bytes
<phase>/collector.jsonl  one row per container per minute: cgroup CPU time and memory (raw counters)
<phase>/walks.jsonl      snmp phases only: one row per data-set walk
<phase>/poller.err, tcpdump.err   stderr of the poller and capture
```

Re-analyse a finished run with `python3 analyze.py /home/claude/bench/runs/<timestamp>`.

## Stress run

`stress.sh` answers where MDT beats SNMP, and at what cost. Same switch, same test host, same collectors as `run.sh`,
plus a bench gNMI client. It is a separate script; `run.sh` is unchanged apart from the collector.

Phases, one after another, never two bench loads at once:

| Phase | Load | Length (default) |
|---|---|---|
| `baseline` | none (live stack only) | 30 min |
| `mdt-double` | bench gnmic: an identical second copy of all ten sw98 subscriptions | 30 min |
| `mdt-30s`, `mdt-10s`, `mdt-5s`, `mdt-1s` | bench gnmic: `xe_if_stats` only, at that sample interval | 15 min each |
| `snmp-30s`, `snmp-10s`, `snmp-5s`, `snmp-1s` | SNMPv3 poller: `xe_if_stats` only, walked at that interval | 15 min each |

Launch (about 3 h for the defaults; `--baseline-min`, `--double-min` and `--step-min` set the lengths, a 2-minute smoke
run is `--baseline-min 2 --double-min 2 --step-min 2`):

```
ssh claude@172.24.89.69 'cd /home/claude/bench/snmp-vs-mdt && setsid nohup ./stress.sh >/home/claude/bench/stress-launch.log 2>&1 </dev/null &'
```

Progress: `/home/claude/bench/runs/stress-<timestamp>/run.log`. Results in the same run dir: `summary.json`,
`summary.txt`, and per phase `phase.json` (load, interval_s, start, end), `nats.jsonl` (live stream, as in `run.sh`),
`cpu.jsonl`, `wire.jsonl`, `collector.jsonl`, plus for the bench phases:

```
<phase>/gnmic.json         the bench gnmic config (generated; no credentials, it reads ${SWITCH_USERNAME} etc.)
<phase>/bench_events.jsonl gnmic file output, event format: one JSON array per gNMI message (the bench's own data)
<phase>/bench_mdt.jsonl    one row per message: arrival time on this host, switch timestamp, subscription, bytes
<phase>/walks.jsonl        snmp phases: one row per walk of xe_if_stats (the only data set walked)
```

**Bench gnmic.** Container `bench-gnmic`, image `ghcr.io/openconfig/gnmic:0.46.0` (the live image), `--network host`,
credentials from `/opt/gnmic/gnmic_env` through `--env-file` (read only). One target, sw98, with the subscriptions
copied from the live `gnmic/config/mdt.yaml` on the host (`BENCH_MDT_YAML`, default
`/home/claude/mdt/gnmic/config/mdt.yaml`, the file gnmic-1 runs). Output is a file, not NATS: nothing is published to
the live `mdt` subject, so Splunk and the dashboards do not see the bench. The file output has no processors, so the
bench writes the raw gNMI events, not the NATS payload the live stack publishes. Each phase removes the containers on
exit (and on error, through a trap).

**Sweep method.** `mdt-<N>s` and `snmp-<N>s` load the same data set (`xe_if_stats`: the ten interface counters and
error breakdown, as in `mdt.yaml`) at the same interval. Per interval, `summary.txt` has one block for MDT and one for
SNMP:

- switch CPU deltas vs baseline (1-min column) for IOSd total, platform total, and the process rows that carry the load
  (MDT: ndbmand, pubd, gnmib; SNMP: SNMP ENGINE, IP SNMP, PDU DISPATCHER);
- wire bytes/h and packets/h deltas vs baseline for the class that carries the load (`gnmi` for MDT, `snmp` for SNMP);
  the bench gnmic shares TCP 57400 with the live stack, so its wire cost is the gnmi delta, and the live stream is part
  of the baseline;
- collector CPU of the bench container (`bench-gnmic` or `bench-snmp-poller`), mean and max, 100 = one core;
- messages received vs expected. MDT: samples counted as bursts (below), against phase length / interval. SNMP:
  walks against phase length / interval;
- SNMP: walk duration p50/p95/max, late walks (started more than 10% of the interval late) and missed slots (a gap of k
  intervals between two walk starts misses k-1 slots).

A sample from the switch arrives as a burst of gNMI messages a few tens of milliseconds apart (IOS-XE splits one sample
into several messages, each with a different group of leaves). `analyze.py` therefore counts a new sample only after a gap
longer than half the nominal interval. Measured on sw98 at 1 s: a burst every second, about five messages per burst.

**mdt-double.** The second copy of all ten subscriptions (`<name>_copy`, same paths, modes and intervals) runs for 30
min against a 30-min baseline. The deltas are the cost of one MDT set of sw98 subscriptions: the switch CPU of ndbmand,
pubd, gnmib, IOSd and platform, and the gnmi wire rates.

**Rate accuracy.** Computed in `analyze.py`, no extra phase. Two error bounds, in percent of the rate, per interval:

- SNMP, on host time only (SNMP has no sample timestamp). For each walk after the first:
  `(duration_i + |start_i - start_(i-1) - N|) / N`, where `N` is the nominal interval. `duration_i` is the spread of
  the counter read; the gap term is the host-clock start spacing against nominal.
- MDT, on host arrival times (what a collector without switch timestamps would use). For each sample after the first:
  `|(arrival_i - arrival_(i-1)) - (switch_i - switch_(i-1))| / N`. The switch spacing is the true spacing, so a rate
  on switch timestamps has 0 error by construction. Constant transport delay cancels in the difference; the bound is
  the arrival jitter.

The same two bounds are reported for the existing run `20261116-103628` (the 30 s SNMP phase against the live NATS
stream, nominal 30 s) by re-running `analyze.py` on that run dir.

**Caveats.**
- The `1 s` numbers are as measured on this switch: it accepted a 1 s sample interval, and the bench counted bursts,
  not switch-side sample times. Sample loss at 1 s (missing bursts) is in the received count, not corrected.
- Collector CPU of `bench-gnmic` is the gnmic cost without the NATS publish and without processors, so it is a lower
  bound on what the live gnmic pays per subscription. The MDT figures are switch CPU and wire, which do not depend on
  this.
- The sweep runs 15 min per step. The 1-min CPU column of 15 samples is noisy; compare the sweep steps with the
  baseline, not with each other.
- The live stack keeps running throughout as background. The `nats.jsonl` of every phase is the live stream: its rate
  should not move between phases (a check that the bench did not publish to `mdt`).

## Data sets and MIB mapping

Each MDT subscription in `gnmic/config/mdt.yaml` on sw98 is one data set. The poller walks it at the same interval
(`DATASETS` in `poller.py`). Each walk is a full subtree walk: SNMP has no per-leaf subscription, so the cost of
the whole table is what it costs.

| MDT subscription | MDT interval | SNMP subtrees walked | Notes |
|---|---|---|---|
| `xe_if_stats` | 30 s | IF-MIB ifTable `1.3.6.1.2.1.2.2`, ifXTable `.31.1.1`, EtherLike `.10.7.2`, RMON etherStats `.16.1.1` | HC counters from ifXTable; CRC from dot3Stats; oversize/undersize/jabber from etherStats |
| `xe_cpu_stats` | 60 s | CISCO-PROCESS-MIB cpmCPUTotalTable `.9.9.109.1.1.1` | |
| `xe_mem_stats` | 300 s | CISCO-MEMORY-POOL `.9.9.48.1.1.1`, CISCO-ENHANCED-MEMPOOL `.9.9.221.1.1.1` | |
| `xe_poe_stats` | 300 s | POWER-ETHERNET-MIB `1.3.6.1.2.1.105`, CISCO-POWER-ETHERNET-EXT `.9.9.402` | |
| `xe_if_info` | 300 s | ifTable `.2.2`, dot3 duplex `.10.7.2`, MAU-MIB `.26` | admin/oper/last-change, duplex, auto-negotiation, MTU |
| `xe_cdp_info` | 60 s | CISCO-CDP-MIB cdpCacheTable `.9.9.23.1.2.1` | |
| `xe_mac_info` | 300 s | BRIDGE-MIB dot1dTpFdbTable `1.3.6.1.2.1.17.4.3` per VLAN (context `vlan-<id>`, v2c `community@<id>`), dot1dBasePortTable `.17.1.4` once per walk | VLANs from CISCO-VTP vtpVlanState (operational); reserved 1002-1005 skipped |
| `xe_arp_info` | 300 s | IP-MIB ipNetToMediaTable `1.3.6.1.2.1.4.22` | default context only; MDT covers all VRFs |
| `xe_lag_info` | 300 s | IEEE8023-LAG-MIB `1.2.840.10006.300.43`, CISCO-VLAN-MEMBERSHIP `.9.9.68.1.2.2.1.2`, CISCO-VTP vlanTrunkPortTable `.9.9.46.1.6.1` | |
| `xe_inventory` | 3600 s | ENTITY-MIB entPhysicalTable `1.3.6.1.2.1.47.1.1.1` | |

Walks are serial in one poller process. Each data set is due at start and then every interval. A walk that runs
late delays the next one, and `lag_ms` records how late it started, so an overloaded poller shows up as lag.

Walk settings: `snmpbulkwalk -On -Oq -m "" -t 5 -r 1`, default max-repetitions (10). Larger max-repetitions would
cut the request count, so the numbers here are for the defaults.

## Outputs and what they mean

- **SNMP walks** (`walks.jsonl`): start, end, duration_ms, varbinds, calls, VLAN count, errors and the first error.
  `requests` is null: `snmpbulkwalk` does not report the request count. Packet counts come from the wire capture.
- **MDT latency** (`nats.jsonl`): host receive time minus the switch sample time (`timestamp` in the gnmic event).
  This is the time from the switch sampling to the gnmic output on NATS, as a subscriber sees it. It includes gnmic
  processing and NATS, and it is corrected by the switch clock offset (see below).
- **Switch CPU** (`cpu.jsonl`): `show processes cpu sorted` for IOSd processes matching SNMP, PDU DISPATCHER and
  gRPC/MDT/telemetry, and `show processes cpu platform sorted` for pubd, ndbmand, dmiauthd, gnmib and confd. Values
  are 5 s, 1 min and 5 min percent. `analyze.py` reports the 1-min column (mean and max) and the delta against
  baseline.
- **Wire** (`wire.jsonl`): `tcpdump -e` frame length, Ethernet header included, for traffic to and from 172.24.80.240
  on TCP 57400 (gNMI), UDP 161 (SNMP) and TCP 22 (the CPU sampler's SSH).
- **Collector** (`collector.jsonl`): cgroup v2 `cpu.stat` usage_usec and `memory.current` for the gnmic/NATS containers
  and the poller, read once a minute through the container's init PID. `analyze.py` turns the difference between two
  minutes into CPU % (100 = one core). This replaces `podman stats`, whose CPU % is an average since container start.

## Caveats

- **Clock offset.** The lab switch clock is not NTP-synced: `show clock` showed the switch about 13 minutes behind
  the host (the `*` marks the unsynced clock). The MDT latency is corrected with the median offset of the phase,
  taken from the `show clock` in each CPU sample. The offset is measured to about a second, and its min and max
  are reported. Without that correction the latency is meaningless.
- **Latency includes gnmic.** The MDT latency is measured at the NATS subscriber, so it includes the gnmic
  processing and output. It is not the switch-to-gNMI-client latency.
- **The sampler costs both phases.** Each CPU sample is an SSH login and two `show` commands on the switch, once a
  minute, in the baseline and the SNMP phases alike. The wire capture counts that SSH traffic in its own class.
  Absolute switch CPU is therefore a little higher than with no sampler; the deltas between phases are the signal.
- **Walk timing is not the whole SNMP cost.** Serial walks in one process: a walk that overruns delays the next data
  set, and `lag_ms` shows it. The SNMP-side CPU on the switch is in the `snmp` process rows of `cpu.jsonl`.
- **v3 context walks.** Each VLAN is a separate context walk. Its cost grows with VLAN count.
- **ARP covers the global table only**, as noted above. The MDT subscription covers all VRFs.
- **Lab-specific values.** Only the IOSd processes in `cpu_sampler.py` are watched; other processes are in the raw
  output. The lab switch has no port-channels, so the LAG walk returns one row (the table timestamp).
- **Interface errors.** The lab has intentional interface errors. They are in the data and are not a problem here.
- **One switch, one day.** The results are for this switch, this IOS-XE version and this traffic. Do not generalise
  to other platforms without running the bench there.

## Running on another switch

Set `BENCH_SWITCH=<ip>` for `run.sh` and `switch-snmp.sh`. `BENCH_SRC_IP` sets the one address the ACL permits (the
test host). The `mgmt_ip` filter in `nats_sub.py` is the `--mgmt-ip` argument (set by `run.sh`). The data-set mapping
assumes the same subscriptions as sw98: check the subscriptions in `gnmic/config/mdt.yaml` for that switch and
adjust `DATASETS` in `poller.py` if they differ. Platform-specific MIB subtrees (CISCO-VTP, CISCO-PROCESS) need to
exist on that platform. Note that `switch-snmp.sh` uses the same `BENCH-*` names on every switch.

## Teardown

`scripts/mdthost 'bench/snmp-vs-mdt/switch-snmp.sh remove'`, then remove `/home/claude/bench/snmp_env` if the bench is
not going to run again. Run output stays in `/home/claude/bench/runs`.
