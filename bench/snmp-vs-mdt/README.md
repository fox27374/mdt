# MDT vs SNMP measurement bench

Measures what it costs to collect the same data from one switch over SNMPv3 (and optionally v2c) and over the
existing gNMI/MDT streaming: collection time, switch CPU per process, bytes and packets on the wire, collector
CPU and memory, and how fresh the data is at the collector.

Scope: one switch, `ibk-lab-sw98` (172.24.80.240, Catalyst IOS-XE 17.18, gnmic dial-in on :57400). Other switches
are a config change (see "Running on another switch"). No Splunk, no dashboard, no report page: the output is
`summary.json` and `summary.txt`.

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
| `podman_stats.py` | host | `podman stats` for gnmic-1, gnmic-2, gnmic-output, nats, bench-snmp-poller, once a minute |
| `run.sh` | host, detached | the phases, starts every collector, writes the run dir, then runs `analyze.py` |
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
<phase>/podman.jsonl     one row per container per minute: CPU %, memory MiB
<phase>/walks.jsonl      snmp phases only: one row per data-set walk
<phase>/poller.err, tcpdump.err   stderr of the poller and capture
```

Re-analyse a finished run with `python3 analyze.py /home/claude/bench/runs/<timestamp>`.

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
- **Collector** (`podman.jsonl`): `podman stats` CPU % (100 = one core) and memory for the gnmic/NATS containers and
  the poller.

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
