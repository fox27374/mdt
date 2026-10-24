# Generates the Interface Details dashboard (Dashboard Studio JSON in views/interface_details.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_interface_details.py  then scripts/splunk-deploy
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "interface_details.xml")

# Token values: the device, and the port as a full name or a bare path from the port view ("1/1/4").
N, I = "$tk_node$", "$tk_interface$"
phys = "| `mdt_physical_ports`"
# Catalyst uplink slots show up twice (GigabitEthernet1/1/4 and TenGigabitEthernet1/1/4); keep one per slot, the up one, else the faster.
slots = (f"{phys} | rex field=interface \"^\\D+(?<path>\\d+(/\\d+)+)\" "
         "| sort 0 - oper_up - speed | dedup keepempty=true node path | sort 0 interface | fields - path")
# Keeps the port the token names: a full name, or a bare path (both slot names match, then the slots rule applies).
# Rows of one port per time bucket are reduced the same way: the up one, else the faster.
REX = "| rex field=interface \"^\\D+(?<path>\\d+(/\\d+)+)\""
MATCH = f"| where node=\"{N}\" AND (interface=\"{I}\" OR path=\"{I}\")"
PICK_SERIES = f"{REX} {MATCH} | sort 0 _time - oper_up - speed | dedup _time node path"
PICK_ONE = f"{REX} {MATCH} | sort 0 - oper_up - speed | dedup keepempty=true node path"

# Counters per 5-minute bucket and port, as sums of per-minute deltas (a reset gives no delta) with the sample count.
# name: raw field from mdt_if_counters / mdt_if_detail. Gnmic only for the detail counters; Cribl reports in/out errors only.
PAIRS = [("in_oct", "in_octets"), ("out_oct", "out_octets"), ("in_err", "in_errors"), ("out_err", "out_errors"),
         ("crc", "crc"), ("ov_rx", "oversize_rx"), ("un_rx", "undersize_rx"), ("frag_rx", "fragment_rx"),
         ("jab_rx", "jabber_rx"), ("tx_err", "tx_errors"), ("ov_tx", "oversize_tx")]
RAW = [r for _, r in PAIRS]
DETAIL_RAW = RAW[4:]
CNT = [d for d, _ in PAIRS]
SUMS = " ".join(f"sum({d}) as {d} count({d}) as {d}_n" for d in CNT)

# Fleet-wide per-minute deltas, bucketed to 5 minutes, joined with status, CDP links and the far port's name.
# Chains filter it to the device and port, so the base runs once for all panels.
STATUS_FIELDS = "node interface admin_up oper_up speed last_change"
FLOW = (
    "| `mdt_if_counters(*,*)` | append [| `mdt_if_detail(*,*)`] "
    "| stats max(in_octets) as in_octets max(out_octets) as out_octets max(in_errors) as in_errors max(out_errors) as out_errors "
    + " ".join(f"max({r}) as {r}" for r in DETAIL_RAW) + " by _time node interface "
    + f"{phys} | sort 0 node interface _time "
    "| streamstats current=f window=1 last(_time) as p_t " + " ".join(f"last({r}) as p_{r}" for r in RAW) + " by node interface "
    "| eval dt=_time - p_t | where dt > 0 "
    "| eval " + ", ".join(f"{d}=if({r} >= p_{r}, {r} - p_{r}, null())" for d, r in PAIRS) + " "
    "| eval in_bps=in_oct * 8 / dt, out_bps=out_oct * 8 / dt "
    f"| bin _time span=5m | stats avg(in_bps) as in_bps avg(out_bps) as out_bps {SUMS} by _time node interface "
    "| where _time + 300 <= now() "
    "| eval inorm=`mdt_ifkey(interface)` "
    f"| join type=left node interface [| `mdt_if_status(*)` {phys} | fields {STATUS_FIELDS}] "
    "| join type=left node inorm [| `mdt_links`] "
    "| join type=left far_node far_inorm [| `mdt_if_status(*)` " + phys + " | eval inorm=`mdt_ifkey(interface)` "
    "| rename node as far_node, inorm as far_inorm, interface as far_interface | fields far_node far_inorm far_interface]"
)

