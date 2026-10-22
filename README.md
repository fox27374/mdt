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
                                            ▲
                                            │ query
                                     ┌──────────────┐
                                     │   monitor    │  :8080 web UI
                                     │ (health/     │
                                     │  status)     │
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
5. **Monitoring** — the `monitor` service queries the collectors, NATS server, Consul,
   and the configuration file to assemble a live status view of the entire pipeline,
   exposed as both a web UI and a JSON API on `:8080`.

## Files

| File | Purpose |
|------|---------|
| [compose.yaml](compose.yaml) | Main Compose stack: Consul, two clustered gnmic collectors, gnmic output, NATS, and the OpenTelemetry collector. |
| [compose-debug.yaml](compose-debug.yaml) | Identical stack to `compose.yaml` but with `--debug` added to every gnmic command — used for troubleshooting. |
| [config/mdt.yaml](config/mdt.yaml) | The core gnmic **collector** config: global auth, clustering, targets, subscriptions, processors, and the NATS output. |
| [config/output.yaml](config/output.yaml) | The gnmic **output** config: reads from NATS and exposes the Prometheus endpoint. |
| [config/otel.yaml](config/otel.yaml) | The OpenTelemetry **collector** config: receives Cisco model-driven telemetry (`yang_grpc`), scrapes gnmic-output and host metrics, and exports to Splunk HEC. |
| [config/ca.pem](config/ca.pem) | CA certificate used to verify the NX-OS switch gRPC endpoints. |
| [gnmic_env.template](gnmic_env.template) | Template for device credentials. Copy to `gnmic_env` and fill in. |
| `gnmic_env` | Actual device credentials (git-ignored). |
| [otel_env.template](gnmic/otel_env.template) | Template for the collector's Splunk HEC token (`SPLUNK_HEC_TOKEN`). Copy to `otel_env` and fill in. |
| `otel_env` | Actual Splunk HEC token for the collector (git-ignored). |
| [monitor/](monitor/) | The gnmic-monitor web service: health status and health API for the entire stack. |

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
- **Palo Alto firewalls** (`panos_*`) — interface counters, CPU, session
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
cp otel_env.template otel_env
# edit otel_env and set SPLUNK_HEC_TOKEN
```

`compose.yaml` needs both files: `up` fails if `otel_env` is missing.

### 2. Start the stack

The rootless podman socket that `podman-exporter` mounts must exist. Set it up once per host
(see [Rootless podman socket at boot](#rootless-podman-socket-at-boot)), then:

```bash
PODMAN_UID=$(id -u) XDG_RUNTIME_DIR=/run/user/$(id -u) podman-compose --in-pod false up -d
# or, with verbose logging:
PODMAN_UID=$(id -u) XDG_RUNTIME_DIR=/run/user/$(id -u) podman-compose --in-pod false -f compose-debug.yaml up
```

Why the flags: `podman-compose` puts all services in one pod by default, but
`podman-exporter` sets `userns_mode: keep-id`, and podman rejects `--userns` inside a
pod (`--userns and --pod cannot be set together`). `--in-pod false` runs the services
without a pod. `PODMAN_UID` and `XDG_RUNTIME_DIR` point `podman-exporter` at your rootless
podman socket (see [Container metrics](#container-metrics)).

#### Replacing a single service

`podman-compose up` fails with a name-in-use error if the service's container already
exists. To replace one service, remove its container first, then bring up only that service.
Podman refuses to remove a container that other containers depend on, so remove the
dependents too and recreate them. The `monitor` service (container `gnmic-monitor`) depends on
`podman-exporter`:

```bash
podman rm -f gnmic-monitor
podman rm -f podman-exporter
PODMAN_UID=$(id -u) XDG_RUNTIME_DIR=/run/user/$(id -u) podman-compose --in-pod false up -d --no-deps podman-exporter monitor
```

After a `podman-compose down`, the DNS resolver for the network can go stale (containers
cannot resolve each other). Fix it by killing `aardvark-dns` and removing its state directory
`/run/user/$(id -u)/containers/networks/aardvark-dns` (`rm -rf`, it is a directory), then bring the
stack up again:

```bash
pkill -x aardvark-dns
rm -rf /run/user/$(id -u)/containers/networks/aardvark-dns
PODMAN_UID=$(id -u) XDG_RUNTIME_DIR=/run/user/$(id -u) podman-compose --in-pod false up -d
```

### 3. Verify

- Prometheus metrics: <http://localhost:9273/metrics>
- Consul UI (cluster/target ownership): <http://localhost:8500>
- NATS: `localhost:4222`

## OpenTelemetry collector

The `otel-collector` service runs the pinned `otel/opentelemetry-collector-contrib:0.154.0` image with `config/otel.yaml`. It:

- receives network device telemetry over gRPC on host port **57000** (`yang_grpc`, the device dial-out target),
- scrapes gnmic-output (`gnmic-output:9273`) and collects host metrics from the host root mounted at `/hostfs`,
- exports the metrics to Splunk HEC. The token is read from `SPLUNK_HEC_TOKEN` in `gnmic/otel_env` (git-ignored).

Inside the compose network it serves the health check on `:13133` and its own Prometheus self-telemetry on `:8888/metrics`. The monitor reads both (see [Environment variables](#environment-variables)).

## Monitoring

The `monitor` service provides a web UI and JSON API for inspecting the health and status of the entire MDT pipeline. Access it at <http://localhost:8080> or query the JSON API at `/api/status`.

The UI and API display:

- **Component health** — live status of Consul, NATS server, NATS consumer, gnmic-output, each gnmic collector (gnmic-1, gnmic-2), and the `otel-collector` (see [OpenTelemetry collector check](#opentelemetry-collector-check)).
- **Target list** — all targets from the configuration with their owner collector and current status.
- **Subscription status** — each target's subscriptions with their last-seen timestamp and data-point count.

Status values are:

- **OK** — healthy, receiving data at the expected rate.
- **WAITING** — component or subscription starting up.
- **STALE** — no new data received for 3 × the subscription's sample interval (minimum 2 minutes).
- **NO_DATA** — subscription configured but never received a data point.
- **ERROR** — configuration error or communication failure.

### Environment variables

The monitor reads these environment variables; defaults shown are used if unset:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LISTEN` | `:8080` | HTTP listen address |
| `COLLECTORS` | `gnmic-1=http://gnmic-1:8800,gnmic-2=http://gnmic-2:8800` | Comma-separated list of collectors and their APIs |
| `NATS_URL` | `nats://nats:4222` | NATS server URL |
| `NATS_SUBJECT` | `mdt` | NATS subject being consumed |
| `NATS_MON_URL` | `http://nats:8222` | NATS monitoring API URL |
| `CONSUL_URL` | `http://consul:8500` | Consul HTTP API URL |
| `OUTPUT_URL` | `http://gnmic-output:9273/metrics` | gnmic-output metrics endpoint |
| `MDT_CONFIG` | `/app/config/mdt.yaml` | Path to gnmic collector configuration |
| `POLL_INTERVAL` | `15s` | How often to query components for status updates |
| `LOCAL_HOST_NAME` | `docker-host` | Display name of the local host; used in the default `HOSTS` and `CONTAINER_EXPORTERS`. Compose sets it from `MONITOR_HOST_NAME` |
| `LOCAL_CONTAINER_EXPORTER` | (empty) | Set to any non-empty value to default `CONTAINER_EXPORTERS` to the local podman-exporter on port 9882 (compose.yaml sets it) |
| `HOSTS` | `<LOCAL_HOST_NAME>=http://host.containers.internal:9100` | Comma-separated list of hosts to monitor; format: `name=http://host:9100,...` |
| `OTEL_HEALTH_URL` | `http://otel-collector:13133/` | OpenTelemetry collector health_check endpoint. Set to empty to skip this check |
| `OTEL_METRICS_URL` | `http://otel-collector:8888/metrics` | OpenTelemetry collector self-telemetry (Prometheus). Set to empty to skip this check. Both empty turns the collector check and the System tab panel off |
| `OTEL_FAIL_PCT` | `1` | Export failure threshold (%): failed / (sent + failed) metric points since the previous poll. At or above, the collector is not OK |
| `OTEL_QUEUE_PCT` | `80` | Exporter retry queue threshold (%): used / capacity. At or above, the collector is not OK |
| `HOST_NIC_INCLUDE` | `^(en\|eth\|em\|bond\|ib)[a-z0-9]*$` | Regex pattern for network interfaces to include |
| `CONTAINER_EXPORTERS` | (empty, no container rows) | Optional. Comma-separated `name=url` of prometheus-podman-exporter endpoints; `name` must match a `HOSTS` name. Unset: no container rows, unless `LOCAL_CONTAINER_EXPORTER` is set |
| `CONTAINER_INCLUDE` | (empty, all containers) | Optional regex; only containers whose name matches are shown |
| `HOST_CPU_WARN` / `HOST_CPU_CRIT` | `80` / `95` | CPU usage thresholds (%) |
| `HOST_MEM_WARN` / `HOST_MEM_CRIT` | `85` / `95` | Memory usage thresholds (%) |
| `HOST_DISK_WARN` / `HOST_DISK_CRIT` | `80` / `90` | Disk usage thresholds (%) |
| `HOST_NET_WARN` / `HOST_NET_CRIT` | `70` / `90` | Network utilization thresholds (%) |

