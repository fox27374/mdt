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
REX = "| rex field=interface \"^\\D+(?<path>\\d+(/\\d+)+)\""
MATCH = f"| where node=\"{N}\" AND (interface=\"{I}\" OR path=\"{I}\")"
PICK_ONE = f"{REX} {MATCH} | sort 0 - oper_up - speed | dedup keepempty=true node path"

# Counters per 5-minute bucket and port, as sums of per-minute deltas (a reset gives no delta) with the sample count.
# name: raw field from mdt_if_counters / mdt_if_detail. A platform without a detail counter reports in/out errors only.
PAIRS = [("in_oct", "in_octets"), ("out_oct", "out_octets"), ("in_err", "in_errors"), ("out_err", "out_errors"),
         ("crc", "crc"), ("ov_rx", "oversize_rx"), ("un_rx", "undersize_rx"), ("frag_rx", "fragment_rx"),
         ("jab_rx", "jabber_rx"), ("tx_err", "tx_errors"), ("ov_tx", "oversize_tx")]
RAW = [r for _, r in PAIRS]
DETAIL_RAW = RAW[4:]
CNT = [d for d, _ in PAIRS]
SUMS = " ".join(f"sum({d}) as {d} count({d}) as {d}_n" for d in CNT)

# The port and its CDP far end, resolved once by the status search and handed to the other searches as tokens
# ($status:result.<field>$, smart source). far_node / far_interface are "none" without a known far end, which matches nothing.
T_NODE, T_IF = "$status:result.node$", "$status:result.interface$"
F_NODE, F_IF = "$status:result.far_node$", "$status:result.far_interface$"

# Per-minute deltas of both ports, bucketed to 5 minutes. side: this or far.
FLOW = (
    f"| `mdt_if_counters({T_NODE},{T_IF})` | append [| `mdt_if_detail({T_NODE},{T_IF})`] "
    f"| append [| `mdt_if_counters({F_NODE},{F_IF})`] | append [| `mdt_if_detail({F_NODE},{F_IF})`] "
    "| stats max(in_octets) as in_octets max(out_octets) as out_octets max(in_errors) as in_errors max(out_errors) as out_errors "
    + " ".join(f"max({r}) as {r}" for r in DETAIL_RAW) + " by _time node interface "
    "| sort 0 node interface _time "
    "| streamstats current=f window=1 last(_time) as p_t " + " ".join(f"last({r}) as p_{r}" for r in RAW) + " by node interface "
    "| eval dt=_time - p_t | where dt > 0 "
    "| eval " + ", ".join(f"{d}=if({r} >= p_{r}, {r} - p_{r}, null())" for d, r in PAIRS) + " "
    "| eval in_bps=in_oct * 8 / dt, out_bps=out_oct * 8 / dt "
    f"| bin _time span=5m | stats avg(in_bps) as in_bps avg(out_bps) as out_bps {SUMS} by _time node interface "
    "| where _time + 300 <= now() "
    f"| eval side=if(node=\"{T_NODE}\" AND interface=\"{T_IF}\", \"this\", \"far\")"
)
THIS = "| where side=\"this\""

# Device status of the port (one row), with its CDP neighbour and far-end port.
# Front-panel ports and port-channels (a port-channel's counters and status are not physical-only, but its ports are the front-panel ones).
PO_OR_PHYS = "| where (`mdt_is_physical` OR match(interface, \"(?i)^(port-channel|po[0-9])\"))"
STATUS = (f"| `mdt_if_status({N})` {PO_OR_PHYS} {PICK_ONE} | eval inorm=`mdt_ifkey(interface)` "
          "| join type=left node inorm [| `mdt_links`] "
          "| join type=left far_node far_inorm [| `mdt_if_status(*)` " + phys + " | eval inorm=`mdt_ifkey(interface)` "
          "| rename node as far_node, inorm as far_inorm, interface as far_interface | fields far_node far_inorm far_interface] "
          # A neighbour without telemetry (an AP, a phone) has no telemetry port: its CDP name only, no link.
          "| eval neighbour_md=case(isnull(far_node), \"none\", isnull(far_interface), far_node, true(), \"[\".far_node.\" \".far_interface.\"](/app/mdt_infra_monitoring/interface_details?form.tk_node=\".far_node.\"&form.tk_interface=\".far_interface"
          ".\"&form.global_time.earliest=$global_time.earliest$&form.global_time.latest=$global_time.latest$)\") "
          "| eval far_node=coalesce(far_node, \"none\"), far_interface=coalesce(far_interface, \"none\")")

