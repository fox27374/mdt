# Generates the Switch Details dashboard (Dashboard Studio JSON in views/switch_details.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_switch_details.py  then scripts/splunk-deploy
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "switch_details.xml")

N = "$tk_node$"
phys = "| `mdt_physical_ports`"
# Catalyst uplink slots show up twice (GigabitEthernet1/1/4 and TenGigabitEthernet1/1/4); keep one per slot, the up one, else the faster.
slots = (f"{phys} | rex field=interface \"^\\D+(?<path>\\d+(/\\d+)+)\" "
         "| sort 0 - oper_up - speed | dedup keepempty=true node path | sort 0 interface | fields - path")

# Base searches run once; chains post-process their results.
bases = {
    "ds_nodes": "`mdt_nodes($global_time.earliest$)`",
    # Every interface with state, CDP neighbour and learned MACs; chains filter to front-panel ports.
    "ds_status": f"`mdt_if_status({N})` | join type=left node interface [`mdt_cdp({N})` "
                 f"| stats values(neighbour) as neighbour by node interface] "
                 f"| join type=left node interface [`mdt_mac({N},*)` | eval entry=mac.if(vlan==\"-\", \"\", \" (VLAN \".vlan.\")\") "
                 f"| stats dc(mac) as macs values(entry) as mac_list by node interface] "
                 # PoE per port, joined on the interface key: gnmic and OTel name the same port with the same short or long form.
                 f"| eval inorm=`mdt_ifkey(interface)` | join type=left node inorm [`mdt_poe_port({N})` "
                 f"| eval inorm=`mdt_ifkey(interface)` | fields node inorm poe_w poe_state pd_class] "
                 # Errors in the time range, for the red frame on the faceplate.
                 f"| join type=left node interface [`mdt_if_counters({N},*)` | `mdt_if_rates` "
                 f"| stats sum(in_errs) as in_errs sum(out_errs) as out_errs by node interface | where in_errs + out_errs > 0]",
    # Per-minute rates of front-panel ports (no double counting via port-channels or VLANs), with link speed.
    "ds_rates": f"`mdt_if_counters({N},*)` {phys} | `mdt_if_rates` "
                f"| join type=left node interface [`mdt_if_status({N})` | fields node interface speed] "
                f"| eval util=round(max(in_bps, out_bps) / speed * 100, 4)",
    "ds_poe": f"`mdt_poe({N})`",
    "ds_cpu": f"`mdt_cpu({N})` | stats latest(cpu) as cpu | eval cpu=round(cpu, 0)",
    "ds_mem": f"`mdt_mem({N})` | stats latest(mem) as mem | eval mem=round(mem, 0)",
    # MACs on port-channels and VLANs; the Interfaces table shows those on front-panel ports.
    "ds_mac": f"`mdt_mac({N},*)` | where NOT (`mdt_is_physical`) | sort interface vlan mac | rename interface as Interface, vlan as VLAN, mac as MAC | fields - node",
    "ds_logs": f"index=cisco_syslog host=\"{N}\" | eval severity=mvindex(severity, 0), message=mvindex(message, 0) "
               f"| table _time severity message | sort - _time | head 200",
}
# Time charts leave out the current 5-minute bucket: not every port has reported in it yet, so its sum is too low.
chains = {  # name: (base, post-process)
    # One row per front-panel port for the port_faceplate visualization (the viz lays the ports out itself).
    "ds_ports": ("ds_status", f"{slots} | eval state=case(admin_up==0, \"admin down\", oper_up==1, \"up\", true(), \"down\") "
                 # Uplinks learn hundreds of MACs; the first 5 are listed, the count is in macs.
                 "| eval neighbour=mvjoin(neighbour, \", \"), mac_list=mvjoin(mvindex(mac_list, 0, min(4, mvcount(mac_list) - 1)), \", \") "
                 "| fillnull value=0 macs | fillnull value=\"\" neighbour mac_list | fields interface state speed neighbour macs mac_list poe_w poe_state pd_class in_errs out_errs"),
    "ds_nodata": ("ds_status", f"| stats count | where count=0 "
                  f"| eval Note=\"No telemetry for {N}. Switch Details covers switches that stream interface data.\" | fields Note"),
    "ds_ports_up": ("ds_status", f"{slots} | stats count as total sum(oper_up) as up "
                    "| eval pct=round(up / total * 100, 0) | fields pct"),
    "ds_ifaces_table": ("ds_status", f"{slots} "
                        f"| eval Status=case(admin_up==0, \"admin down\", oper_up==1, \"up\", true(), \"down\") "
                        f"| eval Speed=case(speed >= 1000000000, round(speed / 1000000000, 1).\" Gb/s\", speed > 0, round(speed / 1000000, 0).\" Mb/s\") "
                        f"| eval \"Last change\"=strftime(last_change, \"%Y-%m-%d %H:%M\") "
                        # "2d 15h 25m": zero parts left out, minutes shown when nothing else is
                        f"| eval d=floor(now() - last_change), dd=floor(d / 86400), dh=floor(d % 86400 / 3600), dm=floor(d % 3600 / 60) "
                        f"| eval \"Down for\"=if(oper_up==0 AND isnotnull(last_change), trim(if(dd > 0, dd.\"d \", \"\").if(dh > 0, dh.\"h \", \"\").if(dm > 0 OR d < 3600, dm.\"m\", \"\")), null()) "
                        # Uplinks learn hundreds of MACs; list up to 5, count beyond that.
                        f"| eval MACs=case(macs > 5, macs.\" MACs\", macs > 0, mac_list) | fillnull value=\"\" \"Down for\" \"CDP neighbour\" MACs "
                        f"| rename interface as Interface, neighbour as \"CDP neighbour\" "
                        f"| table Interface Status Speed \"Last change\" \"Down for\" \"CDP neighbour\" MACs"),
    # The gauge has a fixed 0-100 scale, so it shows percent of PoE capacity (drawn + free).
    "ds_poe_gauge": ("ds_poe", "| eval pct=round(used / (used + free) * 100, 0) | fields pct"),
    "ds_throughput": ("ds_rates", "| bin _time span=5m | where _time + 300 <= now() | stats avg(in_bps) as in avg(out_bps) as out by _time interface "
                      "| stats sum(in) as in sum(out) as out by _time "
                      "| eval \"In (Mb/s)\"=round(in / 1000000, 2), \"Out (Mb/s)\"=round(out / 1000000, 2) | fields - in out"),
    "ds_errors": ("ds_rates", "| bin _time span=5m | where _time + 300 <= now() | timechart span=5m sum(in_errs) as \"In errors\" sum(out_errs) as \"Out errors\""),
    "ds_top_util": ("ds_rates", "| stats max(util) as \"Peak utilization %\" by interface | sort - \"Peak utilization %\" | head 5"),
    "ds_top_errors": ("ds_rates", "| stats sum(in_errs) as \"In errors\" sum(out_errs) as \"Out errors\" by interface "
                      "| eval total='In errors' + 'Out errors' | where total > 0 | sort - total | head 5 | fields - total"),
}