#### OpenTelemetry collector check

The `otel-collector` component is OK only when all of these hold:

- the health endpoint returns HTTP 200 with status `Server available`,
- the self-telemetry scrape succeeds,
- the export failure ratio since the previous poll is below `OTEL_FAIL_PCT` (no metric points sent or failed in that interval counts as no failure),
- every exporter's retry queue is below `OTEL_QUEUE_PCT`.

On the first poll there is no previous sample, so only health and queue are judged. The detail shows the first failing reason, or a short summary such as `sent 1200 points/s, 0.0% failed, queue 0%`.

The System tab shows an **OpenTelemetry collector** panel, present only when the metrics scrape works: a summary line (RSS, CPU, uptime), one row per exporter (sent/s, failed/s, queue used out of capacity) and one row per receiver (accepted/s, refused/s, failed/s). Rates show `n/a` until there are two polls.

### Host metrics

When `HOSTS` is configured, the monitor scrapes node_exporter instances and displays host metrics in the web UI. Each host shows:

- **CPU** — usage averaged over 5 minutes
- **Memory** — memory used as a percentage of total
- **Disks** — used percentage for each real filesystem (excluding virtual/temporary filesystems)
- **NICs** — utilization as a percentage of link speed, averaged over 1 minute, for each physical network interface (matched by the `HOST_NIC_INCLUDE` regex)