# Device status of the port (one row), with its CDP neighbour and far-end port.
STATUS = (f"| `mdt_if_status({N})` {phys} {PICK_ONE} | eval inorm=`mdt_ifkey(interface)` "
          "| join type=left node inorm [| `mdt_links`] "
          "| join type=left far_node far_inorm [| `mdt_if_status(*)` " + phys + " | eval inorm=`mdt_ifkey(interface)` "
          "| rename node as far_node, inorm as far_inorm, interface as far_interface | fields far_node far_inorm far_interface]")

# Learned MACs on the port (one row per MAC and VLAN). The mac macro names ports in full, the slot rule picks the port.
MACS = (f"| `mdt_mac({N},*)` | search [| `mdt_if_status({N})` {phys} {PICK_ONE} | fields interface] "
        "| rename mac as MAC, vlan as VLAN | fields MAC VLAN | sort MAC")

# Syslog naming the port by its path (Gi1/1/4, TenGigabitEthernet1/1/4, Ethernet1/23, eth1/23 all contain the path).
tokpath = f"if(match(\"{I}\", \"^\\D\"), replace(\"{I}\", \"^\\D+\", \"\"), \"{I}\")"
LOGS = (f"index=cisco_syslog host=\"{N}\" | eval severity=mvindex(severity, 0), message=mvindex(message, 0) "
        f"| eval tp={tokpath} | where match(message, \"(?<![\\d/])\" . tp . \"(?![\\d/])\") "
        "| table _time severity message | sort - _time | head 200")

# Link comparison: this port and its far end, totals over the whole time range.
METRICS = [("Traffic in (GB)", "in_oct", 1e9), ("Traffic out (GB)", "out_oct", 1e9), ("Errors in", "in_err", 1),
           ("Errors out", "out_err", 1), ("CRC received", "crc", 1), ("Oversize received", "ov_rx", 1),
           ("Oversize sent", "ov_tx", 1), ("Undersize received", "un_rx", 1), ("Fragments received", "frag_rx", 1),
           ("Jabber received", "jab_rx", 1), ("Transmit errors", "tx_err", 1)]
def cell(field, s):  # "-" when the platform does not report the counter; GB with 2 decimals, counts whole
    decimals = 0 if s == 1 else 2
    div = "" if s == 1 else f" / {int(s)}"
    return f"if(isnull({field}), \"-\", tostring(round({field}{div}, {decimals}), \"commas\"))"
compare_cells_this = ", ".join(
    [f"coalesce(t_node.\" \".t_if, \"-\")"] + [cell(f"t_{c}", s) for _, c, s in METRICS])
compare_cells_far = ", ".join(
    ["if(far_rows=0, \"no telemetry\", coalesce(f_node.\" \".f_if, \"-\"))"]
    + [f"if(far_rows=0, \"no telemetry\", {cell(f'f_{c}', s)})" for _, c, s in METRICS])
