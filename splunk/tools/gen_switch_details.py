# Generates the Switch Details dashboard (Dashboard Studio JSON in views/switch_details.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_switch_details.py  then scripts/splunk-deploy
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "switch_details.xml")

# The leading * lets a port view click ("1/0/5") match the full interface name.
N, I = "$tk_node$", "*$tk_interface$"
phys = "| `mdt_physical_ports`"

# Base searches run once; chains post-process their results.
bases = {
    "ds_nodes": "`mdt_nodes`",
    # Every interface with state and CDP neighbour; chains filter to front-panel ports.
    "ds_status": f"`mdt_if_status({N})` | join type=left node interface [`mdt_cdp({N})` "
                 f"| stats values(neighbour) as neighbour values(remote_interface) as remote_interface by node interface]",
    # Per-minute rates of front-panel ports (no double counting via port-channels or VLANs), with link speed.
    "ds_rates": f"`mdt_if_counters({N},{I})` {phys} | `mdt_if_rates` "
                f"| join type=left node interface [`mdt_if_status({N})` | fields node interface speed] "
                f"| eval util=round(max(in_bps, out_bps) / speed * 100, 4)",
    "ds_poe": f"`mdt_poe({N})`",
    "ds_cpu": f"`mdt_cpu({N})` | timechart span=1m avg(cpu) as \"CPU %\" avg(load) as \"Load average (1 min, NX-OS)\"",
    "ds_mem": f"`mdt_mem({N})` | timechart span=1m avg(mem) as \"Memory %\"",
    "ds_mac": f"`mdt_mac({N},{I})` | sort interface vlan mac | rename interface as Interface, vlan as VLAN, mac as MAC | fields - node",
    "ds_logs": f"index=cisco_syslog host=\"{N}\" | eval severity=mvindex(severity, 0), message=mvindex(message, 0) "
               f"| table _time severity message | sort - _time | head 200",
}
# Port view: one row per stack member and odd/even port, one column per port pair named after the odd port (zero padded so they sort);
# _s<col> columns carry the state for the cell colour and are left out of the display.
COLS = [f"{p:02d}" for p in range(1, 96, 2)] + [f"U{p}" for p in range(1, 8, 2)]
portview = open(sys.path[0] + "/portview.spl").read().strip().replace("\n", " ")
# Time charts leave out the current 5-minute bucket: not every port has reported in it yet, so its sum is too low.
chains = {  # name: (base, post-process)
    "ds_ports": ("ds_status", f"{phys} {portview}"),
    "ds_ifaces": ("ds_status", f"{phys} | fields interface | sort interface"),
    "ds_nodata": ("ds_status", f"| stats count | where count=0 "
                  f"| eval Note=\"No telemetry for {N}. Switch Details covers switches that stream interface data.\" | fields Note"),
    "ds_ports_up": ("ds_status", f"{phys} | stats count as total sum(oper_up) as up "
                    "| eval Ports=up.\" of \".total.\" (\".round(up / total * 100, 0).\"%)\" | fields Ports"),
    "ds_ifaces_table": ("ds_status", f"{phys} | search interface=\"{I}\" "
                        f"| eval Status=case(admin_up==0, \"admin down\", oper_up==1, \"up\", true(), \"down\") "
                        f"| eval Speed=case(speed >= 1000000000, round(speed / 1000000000, 1).\" Gb/s\", speed > 0, round(speed / 1000000, 0).\" Mb/s\") "
                        f"| eval \"Last change\"=strftime(last_change, \"%Y-%m-%d %H:%M\") "
                        # "2d 15h 25m": zero parts left out, minutes shown when nothing else is
                        f"| eval d=floor(now() - last_change), dd=floor(d / 86400), dh=floor(d % 86400 / 3600), dm=floor(d % 3600 / 60) "
                        f"| eval \"Down for\"=if(oper_up==0 AND isnotnull(last_change), trim(if(dd > 0, dd.\"d \", \"\").if(dh > 0, dh.\"h \", \"\").if(dm > 0 OR d < 3600, dm.\"m\", \"\")), null()) "
                        f"| rename interface as Interface, neighbour as \"CDP neighbour\", remote_interface as \"Neighbour port\" "
                        f"| table Interface Status Speed \"Last change\" \"Down for\" \"CDP neighbour\" \"Neighbour port\""),
    # The filler gauge has a fixed 0-100 scale, so it shows percent of PoE capacity (drawn + free) and the watts go in a text tile.
    "ds_poe_gauge": ("ds_poe", "| eval pct=round(used / (used + free) * 100, 0) | fields pct"),
    "ds_poe_watts": ("ds_poe", "| eval PoE=used.\" W drawn, \".free.\" W free\" | fields PoE"),
    "ds_throughput": ("ds_rates", "| bin _time span=5m | where _time + 300 <= now() | stats avg(in_bps) as in avg(out_bps) as out by _time interface "
                      "| stats sum(in) as in sum(out) as out by _time "
                      "| eval \"In (Mb/s)\"=round(in / 1000000, 2), \"Out (Mb/s)\"=round(out / 1000000, 2) | fields - in out"),
    "ds_errors": ("ds_rates", "| bin _time span=5m | where _time + 300 <= now() | timechart span=5m sum(in_errs) as \"In errors\" sum(out_errs) as \"Out errors\""),
    "ds_top_util": ("ds_rates", "| stats max(util) as \"Peak utilization %\" by interface | sort - \"Peak utilization %\" | head 5"),
    "ds_top_errors": ("ds_rates", "| stats sum(in_errs) as \"In errors\" sum(out_errs) as \"Out errors\" by interface "
                      "| eval total='In errors' + 'Out errors' | where total > 0 | sort - total | head 5 | fields - total"),
}