import re
GEN = "mdt_nodes|mdt_if_status|mdt_if_counters|mdt_cpu|mdt_mem|mdt_poe_port|mdt_poe|mdt_cdp|mdt_mac"
# Generating macros start with mstats, so they need a leading pipe, at query start and inside subsearches.
bases = {k: re.sub(r"(^|\[)`(" + GEN + ")", r"\1| `\2", q) for k, q in bases.items()}
dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q}} for k, q in bases.items()}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})

# Marker gauge on a 0-100 scale; green / yellow / red bands from 70 and 90 % unless a fixed colour is given.
def gauge(title, d, color=None):
    ranges = ([{"from": 0, "to": 100, "value": color}] if color else
              [{"from": 0, "to": 70, "value": "#53a051"}, {"from": 70, "to": 90, "value": "#f8be34"}, {"from": 90, "to": 100, "value": "#dc4e41"}])
    return {"type": "splunk.markergauge", "title": title, "dataSources": {"primary": d},
            "options": {"orientation": "horizontal", "gaugeRanges": ranges}}

def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}

# Clicking a port opens its Interface Details in a new tab, with the device and time range.
def open_port(port):
    return [{"type": "drilldown.customUrl", "options": {"url": "/app/mdt_infra_monitoring/interface_details?form.tk_node=" + N
             + "&form.tk_interface=" + port + "&form.global_time.earliest=$global_time.earliest$&form.global_time.latest=$global_time.latest$",
             "newTab": True}}]