When `CONTAINER_EXPORTERS` is set for a host, its running containers are listed under the host (expand the host row). Each container shows:

- **CPU** — percent of one core, computed from the change in CPU time since the previous poll (can exceed 100% on multi-core containers). `n/a` on the first poll
- **Memory** — memory in use; with a percentage of the limit when the container has a `--memory` limit

Container values have no thresholds or levels.

Each metric has one of four levels:

- **OK** — value below the `WARN` threshold
- **WARN** — value at or above the `WARN` threshold, but below the `CRIT` threshold
- **CRIT** — value at or above the `CRIT` threshold
- **UNKNOWN** — metric data not available

A host's overall level is the worst of its metrics.

#### Monitoring an additional host

To monitor a host other than `docker-host`, run `node_exporter` on that host (for example, version v1.12.1 from `docker.io/prom/node-exporter`), then add it to `HOSTS`:

```bash
export MONITOR_HOSTS="$(hostname)=http://host.containers.internal:9100,other-host=http://10.0.0.2:9100"
podman-compose up -d
```

To rename the local host's row and its container rows without overriding `HOSTS` or `CONTAINER_EXPORTERS`, set `MONITOR_HOST_NAME` (for example `export MONITOR_HOST_NAME=$(hostname)`). `MONITOR_HOSTS` and `MONITOR_CONTAINER_EXPORTERS` fully override the name when set.

#### Container metrics

The compose stack runs `prometheus-podman-exporter` (service `podman-exporter`, port 9882) against the rootless podman socket of the host user. Set `PODMAN_UID` to the output of `id -u` on the host (default 1000), and make sure the podman socket exists at `${XDG_RUNTIME_DIR}/podman/podman.sock`. The monitor reads it through `CONTAINER_EXPORTERS`, which the compose file enables for the local host (`<MONITOR_HOST_NAME or docker-host>=http://host.containers.internal:9882`). Override with `MONITOR_CONTAINER_EXPORTERS`.

`podman-exporter` has `restart: unless-stopped`, so if the socket appears after the container has started, the exporter retries on its own and no restart is needed.

#### Rootless podman socket at boot

Optional host prerequisite, not managed by this repo: the rootless podman API socket must exist at every boot. If your host already provides it (for example `systemctl --user enable --now podman.socket`), nothing more is needed. Otherwise install [`scripts/podman-api.service`](scripts/podman-api.service) once, as the stack user (uid of `PODMAN_UID`), from a real login session (ssh or `machinectl shell`), not `su`:

```bash
mkdir -p ~/.config/systemd/user
cp scripts/podman-api.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now podman-api.service
sudo loginctl enable-linger "$(whoami)"
```

Do not enable `podman.socket` as well; both bind the same path. Check with `curl --unix-socket ${XDG_RUNTIME_DIR}/podman/podman.sock http://d/v5.0.0/libpod/_ping` (expect `OK`). If the path exists as an empty directory (left by a container start before the socket existed), stop the service, `rmdir` it and start the service again. Without the socket the stack still runs; the monitor just shows no container rows.

#### Security

`node_exporter` listens unauthenticated on port 9100 on all interfaces of the host. On production networks, restrict access to port 9100 to the monitor's address using the host firewall. `prometheus-podman-exporter` listens the same way on port 9882 and exposes container names and resource use; restrict it too.

## Ports

| Port | Service | Purpose |
|------|---------|---------|
| 9273 | gnmic-output | Prometheus `/metrics` endpoint |
| 57000 | otel-collector | Device telemetry (`yang_grpc`) |
| 13133 | otel-collector | Health check (internal to the compose network) |
| 8888 | otel-collector | Collector self-telemetry, `/metrics` (internal) |
| 9100 | node-exporter | Host metrics endpoint |
| 9882 | podman-exporter | Container metrics endpoint |
| 4222 | NATS | Message bus |
| 8500 | Consul | HTTP API / UI |
| 8600/udp | Consul | DNS |
| 8800 | gnmic | Clustering API (internal) |
| 8080 | monitor | Monitor web UI and `/api/status` |
| 57400 | targets | gNMI dial-in port on switches |
| 9339 | targets | gNMI dial-in port on Palo Alto firewalls |