labels = ", ".join(f"\"{l}\"" for l in ["Port"] + [l for l, _, _ in METRICS])
COMPARE = (
    f"| stats {SUMS} max(oper_up) as oper_up max(speed) as speed max(far_node) as far_node max(far_inorm) as far_inorm "
    "max(far_interface) as far_interface by node interface inorm "
    "| eval " + ", ".join(f"{d}=if({d}_n=0, null(), {d})" for d in CNT) + " "
    f"{REX} | eval cand=if(node=\"{N}\" AND (interface=\"{I}\" OR path=\"{I}\"), 1, 0) "
    "| sort 0 - cand - oper_up - speed | dedup keepempty=true node path "
    "| eval fn=if(cand=1, far_node, null()), fi=if(cand=1, far_inorm, null()) | eventstats max(fn) as fn max(fi) as fi "
    "| where cand=1 OR (node=fn AND inorm=fi) | eval far=if(cand=1, 0, 1) "
    "| eval " + ", ".join(f"t_{c}=if(cand=1, {c}, null()), f_{c}=if(far=1, {c}, null())" for c in CNT)
    + ", t_node=if(cand=1, node, null()), t_if=if(cand=1, interface, null()), f_node=if(far=1, node, null()), f_if=if(far=1, interface, null()) "
    "| stats count(eval(far=1)) as far_rows max(t_node) as t_node max(t_if) as t_if max(f_node) as f_node max(f_if) as f_if "
    + " ".join(f"max(t_{c}) as t_{c} max(f_{c}) as f_{c}" for c in CNT) + " "
    f"| eval far_rows=coalesce(far_rows, 0) | eval labels=mvappend({labels}) "
    f"| eval this_vals=mvappend({compare_cells_this}) | eval far_vals=mvappend({compare_cells_far}) "
    "| eval x=mvzip(mvzip(labels, this_vals, \"|\"), far_vals, \"|\") | mvexpand x "
    "| rex field=x \"^(?<Counter>[^|]*)\\|(?<This>[^|]*)\\|(?<Neighbour>.*)$\" "
    "| table Counter This Neighbour | rename This as \"This port\", Neighbour as \"Neighbour port\""
)

bases = {
    "ds_nodes": "| `mdt_nodes($global_time.earliest$)`",
    "ds_ifaces": f"| `mdt_if_status({N})` {slots} | fields interface",
    "ds_status": STATUS,
    "ds_macs": MACS,
    "ds_logs": LOGS,
    "ds_flow": FLOW,
}
chains = {  # name: (base, post-process)
    "ds_hdr_status": ("ds_status", "| eval Status=case(admin_up==0, \"admin down\", oper_up==1, \"up\", true(), \"down\") | fields Status"),
    "ds_hdr_speed": ("ds_status", "| eval Speed=case(speed >= 1000000000, round(speed / 1000000000, 1).\" Gb/s\", speed > 0, round(speed / 1000000, 0).\" Mb/s\") | fields Speed"),
    # "down for 2d 15h 25m" when down (zero parts left out, minutes shown when nothing else is), else the time of the last change
    "ds_hdr_changed": ("ds_status", "| eval d=floor(now() - last_change), dd=floor(d / 86400), dh=floor(d % 86400 / 3600), dm=floor(d % 3600 / 60) "
                       "| eval \"Last change\"=case(isnull(last_change), \"-\", oper_up==0, \"down for \".trim(if(dd > 0, dd.\"d \", \"\").if(dh > 0, dh.\"h \", \"\").if(dm > 0 OR d < 3600, dm.\"m\", \"\")), "
                       "true(), strftime(last_change, \"%Y-%m-%d %H:%M\")) | fields \"Last change\""),
    "ds_hdr_neighbour": ("ds_status", "| eval neighbour=coalesce(far_node, \"none\"), neighbour_port=coalesce(far_interface, \"-\") | fields neighbour neighbour_port"),
    "ds_hdr_macs": ("ds_macs", "| stats dc(MAC) as \"Learned MACs\""),
    "ds_throughput": ("ds_flow", f"{PICK_SERIES} | eval \"In (Mb/s)\"=round(in_bps / 1000000, 2), \"Out (Mb/s)\"=round(out_bps / 1000000, 2) "
                      "| table _time \"In (Mb/s)\" \"Out (Mb/s)\""),
    # Other = in + out errors the telemetry has no kind for (Cribl reports only totals); floor 0
    "ds_errors": ("ds_flow", f"{PICK_SERIES} | eval CRC=coalesce(crc, 0), Oversize=coalesce(ov_rx, 0), Undersize=coalesce(un_rx, 0), "
                  "Fragment=coalesce(frag_rx, 0), Jabber=coalesce(jab_rx, 0), Transmit=coalesce(tx_err, 0) "
                  "| eval Other=max(0, coalesce(in_err, 0) + coalesce(out_err, 0) - CRC - Oversize - Undersize - Fragment - Jabber - Transmit) "
                  "| table _time CRC Oversize Undersize Fragment Jabber Transmit Other"),
    "ds_peak": ("ds_flow", f"{PICK_SERIES} | eval util=round(max(coalesce(in_bps, 0), coalesce(out_bps, 0)) / speed * 100, 1) "
                "| stats max(util) as \"Peak utilization %\""),
    "ds_compare": ("ds_flow", COMPARE),
}
dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q}} for k, q in bases.items()}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})