# Learned MACs on the port (one row per MAC and VLAN). The mac macro names ports in full, the slot rule picks the port.
MACS = (f"| `mdt_mac({T_NODE},{T_IF})` "
        "| rename mac as MAC, vlan as VLAN | fields MAC VLAN | sort MAC")

# Syslog naming the port by its path (Gi1/1/4, TenGigabitEthernet1/1/4, Ethernet1/23, eth1/23 all contain the path).
tokpath = f"if(match(\"{I}\", \"^\\D\"), replace(\"{I}\", \"^\\D+\", \"\"), \"{I}\")"
LOGS = (f"`mdt_syslog_index` host=\"{N}\" | eval severity=mvindex(severity, 0), message=mvindex(message, 0) "
        f"| eval tp={tokpath} | where match(message, \"(?<![\\d/])\" . tp . \"(?![\\d/])\") "
        "| table _time severity message | sort - _time | head 200")

# Link comparison: this port and its far end, totals over the whole time range.
METRICS = [("Traffic in (GB)", "in_oct", 1e9), ("Traffic out (GB)", "out_oct", 1e9), ("Errors in", "in_err", 1),
           ("Errors out", "out_err", 1), ("CRC received", "crc", 1), ("Oversize received", "ov_rx", 1),
           ("Oversize sent", "ov_tx", 1), ("Undersize received", "un_rx", 1), ("Fragments received", "frag_rx", 1),
           ("Jabber received", "jab_rx", 1), ("Transmit errors", "tx_err", 1)]
def cell(field, s):  # "-" when the platform does not report the counter; GB with 2 decimals, counts whole.
    # No thousands separators: those turn a number into text, which the table aligns left.
    decimals = 0 if s == 1 else 2
    div = "" if s == 1 else f" / {int(s)}"
    return f"if(isnull({field}), \"-\", tostring(round({field}{div}, {decimals})))"
compare_cells_this = ", ".join(
    [f"coalesce(t_node.\" \".t_if, \"-\")"] + [cell(f"t_{c}", s) for _, c, s in METRICS])
compare_cells_far = ", ".join(
    ["if(far_rows=0, \"no telemetry\", coalesce(f_node.\" \".f_if, \"-\"))"]
    + [f"if(far_rows=0, \"no telemetry\", {cell(f'f_{c}', s)})" for _, c, s in METRICS])
labels = ", ".join(f"\"{l}\"" for l in ["Port"] + [l for l, _, _ in METRICS])
COMPARE = (
    f"| stats {SUMS} by side "
    "| eval " + ", ".join(f"{d}=if({d}_n=0, null(), {d})" for d in CNT) + " "
    "| eval " + ", ".join(f"t_{c}=if(side=\"this\", {c}, null()), f_{c}=if(side=\"far\", {c}, null())" for c in CNT) + " "
    "| stats count(eval(side=\"far\")) as far_rows " + " ".join(f"max(t_{c}) as t_{c} max(f_{c}) as f_{c}" for c in CNT) + " "
    f"| eval t_node=\"{T_NODE}\", t_if=\"{T_IF}\", f_node=\"{F_NODE}\", f_if=\"{F_IF}\" "
    f"| eval far_rows=coalesce(far_rows, 0) | eval labels=mvappend({labels}) "
    f"| eval this_vals=mvappend({compare_cells_this}) | eval far_vals=mvappend({compare_cells_far}) "
    "| eval x=mvzip(mvzip(labels, this_vals, \"|\"), far_vals, \"|\") | mvexpand x "
    "| rex field=x \"^(?<Counter>[^|]*)\\|(?<This>[^|]*)\\|(?<Neighbour>.*)$\" "
    "| table Counter This Neighbour | rename This as \"This port\", Neighbour as \"Neighbour port\""
)