viz = {
    # Custom visualization (splunk/viz, built into the app): the type is <app id>.<visualization name>.
    # Clicking a port sends its interface as click.value, see visualization.js.
    "viz_ports": {"type": "mdt_infra_monitoring.port_faceplate",
                  "title": "Ports. Click a port to open its details.",
                  "dataSources": {"primary": "ds_ports"}, "options": {},
                  "eventHandlers": open_port("$click.value$")},
    "viz_nodata": {"type": "splunk.table", "dataSources": {"primary": "ds_nodata"}, "options": {},
                   "containerOptions": {"visibility": {"hideWhenNoData": True}}},
    "viz_cpu": gauge("CPU %", "ds_cpu"),
    "viz_mem": gauge("Memory %", "ds_mem"),
    "viz_poe": {**gauge("PoE drawn (% of PoE capacity)", "ds_poe_gauge"), "containerOptions": {"visibility": {"hideWhenNoData": True}}},
    "viz_ports_up": gauge("Ports up %", "ds_ports_up", "#708794"),
    "viz_throughput": chart("splunk.line", "Throughput, sum of all ports (5 min average)", "ds_throughput"),
    "viz_errors": chart("splunk.column", "Errors per 5 min (all ports)", "ds_errors", stackMode="stacked"),
    "viz_top_util": {**chart("splunk.bar", "Top 5 interfaces by peak utilization % (in or out); click to open", "ds_top_util", legendDisplay="off"),
                     "eventHandlers": open_port("$row.interface.value$")},
    "viz_top_errors": {**chart("splunk.bar", "Top 5 interfaces with errors; click to open", "ds_top_errors", stackMode="stacked", legendDisplay="bottom"),
                       "eventHandlers": open_port("$row.interface.value$")},
    "viz_ifaces": {**chart("splunk.table", "Interfaces; click a row to open", "ds_ifaces_table", count=100),
                   "eventHandlers": open_port("$row.Interface.value$")},
    "viz_mac": {**chart("splunk.table", "MAC addresses on port-channels and VLANs", "ds_mac", count=50),
                "containerOptions": {"visibility": {"hideWhenNoData": True}}},
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
}

rows = [  # (item, x, y, w, h)
    ("viz_nodata", 0, 0, 1440, 80),
    ("viz_cpu", 0, 80, 360, 200), ("viz_mem", 360, 80, 360, 200), ("viz_poe", 720, 80, 360, 200), ("viz_ports_up", 1080, 80, 360, 200),
    ("viz_ports", 0, 280, 1440, 200),
    ("viz_top_util", 0, 480, 720, 260), ("viz_top_errors", 720, 480, 720, 260),
    ("viz_throughput", 0, 740, 720, 320), ("viz_errors", 720, 740, 720, 320),
    ("viz_ifaces", 0, 1060, 940, 480), ("viz_mac", 940, 1060, 500, 480),
    ("viz_logs", 0, 1540, 1440, 420),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_node"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1960},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "Switch", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Switch Details",
    "description": "One switch: ports, CPU, memory, PoE, traffic, errors, CDP neighbours, MAC table and syslog. Covers Cribl (sw11-13) and gnmic (IOS-XE, NX-OS) telemetry.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Switch Details</label>\n'
       '    <description>One switch: ports, CPU, memory, PoE, traffic, errors, CDP, MAC and syslog</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
