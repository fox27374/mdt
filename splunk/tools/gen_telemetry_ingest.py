# Generates the Telemetry Ingest dashboard (Dashboard Studio JSON in views/telemetry_ingest.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_telemetry_ingest.py  then scripts/splunk-deploy
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "telemetry_ingest.xml")

# Pipeline of a metric, by name. Collector host = the collector's own metrics (no device).
PIPE = ('case(match(metric_name, "^mdt_xe_"), "gnmic IOS-XE", match(metric_name, "^mdt_nx_"), "gnmic NX-OS", '
        'match(metric_name, "^mdt_wl_"), "gnmic WLC", match(metric_name, "^mdt_panos_"), "gnmic PAN-OS", '
        'match(metric_name, "^cisco[.]"), "OTel dial-out", match(metric_name, "^(system[.]|up$|scrape_)"), "Collector host", true(), "Other")')
LIC = "(idx=cisco_metrics OR idx=cisco_syslog)"
POOL = ('| appendcols [| rest /services/licenser/pools splunk_server=local | search title=auto_generated_pool_enterprise '
        '| eval pool_bytes=tonumber(effective_quota) | fields pool_bytes]')
# Devices: data points and last time over the last 15 minutes, distinct gnmic subscriptions, and every device seen in the last 7 days
# (expected devices: one that is silent in the picked range shows as silent, not missing). The 7-day subsearch has its own earliest.
DEVICES = (
    "| mstats count(_value) as n latest_time(_value) as t WHERE `mdt_metrics_index` metric_name=* earliest=-15m BY metric_name extracted_source "
    f"| eval pipe={PIPE}, device=extracted_source "
    "| where pipe!=\"Collector host\" AND isnotnull(device) "
    "| stats sum(n) as n max(t) as seen values(pipe) as pipe by device "
    "| append [| mstats count(_value) as n WHERE `mdt_metrics_index` metric_name=mdt_* earliest=-15m BY extracted_source subscription_name "
    "| stats dc(subscription_name) as subs by extracted_source | rename extracted_source as device] "
    "| stats sum(n) as n max(seen) as seen max(subs) as subs values(pipe) as pipe by device "
    "| append [| mstats latest_time(_value) as t WHERE `mdt_metrics_index` metric_name=* earliest=-7d BY metric_name extracted_source "
    f"| eval pipe={PIPE}, device=extracted_source "
    "| where pipe!=\"Collector host\" AND isnotnull(device) "
    "| stats max(t) as seen values(pipe) as pipe by device] "
    "| stats sum(n) as n max(seen) as seen max(subs) as subs values(pipe) as pipe by device "
    "| eval Pipeline=case(match(mvjoin(pipe, \",\"), \"gnmic\"), \"gnmic\", match(mvjoin(pipe, \",\"), \"OTel\"), \"OTel dial-out\", true(), \"Other\")"
)

# Per-minute license volume of the two indexes, from the license log (type=Usage carries bytes per index).
USAGE = f"index=_internal source=*license_usage.log type=Usage {LIC}"

bases = {
    "ds_tile_metrics": "| mstats count(_value) as n WHERE `mdt_metrics_index` metric_name=* earliest=-15m "
                       "| eval rate=round(n / 900, 0) | fields rate",
    "ds_devices": DEVICES,
    "ds_subs": "| mstats count(_value) WHERE `mdt_metrics_index` metric_name=mdt_* earliest=-15m BY extracted_source subscription_name "
               "| stats count as subscriptions",
    "ds_lic_today": f"{USAGE} | stats sum(b) as bytes",
    "ds_lic_table": (f"{USAGE} "
                     "| eval td=if(_time >= relative_time(now(), \"@d\"), b, 0), yd=if(_time >= relative_time(now(), \"-1d@d\") AND _time < relative_time(now(), \"@d\"), b, 0) "
                     "| stats sum(td) as td sum(yd) as yd sum(b) as mo by idx "
                     "| appendpipe [| stats sum(td) as td sum(yd) as yd sum(mo) as mo | eval idx=\"Total\"] "
                     f"{POOL} | filldown pool_bytes "
                     "| eval Index=idx, \"Today (MB)\"=round(td / 1048576, 1), \"Yesterday (MB)\"=round(yd / 1048576, 1), "
                     "\"30-day average (MB/day)\"=round(mo / 30 / 1048576, 1), \"% of pool (today)\"=round(td / pool_bytes * 100, 2) "
                     "| table Index \"Today (MB)\" \"Yesterday (MB)\" \"30-day average (MB/day)\" \"% of pool (today)\""),
    "ds_lic_chart": f"{USAGE} | bin _time span=1d | stats sum(b) as bytes by _time idx "
                    "| eval MB=round(bytes / 1048576, 1) | xyseries _time idx MB | fillnull value=0",
    "ds_ingest": "| mstats count(_value) as n WHERE `mdt_metrics_index` metric_name=* BY metric_name span=5m "
                 f"| eval pipe={PIPE} | stats sum(n) as n by _time pipe "
                 "| where _time + 300 <= now() | eval rate=round(n / 300, 1) | xyseries _time pipe rate | fillnull value=0",
    "ds_storage": "| rest /services/data/indexes datatype=all count=0 | search title=cisco_metrics OR title=cisco_syslog "
                  "| eval Index=title, Type=if(datatype=\"metric\", \"metric\", \"event\"), \"Size on disk (MB)\"=round(currentDBSizeMB, 1), "
                  "\"Events / data points\"=totalEventCount, \"Retention (days)\"=round(frozenTimePeriodInSecs / 86400, 0) "
                  "| table Index Type \"Size on disk (MB)\" \"Events / data points\" \"Retention (days)\" | sort Index",
}
chains = {  # name: (base, post-process)
    "ds_sending": ("ds_devices", "| where n > 0 | stats count as devices"),
    "ds_devices_table": ("ds_devices", "| eval \"Metrics/s\"=round(coalesce(n, 0) / 900, 1), "
                         "\"Last data\"=if(isnull(seen), \"\", strftime(seen, \"%Y-%m-%d %H:%M:%S\")), "
                         "Subscriptions=if(Pipeline=\"OTel dial-out\", \"dial-out\", tostring(coalesce(subs, 0))), "
                         "Status=if(isnotnull(seen) AND seen >= now() - 600, \"OK\", \"silent\") "
                         "| eval ord=if(Status=\"silent\", 0, 1) | sort 0 ord device | fields - ord "
                         "| rename device as Device | table Device Pipeline \"Last data\" \"Metrics/s\" Subscriptions Status"),
    "ds_lic_mb": ("ds_lic_today", "| eval mb=round(bytes / 1048576, 0) | fields mb"),
}
# Fixed windows per search: tiles and devices use the last 15 minutes, licence views the last 30 days, the rest the picker.
LAST15 = {"earliest": "-15m", "latest": "now"}
DAYS30 = {"earliest": "-29d@d", "latest": "now"}
PICKER = {"earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}
WINDOW = {"ds_tile_metrics": LAST15, "ds_devices": LAST15, "ds_subs": LAST15, "ds_lic_today": {"earliest": "@d", "latest": "now"},
          "ds_lic_table": DAYS30, "ds_lic_chart": DAYS30, "ds_ingest": PICKER, "ds_storage": PICKER}
SLOW = {"ds_lic_today", "ds_lic_table", "ds_lic_chart", "ds_storage"}  # license and REST data change slowly: refresh every 5 min

dataSources = {}
for k, q in bases.items():
    opts = {"query": q, "queryParameters": WINDOW[k]}
    if k in SLOW:
        opts.update({"refresh": "5m", "refreshType": "delay"})
    dataSources[k] = {"type": "ds.search", "name": k[3:], "options": opts}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})

