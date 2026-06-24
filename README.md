# mdt — Model-Driven Telemetry Pipeline

Collects streaming telemetry from network switches and firewalls over **gNMI dial-in**,
ships it through a **NATS** message bus, and re-publishes it as **Prometheus** metrics
(optionally forwarded on to **Splunk**).

The whole stack is built around [gnmic](https://gnmic.openconfig.net/) and runs as a set
of Docker Compose services.

## Architecture

```
┌─────────────────┐   gNMI dial-in    ┌────────────┐
│  Switches /     │  (subscribe)      │  gnmic-1   │
│  Firewalls      │ ────────────────► │  gnmic-2   │  collectors
│  (XE / NX-OS /  │                   │ (clustered)│
│   PAN-OS / WLC) │                   └─────┬──────┘
└─────────────────┘                         │ publish
                                            ▼  subject: mdt
                ┌──────────┐          ┌────────────┐
                │  consul  │◄────────►│    NATS     │  message bus
                │ (locker/ │ cluster  └─────┬───────┘
                │  leader) │  coord         │ consume
                └──────────┘                ▼
                                     ┌──────────────┐
                                     │ gnmic-output │  :9273 /metrics
                                     │ (Prometheus) │
                                     └──────┬───────┘
                                            │ scrape
                                            ▼
                                     ┌──────────────┐
                                     │ OTel Collector│ ─► Splunk HEC
                                     │ (agent_config)│    (optional)
                                     └──────────────┘
```

1. **Collection** — `gnmic-1` / `gnmic-2` subscribe to each target's gNMI streams
   (interface, CPU, memory, PoE, CDP, MAC, wireless, firewall sessions, …).
2. **Clustering** — Consul acts as the locker so the two collectors split the target
   list between them (one owns each target) and fail over automatically.
3. **Processing** — incoming gNMI updates are normalized/filtered/renamed by gnmic
   event processors, then published to the NATS subject `mdt`.
4. **Output** — `gnmic-output` consumes from NATS and exposes everything as Prometheus
   metrics on `:9273/metrics`.
5. **Forwarding (optional)** — a Splunk OpenTelemetry Collector scrapes that endpoint
   and forwards the metrics to Splunk HEC.

## Files

| File | Purpose |
|------|---------|
| [compose.yaml](compose.yaml) | Main Docker Compose stack: Consul, two clustered gnmic collectors, gnmic output, and NATS. |
| [compose-debug.yaml](compose-debug.yaml) | Same stack with `--debug` logging and a `test.yaml` config — used for troubleshooting. |
| [config/mdt.yaml](config/mdt.yaml) | The core gnmic **collector** config: global auth, clustering, targets, subscriptions, processors, and the NATS output. |
| [config/output.yaml](config/output.yaml) | The gnmic **output** config: reads from NATS and exposes the Prometheus endpoint. |
| [config/ca.pem](config/ca.pem) | CA certificate used to verify the NX-OS switch gRPC endpoints. |
| [agent_config.yaml](agent_config.yaml) | Splunk OpenTelemetry Collector config that scrapes `gnmic-output:9273` and ships metrics to Splunk HEC. |
| [gnmic_env.template](gnmic_env.template) | Template for device credentials. Copy to `gnmic_env` and fill in. |
| `gnmic_env` | Actual device credentials (git-ignored). |

> **Note:** The Compose files mount the gnmic configs from `/opt/gnmic/config` on the
> host (`volumes: /opt/gnmic/config:/app/config`). Place the contents of `config/`
> there, or adjust the volume mount to point at this repo's `config/` directory.

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

### 2. Place the gnmic configs

Copy `config/*` to the host path the Compose files expect:

```bash
sudo mkdir -p /opt/gnmic/config
sudo cp config/* /opt/gnmic/config/
```

### 3. Start the stack

```bash
docker compose up -d
# or, with verbose logging:
docker compose -f compose-debug.yaml up
```

### 4. Verify

- Prometheus metrics: <http://localhost:9273/metrics>
- Consul UI (cluster/target ownership): <http://localhost:8500>
- NATS: `localhost:4222`

### 5. (Optional) Forward to Splunk

Run a Splunk OpenTelemetry Collector with [agent_config.yaml](agent_config.yaml); its
`metrics/mdt` pipeline scrapes the gnmic Prometheus endpoint and exports to Splunk HEC.

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
