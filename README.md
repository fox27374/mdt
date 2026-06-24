# mdt — Model-Driven Telemetry Pipeline

Collects streaming telemetry from network switches and firewalls over **gNMI dial-in**,
ships it through a **NATS** message bus, and re-publishes it as **Prometheus** metrics.

The whole stack is built around [gnmic](https://gnmic.openconfig.net/) and runs as a set
of Podman containers managed with `podman-compose`.

## Architecture

```
┌─────────────────┐   gNMI dial-in    ┌────────────┐
│  Switches /     │    (subscribe)    │  gnmic-1   │
│  Firewalls      │ ────────────────► │  gnmic-2   │  collectors
│  (XE / NX-OS /  │                   │ (clustered)│
│   PAN-OS / WLC) │                   └─────┬──────┘
└─────────────────┘                         │  publish
                                            ▼  subject: mdt
                ┌──────────┐          ┌─────────────┐
                │  consul  │◄────────►│    NATS     │  message bus
                │ (locker/ │ cluster  └─────┬───────┘
                │  leader) │  coord         │ consume
                └──────────┘                ▼
                                     ┌──────────────┐
                                     │ gnmic-output │  :9273 /metrics
                                     │ (Prometheus) │ ─► Prometheus / scraper
                                     └──────────────┘
```

1. **Collection** — `gnmic-1` / `gnmic-2` subscribe to each target's gNMI streams
   (interface, CPU, memory, PoE, CDP, MAC, wireless, firewall sessions, …).
2. **Clustering** — Consul acts as the locker so the two collectors split the target
   list between them (one owns each target) and fail over automatically.
3. **Processing** — incoming gNMI updates are normalized/filtered/renamed by gnmic
   event processors, then published to the NATS subject `mdt`.
4. **Output** — `gnmic-output` consumes from NATS and exposes everything as Prometheus
   metrics on `:9273/metrics`, ready to be scraped by Prometheus (or any compatible
   scraper / OTel collector).

## Files

| File | Purpose |
|------|---------|
| [compose.yaml](compose.yaml) | Main Compose stack: Consul, two clustered gnmic collectors, gnmic output, and NATS. |
| [compose-debug.yaml](compose-debug.yaml) | Identical stack to `compose.yaml` but with `--debug` added to every gnmic command — used for troubleshooting. |
| [config/mdt.yaml](config/mdt.yaml) | The core gnmic **collector** config: global auth, clustering, targets, subscriptions, processors, and the NATS output. |
| [config/output.yaml](config/output.yaml) | The gnmic **output** config: reads from NATS and exposes the Prometheus endpoint. |
| [config/ca.pem](config/ca.pem) | CA certificate used to verify the NX-OS switch gRPC endpoints. |
| [gnmic_env.template](gnmic_env.template) | Template for device credentials. Copy to `gnmic_env` and fill in. |
| `gnmic_env` | Actual device credentials (git-ignored). |

> **Note:** The Compose files mount this repo's `config/` directory straight into the
> containers (`volumes: ./config:/app/config:z`). The `:z` suffix relabels the content
> for SELinux so the rootless Podman containers can read it — harmless on non-SELinux
> hosts.

## Targets & subscriptions

`config/mdt.yaml` defines the devices being monitored and what is collected from each.
Subscriptions are grouped by platform:

- **Cisco IOS-XE switches** (`xe_*`) — interface stats, CPU, memory, PoE, interface
  info, CDP neighbors, MAC table.
- **Cisco NX-OS switches** (`nx_*`) — interface stats/info, CPU load, memory, CDP, MAC
  (uses `config/ca.pem` for TLS).
- **Cisco Catalyst WLC** (`wl_*`) — wireless client signal/SNR/retries, AP utilization
  and noise, client/AP/SSID mappings.
- **Palo Alto firewalls** (`pan_*` / `panos_*`) — interface counters, CPU, session
  stats.

Each subscription streams in `sample` mode at its own interval (30s for interface
counters, up to 1h for slow-changing info like CDP/MAC).

### Processors

`config/mdt.yaml` applies these gnmic event processors before publishing to NATS:

- **`nx-normalize-interfaces`** — reshapes NX-OS interface stats so counters carry an
  `interface_name` tag.
- **`drop-if-stats-interfaces`** — drops virtual/uninteresting interfaces (VLAN,
  loopback, tunnel, port-channel, etc.).
- **`rename-metrics`** — shortens metric names to their leaf (`path-base`).
- **`delete-nx-cdp-fields`** — strips noisy NX-OS CDP fields.

## Usage

### 1. Configure credentials

```bash
cp gnmic_env.template gnmic_env
# edit gnmic_env and set SWITCH_USERNAME/PASSWORD and FW_USERNAME/PASSWORD
```

### 2. Start the stack

```bash
podman-compose up -d
# or, with verbose logging:
podman-compose -f compose-debug.yaml up
```

### 3. Verify

- Prometheus metrics: <http://localhost:9273/metrics>
- Consul UI (cluster/target ownership): <http://localhost:8500>
- NATS: `localhost:4222`

## Ports

| Port | Service | Purpose |
|------|---------|---------|
| 9273 | gnmic-output | Prometheus `/metrics` endpoint |
| 4222 | NATS | Message bus |
| 8500 | Consul | HTTP API / UI |
| 8600/udp | Consul | DNS |
| 8800 | gnmic | Clustering API (internal) |
| 57400 | targets | gNMI dial-in port on switches |
| 9339 | targets | gNMI dial-in port on Palo Alto firewalls |