import re
GEN = "mdt_nodes|mdt_if_status|mdt_if_counters|mdt_cpu|mdt_mem|mdt_poe|mdt_cdp|mdt_mac"
# Generating macros start with mstats, so they need a leading pipe, at query start and inside subsearches.
bases = {k: re.sub(r"(^|\[)`(" + GEN + ")", r"\1| `\2", q) for k, q in bases.items()}
dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q}} for k, q in bases.items()}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})

def single(title, d, unit=""):
    o = {"majorColor": "#708794", "sparklineDisplay": "off", "trendDisplay": "off"}
    if unit:
        o.update(unit=unit, unitPosition="after")
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": d}, "options": o}

def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}

# Clicking a bar filters the dashboard to that interface.
filter_on_click = [{"type": "drilldown.setToken", "options": {"tokens": [{"token": "tk_interface", "key": "row.interface.value"}]}}]
viz = {
    "viz_ports": {"type": "splunk.table", "title": "Ports: green up, dark down, light grey admin down. Click a port to filter.",
                  "dataSources": {"primary": "ds_ports"},
                  "options": {"count": 20, "fontSize": "extraSmall", "headerVisibility": "none",
                              "table": "> primary | frameWithoutSeriesNames(" + ", ".join(f'"_s{c}"' for c in COLS) + ")",
                              "tableFormat": {"rowBackgroundColors": "> table | seriesByIndex(0) | pick(black)"},
                              "columnFormat": {**{f"{c}_": {"width": 4} for c in COLS}, **{c: {"width": 52, "rowBackgroundColors": f'> primary | seriesByName("_s{c}") | matchValue(stateColors)',
                                                   "rowColors": f'> primary | seriesByName("_s{c}") | matchValue(textColors)'} for c in COLS}}},
                  "context": {"stateColors": [{"match": "up", "value": "#53a051"}, {"match": "down", "value": "#30363d"},
                                              {"match": "admin down", "value": "#8a929b"}],
                              "black": ["#000000"],
                              "textColors": [{"match": s, "value": "#ffffff"} for s in ("up", "down", "admin down")]},
                  "eventHandlers": [{"type": "drilldown.setToken", "options": {"tokens": [{"token": "tk_interface", "key": "value"}]}}]},
    "viz_nodata": {"type": "splunk.table", "dataSources": {"primary": "ds_nodata"}, "options": {},
                   "containerOptions": {"visibility": {"hideWhenNoData": True}}},
    "viz_ports_up": single("Ports up", "ds_ports_up"),
    "viz_poe_watts": {**single("PoE", "ds_poe_watts"), "containerOptions": {"visibility": {"hideWhenNoData": True}}},
    "viz_poe": {"type": "splunk.fillergauge", "title": "PoE drawn (% of PoE capacity)", "dataSources": {"primary": "ds_poe_gauge"},
                "options": {"orientation": "horizontal", "gaugeColor": "> value | rangeValue(poeColors)"},
                "context": {"poeColors": [{"to": 70, "value": "#53a051"}, {"from": 70, "to": 90, "value": "#f8be34"}, {"from": 90, "value": "#dc4e41"}]},
                "containerOptions": {"visibility": {"hideWhenNoData": True}}},
    # Points arrive every few minutes; connect them so the 1-minute buckets in between don't break the line.
    "viz_cpu": chart("splunk.line", "CPU", "ds_cpu", nullValueDisplay="connect", legendDisplay="off"),
    "viz_mem": chart("splunk.line", "Memory", "ds_mem", yAxisMax=100, yAxisMin=0, nullValueDisplay="connect", legendDisplay="off"),
    "viz_throughput": chart("splunk.line", "Throughput, sum of selected ports (5 min average)", "ds_throughput"),
    "viz_errors": chart("splunk.column", "Errors per 5 min (selected interfaces)", "ds_errors", stackMode="stacked"),
    "viz_top_util": {**chart("splunk.bar", "Top 5 interfaces by peak utilization % (in or out); click to filter", "ds_top_util", legendDisplay="off"),
                     "eventHandlers": filter_on_click},
    "viz_top_errors": {**chart("splunk.bar", "Top 5 interfaces with errors; click to filter", "ds_top_errors", stackMode="stacked", legendDisplay="bottom"),
                       "eventHandlers": filter_on_click},
    "viz_ifaces": chart("splunk.table", "Interfaces", "ds_ifaces_table", count=100),
    "viz_mac": chart("splunk.table", "MAC addresses", "ds_mac", count=50),
    "viz_logs": chart("splunk.table", "Syslog", "ds_logs", count=50),
}