def tile(title, d, **opts):
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": d}, "options": opts}

def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}

# Clicking a neighbour opens its Interface Details with the far-end port, in a new tab.
def details_link(node, port):
    return [{"type": "drilldown.customUrl", "options": {"url": "/app/mdt_infra_monitoring/interface_details?form.tk_node=" + node
             + "&form.tk_interface=" + port + "&form.global_time.earliest=$global_time.earliest$&form.global_time.latest=$global_time.latest$",
             "newTab": True}}]

viz = {
    "viz_status": tile("Status", "ds_hdr_status"),
    "viz_speed": tile("Speed", "ds_hdr_speed"),
    "viz_changed": tile("Last change", "ds_hdr_changed"),
    "viz_neighbour": {"type": "splunk.table", "title": "CDP neighbour (click to open its port)", "dataSources": {"primary": "ds_hdr_neighbour"},
                      "options": {"count": 1, "headerVisibility": "none"},
                      "eventHandlers": details_link("$row.neighbour.value$", "$row.neighbour_port.value$")},
    "viz_macs": tile("Learned MACs", "ds_hdr_macs"),
    "viz_peak": tile("Peak utilization %", "ds_peak"),
    "viz_throughput": chart("splunk.line", "Throughput (5 min average)", "ds_throughput"),
    "viz_errors": chart("splunk.column", "Errors per 5 min by kind", "ds_errors", stackMode="stacked", legendDisplay="bottom"),
    "viz_compare": chart("splunk.table", "Link comparison, whole time range", "ds_compare", count=20),
    "viz_macs_table": chart("splunk.table", "Learned MAC addresses", "ds_macs", count=50),
    "viz_logs": chart("splunk.table", "Syslog for this port, newest first", "ds_logs", count=50),
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
                        "options": {"token": "tk_interface", "selectFirstSearchResult": True,
                                    "items": ">frame(label, value) | objects()"},
                        "context": {"label": ">primary | seriesByName(\"interface\") | renameSeries(\"label\")",
                                    "value": ">primary | seriesByName(\"interface\") | renameSeries(\"value\")"}},
}

rows = [  # (item, x, y, w, h)
    ("viz_status", 0, 0, 240, 110), ("viz_speed", 240, 0, 200, 110), ("viz_changed", 440, 0, 300, 110),
    ("viz_neighbour", 740, 0, 400, 110), ("viz_macs", 1140, 0, 150, 110), ("viz_peak", 1290, 0, 150, 110),
    ("viz_throughput", 0, 110, 720, 320), ("viz_errors", 720, 110, 720, 320),
    ("viz_compare", 0, 430, 1440, 420),
    ("viz_macs_table", 0, 850, 720, 320),
    ("viz_logs", 0, 1170, 1440, 420),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_node", "input_interface"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1590},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "Interface", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Interface Details",
    "description": "One port: status, speed, traffic and error kinds, the far end of its CDP link, learned MACs and syslog.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "1m", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Interface Details</label>\n'
       '    <description>One port: status, speed, traffic, error kinds, CDP far end, MACs and syslog</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
