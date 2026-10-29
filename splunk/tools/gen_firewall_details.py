# Generates the Firewall Details dashboard (Dashboard Studio JSON in views/firewall_details.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_firewall_details.py  then scripts/splunk-deploy
# Data: gnmic PAN-OS subscriptions panos_if_stats (30s counters per interface), panos_if_info (300s negotiated speed, duplex,
# auto-negotiation) and panos_session_stats (60s).
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "firewall_details.xml")

# Interface counters per minute in the mdt_if_counters shape, so mdt_if_rates turns them into bit/s and errors per sample.
# Then 5-minute averages per interface; the open bucket is dropped so the last point is not a partial one.
FLOW = ("| mstats latest(mdt_panos_if_stats_in_octets) as in_octets latest(mdt_panos_if_stats_out_octets) as out_octets "
        "latest(mdt_panos_if_stats_in_errors) as in_errors latest(mdt_panos_if_stats_out_errors) as out_errors "
        "WHERE `mdt_metrics_index` extracted_source=\"$tk_fw$\" span=1m BY extracted_source interface_name "
        "| eval node=extracted_source, interface=interface_name | fields - extracted_source interface_name "
        "| `mdt_if_rates` | bin _time span=5m "
        "| stats avg(in_bps) as in_bps avg(out_bps) as out_bps sum(in_errs) as in_errs sum(out_errs) as out_errs by _time interface "
        "| where _time + 300 <= now()")

bases = {
    "ds_fws": "| mstats count(_value) WHERE `mdt_metrics_index` metric_name=mdt_panos_* BY extracted_source "
              "| rename extracted_source as node | fields node | sort node",
    "ds_flow": FLOW,
    "ds_sessions": "| mstats latest(mdt_panos_session_stats_active) as active latest(mdt_panos_session_stats_max) as max "
                   "WHERE `mdt_metrics_index` extracted_source=\"$tk_fw$\" span=5m",
}

# Per-interface time series, only interfaces that carried traffic (or errors) in the range.
def per_if(value):
    return (f"| eval v={value} | eventstats max(v) as m by interface | where m > 0 "
            "| xyseries _time interface v | fillnull value=0")

chains = {  # name: (base, post-process)
    "ds_active": ("ds_sessions", "| timechart span=5m max(active) as \"Active sessions\""),  # timechart: empty buckets stay null, so gaps show
    "ds_util": ("ds_sessions", "| eval \"Session table %\"=round(active / max * 100, 2) | fields _time \"Session table %\""),
    "ds_in_total": ("ds_flow", "| stats sum(in_bps) as v by _time | eval \"In (Mb/s)\"=round(v / 1000000, 1) | fields _time \"In (Mb/s)\""),
    "ds_out_total": ("ds_flow", "| stats sum(out_bps) as v by _time | eval \"Out (Mb/s)\"=round(v / 1000000, 1) | fields _time \"Out (Mb/s)\""),
    "ds_err_ifs": ("ds_flow", "| stats sum(in_errs) as i sum(out_errs) as o by interface | where coalesce(i, 0) + coalesce(o, 0) > 0 "
                              "| stats count as \"Interfaces with errors\""),
    "ds_in": ("ds_flow", per_if("round(in_bps / 1000000, 2)")),
    "ds_out": ("ds_flow", per_if("round(out_bps / 1000000, 2)")),
    "ds_errs": ("ds_flow", per_if("coalesce(in_errs, 0) + coalesce(out_errs, 0)")),
    "ds_table": ("ds_flow", "| eventstats max(_time) as last "
                            "| eval in_now=if(_time == last, in_bps, null()), out_now=if(_time == last, out_bps, null()) "
                            "| stats max(in_now) as in_now max(out_now) as out_now avg(in_bps) as in_avg avg(out_bps) as out_avg "
                            "max(in_bps) as in_max max(out_bps) as out_max sum(in_errs) as in_errs sum(out_errs) as out_errs by interface "
                            "| foreach in_* out_* [eval <<FIELD>>=if(match(\"<<FIELD>>\", \"errs$\"), <<FIELD>>, round(<<FIELD>> / 1000000, 2))] "
                            # Negotiated speed / duplex (panos_if_info, 300s): one value-1 series per leaf with the value as label.
                            # One mstats per leaf: mstats BY drops series that lack a BY dimension.
                            "| join type=left interface [| mstats latest(_value) WHERE `mdt_metrics_index` metric_name=mdt_panos_if_info_negotiated_port_speed extracted_source=\"$tk_fw$\" earliest=-15m BY interface_name negotiated_port_speed "
                            "| append [| mstats latest(_value) WHERE `mdt_metrics_index` metric_name=mdt_panos_if_info_negotiated_duplex_mode extracted_source=\"$tk_fw$\" earliest=-15m BY interface_name negotiated_duplex_mode] "
                            "| append [| mstats latest(_value) as a WHERE `mdt_metrics_index` metric_name=mdt_panos_if_info_auto_negotiate extracted_source=\"$tk_fw$\" earliest=-15m BY interface_name | eval auto=if(a==1, \"yes\", \"no\")] "
                            "| stats values(negotiated_port_speed) as speed values(negotiated_duplex_mode) as duplex values(auto) as auto by interface_name "
                            "| eval speed=replace(replace(speed, \"^.*SPEED_(.*?)B?$\", \"\\1\"), \"UNKNOWN\", \"unknown\"), duplex=lower(duplex) | rename interface_name as interface] "
                            "| sort 0 - in_max "
                            "| rename interface as Interface, speed as Speed, duplex as Duplex, auto as \"Auto-neg\", in_now as \"In now (Mb/s)\", out_now as \"Out now (Mb/s)\", "
                            "in_avg as \"In avg (Mb/s)\", out_avg as \"Out avg (Mb/s)\", in_max as \"In peak (Mb/s)\", "
                            "out_max as \"Out peak (Mb/s)\", in_errs as \"Errors in\", out_errs as \"Errors out\" "
                            "| table Interface Speed Duplex \"Auto-neg\" \"In now (Mb/s)\" \"Out now (Mb/s)\" \"In avg (Mb/s)\" \"Out avg (Mb/s)\" "
                            "\"In peak (Mb/s)\" \"Out peak (Mb/s)\" \"Errors in\" \"Errors out\""),
}

dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q}} for k, q in bases.items()}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})

def tile(title, d, **opts):
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": d},
            "options": {"majorColor": "#708794", **opts}}

def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}

viz = {
    "viz_active": tile("Active sessions", "ds_active"),
    "viz_util": tile("Session table used", "ds_util", unit="%", unitPosition="after"),
    "viz_in_total": tile("Total in (5 min average)", "ds_in_total", unit="Mb/s", unitPosition="after"),
    "viz_out_total": tile("Total out (5 min average)", "ds_out_total", unit="Mb/s", unitPosition="after"),
    "viz_err_ifs": tile("Interfaces with errors", "ds_err_ifs"),
    "viz_in": chart("splunk.line", "In by interface, Mb/s (5 min average)", "ds_in", legendDisplay="bottom"),
    "viz_out": chart("splunk.line", "Out by interface, Mb/s (5 min average)", "ds_out", legendDisplay="bottom"),
    "viz_sessions": chart("splunk.line", "Active sessions", "ds_active", legendDisplay="off", nullValueDisplay="gaps"),
    "viz_errs": {**chart("splunk.column", "Errors per 5 min by interface (in + out)", "ds_errs",
                         stackMode="stacked", legendDisplay="bottom"),
                 "containerOptions": {"visibility": {"hideWhenNoData": True}}},
    "viz_table": chart("splunk.table", "Interfaces, whole time range", "ds_table", count=30),
}

inputs = {
    "input_time": {"type": "input.timerange", "title": "Time range",
                   "options": {"token": "global_time", "defaultValue": "-4h@m,now"}},
    "input_fw": {"type": "input.dropdown", "title": "Firewall", "dataSources": {"primary": "ds_fws"},
                 "options": {"token": "tk_fw", "selectFirstSearchResult": True, "items": ">frame(label, value) | objects()"},
                 "context": {"label": ">primary | seriesByName(\"node\") | renameSeries(\"label\")",
                             "value": ">primary | seriesByName(\"node\") | renameSeries(\"value\")"}},
}

rows = [  # (item, x, y, w, h)
    ("viz_active", 0, 0, 288, 110), ("viz_util", 288, 0, 288, 110), ("viz_in_total", 576, 0, 288, 110),
    ("viz_out_total", 864, 0, 288, 110), ("viz_err_ifs", 1152, 0, 288, 110),
    ("viz_in", 0, 110, 720, 320), ("viz_out", 720, 110, 720, 320),
    ("viz_sessions", 0, 430, 720, 300), ("viz_errs", 720, 430, 720, 300),
    ("viz_table", 0, 730, 1440, 420),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_fw"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1150},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "Firewall", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Firewall Details",
    "description": "One Palo Alto firewall: sessions, throughput and errors per interface.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Firewall Details</label>\n'
       '    <description>One Palo Alto firewall: sessions, throughput and errors per interface</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