bases = {
    "ds_nodes": "| `mdt_nodes($global_time.earliest$)`",
    # Port-channels are listed after the front-panel ports, so a port-channel opened from Switch Details is in the dropdown.
    "ds_ifaces": f"| `mdt_if_status({N})` {slots} | fields interface "
                 f"| append [| `mdt_if_status({N})` | where match(interface, \"(?i)^(port-channel|po[0-9])\") | fields interface]",
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
    "ds_hdr_macs": ("ds_macs", "| stats dc(MAC) as \"Learned MACs\""),
    # Duplex, auto-negotiation and MTU of the port (mdt_if_status); blank when no source reports them.
    "ds_hdr_duplex": ("ds_status", "| eval Duplex=coalesce(duplex, \"\") | fields Duplex"),
    "ds_hdr_autoneg": ("ds_status", "| eval \"Auto-neg\"=coalesce(autoneg, \"\") | fields \"Auto-neg\""),
    "ds_hdr_mtu": ("ds_status", "| eval MTU=if(isnull(mtu), \"\", tostring(mtu)) | fields MTU"),
    "ds_throughput": ("ds_flow", f"{THIS} | eval \"In (Mb/s)\"=round(in_bps / 1000000, 2), \"Out (Mb/s)\"=round(out_bps / 1000000, 2) "
                      "| table _time \"In (Mb/s)\" \"Out (Mb/s)\""),
    # Oversize frames are only errors where the MTU is smaller (a jumbo port receives them fine), so Oversize is capped at the
    # input errors the always-error kinds leave, and Transmit at the output errors. Other = errors without a kind
    # (a platform without detail counters), floor 0.
    "ds_errors": ("ds_flow", f"{THIS} | eval ie=coalesce(in_err, 0), oe=coalesce(out_err, 0), CRC=coalesce(crc, 0), Undersize=coalesce(un_rx, 0), "
                  "Fragment=coalesce(frag_rx, 0), Jabber=coalesce(jab_rx, 0) "
                  "| eval Oversize=min(coalesce(ov_rx, 0), max(0, ie - CRC - Undersize - Fragment - Jabber)), Transmit=min(coalesce(tx_err, 0), oe) "
                  "| eval Other=max(0, ie + oe - CRC - Oversize - Undersize - Fragment - Jabber - Transmit) "
                  "| table _time CRC Oversize Undersize Fragment Jabber Transmit Other"),
    "ds_peak": ("ds_flow", f"{THIS} | eval util=round(max(coalesce(in_bps, 0), coalesce(out_bps, 0)) / $status:result.speed$ * 100, 1) "
                "| stats max(util) as \"Peak utilization %\""),
    "ds_compare": ("ds_flow", COMPARE),
}
dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q}} for k, q in bases.items()}
dataSources["ds_status"]["options"]["enableSmartSources"] = True
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})

def tile(title, d, **opts):
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": d}, "options": opts}

def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}

viz = {
    "viz_status": tile("Status", "ds_hdr_status"),
    "viz_speed": tile("Speed", "ds_hdr_speed"),
    "viz_changed": tile("Last change", "ds_hdr_changed"),
    # A link to the neighbour's port when there is one, plain "none" otherwise.
    "viz_neighbour": {"type": "splunk.markdown",
                      "options": {"markdown": "**CDP neighbour**\n\n## $status:result.neighbour_md$"}},
    "viz_duplex": tile("Duplex", "ds_hdr_duplex"),
    "viz_autoneg": tile("Auto-negotiation", "ds_hdr_autoneg"),
    "viz_mtu": tile("MTU", "ds_hdr_mtu"),
    "viz_macs": tile("Learned MACs", "ds_hdr_macs"),
    "viz_peak": tile("Peak utilization %", "ds_peak"),
    "viz_throughput": chart("splunk.line", "Throughput (5 min average)", "ds_throughput"),
    "viz_errors": chart("splunk.column", "Errors per 5 min by kind", "ds_errors", stackMode="stacked", legendDisplay="bottom"),
    "viz_compare": chart("splunk.table", "Link comparison, whole time range", "ds_compare", count=20),
    # Hidden when empty (most uplinks learn no MACs, most ports have no syslog) instead of a no-results warning.
    "viz_macs_table": {**chart("splunk.table", "Learned MAC addresses", "ds_macs", count=50), "containerOptions": {"visibility": {"hideWhenNoData": True}}},
    "viz_logs": {**chart("splunk.table", "Syslog for this port, newest first", "ds_logs", count=50), "containerOptions": {"visibility": {"hideWhenNoData": True}}},
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
    # Second header row: the port's duplex, auto-negotiation and MTU.
    ("viz_duplex", 0, 110, 480, 90), ("viz_autoneg", 480, 110, 480, 90), ("viz_mtu", 960, 110, 480, 90),
    ("viz_throughput", 0, 200, 720, 320), ("viz_errors", 720, 200, 720, 320),
    ("viz_compare", 0, 520, 1440, 420),
    # Last row, side by side: both hide when empty and the grid keeps their space, so it is one row at the bottom.
    ("viz_macs_table", 0, 940, 480, 400), ("viz_logs", 480, 940, 960, 400),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_node", "input_interface"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1340},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "Interface", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Interface Details",
    "description": "One port: status, speed, traffic and error kinds, the far end of its CDP link, learned MACs and syslog.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Interface Details</label>\n'
       '    <description>One port: status, speed, traffic, error kinds, CDP far end, MACs and syslog</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