inputs = {
    "input_time": {"type": "input.timerange", "title": "Time range",
                   "options": {"token": "global_time", "defaultValue": "-4h@m,now"}},
    "input_node": {"type": "input.dropdown", "title": "Device", "dataSources": {"primary": "ds_nodes"},
                   "options": {"token": "tk_node", "selectFirstSearchResult": True,
                               "items": ">frame(label, value) | objects()"},
                   "context": {"label": ">primary | seriesByName(\"node\") | renameSeries(\"label\")",
                               "value": ">primary | seriesByName(\"node\") | renameSeries(\"value\")"}},
    "input_interface": {"type": "input.dropdown", "title": "Interface", "dataSources": {"primary": "ds_ifaces"},
                        "options": {"token": "tk_interface", "defaultValue": "*",
                                    "items": ">frame(label, value) | prepend(statics) | objects()"},
                        "context": {"statics": [["All"], ["*"]],
                                    "label": ">primary | seriesByName(\"interface\") | renameSeries(\"label\")",
                                    "value": ">primary | seriesByName(\"interface\") | renameSeries(\"value\")"}},
}

rows = [  # (item, x, y, w, h)
    ("viz_nodata", 0, 0, 1440, 80),
    ("viz_ports_up", 0, 80, 280, 200), ("viz_poe_watts", 280, 80, 260, 200), ("viz_poe", 540, 80, 300, 200),
    ("viz_cpu", 840, 80, 300, 200), ("viz_mem", 1140, 80, 300, 200),
    ("viz_top_util", 0, 280, 720, 260), ("viz_top_errors", 720, 280, 720, 260),
    ("viz_ports", 0, 540, 1440, 170),
    ("viz_throughput", 0, 710, 720, 320), ("viz_errors", 720, 710, 720, 320),
    ("viz_ifaces", 0, 1030, 940, 480), ("viz_mac", 940, 1030, 500, 480),
    ("viz_logs", 0, 1510, 1440, 420),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_node", "input_interface"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1930},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "Switch", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Switch Details",
    "description": "One switch: ports, CPU, memory, PoE, traffic, errors, CDP neighbours, MAC table and syslog. Covers Cribl (sw11-13) and gnmic (IOS-XE, NX-OS) telemetry.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "1m", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Switch Details</label>\n'
       '    <description>One switch: ports, CPU, memory, PoE, traffic, errors, CDP, MAC and syslog</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
