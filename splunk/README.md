# MDT Infrastructure Monitoring (Splunk app)

Dashboards for the switch and wireless telemetry collected by `gnmic/` and the OTel collector (`gnmic/config/otel.yaml`).
App folder: `splunk/mdt_infra_monitoring/`. Requires Splunk 10.4 or later (Dashboard Studio, custom viz).

## Requirements

- **Indexes**
  - `cisco_metrics`: a metrics index (all `mstats` searches).
  - `cisco_syslog`: an events index (switch syslog, Switch Details and Interface Details logs).
- **Dependency**: the Splunkbase app **Network Diagram Viz** (app id `network-diagram-viz`). Network Overview draws its
  topology with it. Without it, Network Overview shows a notice and an empty diagram; the other dashboards work.
  The port faceplate visualization ships in the app, no dependency.

## Install

Folder copy (any Splunk host):

```bash
cp -R splunk/mdt_infra_monitoring $SPLUNK_HOME/etc/apps/
$SPLUNK_HOME/bin/splunk restart
```

Or a package: run `scripts/splunk-package` (writes `mdt_infra_monitoring.spl` to the repo root, or to a path you give),
then in Splunk Web go to **Apps > Manage Apps > Install app from file**, pick the `.spl`, and restart when asked.

The built visualization bundle is committed, so installing needs no Node.js.

## Index names

Every search reads the indexes through two macros in `default/macros.conf`:

| Macro | Default definition |
|-------|--------------------|
| `mdt_metrics_index` | `index=cisco_metrics` |
| `mdt_syslog_index` | `index=cisco_syslog` |

To use other index names, do not edit the app. Override the macros in `local/macros.conf` of the app, or in
**Settings > Advanced search > Search macros** (`mdt_metrics_index`, `mdt_syslog_index`).

Two places match the index names literally and do not use the macros: the licence and storage panels of Telemetry
Ingest (`idx=` in the license usage search, `title=` in the index REST call; see `gen_telemetry_ingest.py`). Change those
in the generator if you rename the indexes.

## Data contract

The dashboards expect these series. Device name is the `extracted_source` dimension (gnmic and OTel), or `node` for Cribl.

| Source | Metric names | Dimensions used | Used for |
|--------|--------------|-----------------|----------|
| gnmic IOS-XE | `mdt_xe_*` (if_stats, if_info, cpu_stats, mem_stats, poe_stats, cdp_info, mac_info, arp_info, inventory) | `extracted_source`, `interface_name` | interfaces, CPU, memory, PoE, CDP, MAC and ARP tables, switch model |
| gnmic NX-OS | `mdt_nx_*` (if_stats, if_info, cpu_stats, mem_stats, cdp_info, mac_info, arp_info) | `extracted_source`, `interface_name` | same as IOS-XE |
| gnmic WLC | `mdt_wl_*` (info, client_stats, radio_info, ap_stats) | `extracted_source` (WLC name) | wireless overview, client details, client search |
| gnmic PAN-OS | `mdt_panos_*` | `extracted_source` | ingest pipeline label only |
| OTel dial-out | `cisco.*` (in-octets, speed, power-consumption, part-no_info, device-name_info, port_info, ...) | `extracted_source`, `interface_name` | interfaces, PoE, models, MAC table |
| Cribl dial-out | `if-stats.*`, `cpu-util.usage`, `mem-stats.usage`, `poe-stats.*` | `node`, `interface` | interfaces, CPU, memory, PoE |
| Collector host | `system.*`, `up`, `scrape_*` | none | excluded from device lists |

Label-valued metrics (PoE oper state, PD class, interface oper status) are published as value-1 series with the state as a
label. Macros in `default/macros.conf` read the gnmic and OTel forms of each topic and return one common shape.

Syslog: events with `host` = device name, read by Switch Details and Interface Details.

The gnmic configs (`gnmic/config/*.yaml`) and the OTel config (`gnmic/config/otel.yaml`) in this repo produce these
names. Changing a collector's metric names means changing the macros too.

Telemetry Ingest decides expected devices from the last 7 days of data (the pipeline is derived from the metric name
prefix). A device that goes silent shows as silent in the picked range.

## Topology settings (Network Overview)

Device roles (core, distribution, access, wlc, firewall, server, hidden) are entries in the KV store collection
`mdt_device_roles`. It starts empty: open **Network Overview > Topology settings** and add patterns (`*` is a wildcard,
for example `ibk-lab-sw*`). Writing needs the `power` or `admin` role.

## Maintaining the dashboards

- Dashboard Studio and generated views: edit the generator in `splunk/tools/gen_<name>.py`, then regenerate with
  `python3 splunk/tools/gen_<name>.py`. Do not edit the view XML by hand. The generators write the whole file, and a
  second run changes nothing.
- `default/data/ui/views/network_overview.xml` is a classic (Simple XML) dashboard with no generator: edit it directly.
- Macros: `default/macros.conf`. Their header comment explains the shapes.
- Visualization: see [viz/README.md](viz/README.md) (`port_faceplate`).
- Lab deploy over ssh: `scripts/splunk-deploy`. It is for the maintainer's lab host only.