def tile(title, d, **opts):
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": d},
            "options": {"majorColor": "#708794", **opts}}

def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}

# Status column: green when the device sent data in the last 10 minutes, red when silent.
devices = {"type": "splunk.table", "title": "Devices: configured and sending (last 15 min). Silent = no data in the last 10 min",
           "dataSources": {"primary": "ds_devices_table"},
           "options": {"count": 30, "columnFormat": {"Status": {
               "rowBackgroundColors": "> primary | seriesByName(\"Status\") | matchValue(statusColors)",
               "rowColors": "> primary | seriesByName(\"Status\") | matchValue(statusTextColors)"}}},
           "context": {"statusColors": [{"match": "OK", "value": "#53a051"}, {"match": "silent", "value": "#dc4e41"}],
                       "statusTextColors": [{"match": "OK", "value": "#ffffff"}, {"match": "silent", "value": "#ffffff"}]},
           "showProgressBar": True}

viz = {
    "viz_metrics": tile("Metrics per second (last 15 min)", "ds_tile_metrics", numberPrecision=0),
    "viz_sending": tile("Sending devices (last 15 min)", "ds_sending"),
    "viz_subs": tile("gnmic subscriptions (last 15 min)", "ds_subs"),
    "viz_lic_mb": tile("Volume ingested today (MB)", "ds_lic_mb", unit="MB", unitPosition="after"),
    "viz_ingest": chart("splunk.area", "Ingest: metrics per second by pipeline (5 min average)", "ds_ingest",
                        stackMode="stacked", legendDisplay="bottom"),
    "viz_devices": devices,
    "viz_lic_chart": chart("splunk.column", "License volume per day by index, last 30 days (MB)", "ds_lic_chart",
                           stackMode="stacked", legendDisplay="bottom"),
    "viz_lic_table": chart("splunk.table", "License usage by index (MB); 30-day average over 30 calendar days", "ds_lic_table", count=10),
    "viz_storage": chart("splunk.table", "Index storage", "ds_storage", count=10),
}

inputs = {
    "input_time": {"type": "input.timerange", "title": "Time range",
                   "options": {"token": "global_time", "defaultValue": "-24h@h,now"}},
}

rows = [  # (item, x, y, w, h)
    ("viz_metrics", 0, 0, 360, 110), ("viz_sending", 360, 0, 360, 110), ("viz_subs", 720, 0, 360, 110),
    ("viz_lic_mb", 1080, 0, 360, 110),
    ("viz_ingest", 0, 110, 1440, 340),
    ("viz_devices", 0, 450, 1440, 430),
    ("viz_lic_chart", 0, 880, 720, 340), ("viz_lic_table", 720, 880, 720, 340),
    ("viz_storage", 0, 1220, 1440, 220),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1440},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "Telemetry", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Telemetry Ingest",
    "description": "Metrics per second by pipeline, sending devices and silent ones, gnmic subscriptions, licence use and index storage.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Telemetry Ingest</label>\n'
       '    <description>Metrics per second by pipeline, sending and silent devices, gnmic subscriptions, licence use and index storage</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
