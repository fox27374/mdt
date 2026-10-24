# Generates the Wireless Overview dashboard (Dashboard Studio JSON in views/wireless_overview.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_wireless_overview.py  then scripts/splunk-deploy
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "wireless_overview.xml")

W = 'index=cisco_metrics extracted_source="$wlc$"'
BAND = lambda f: f'band=case({f}=0, "2.4 GHz", {f}=1, "5 GHz", {f}=2, "6 GHz")'
COLORS = {"2.4 GHz": "#1e93c6", "5 GHz": "#f2b827", "6 GHz": "#d6563c"}
# gnmic samples every 30s: take the latest value per series and minute, then add up across APs (summing raw samples counts each twice).
# Every per-minute search leaves out the current minute: not every series has reported in it yet.
CLIENTS = (f"| mstats latest(mdt_wl_ap_stats_num_assoc_clients) as c WHERE {W} span=1m "
           "BY ssid_counters_wtp_mac ssid_counters_slot_id ssid_counters_wlan_id | where _time + 60 <= now() ")
# Memory pools (memory_statistic_name) added up; CPU is the WLC's one-minute average.
SYS = (f"| mstats latest(mdt_xe_mem_stats_used_memory) as used latest(mdt_xe_mem_stats_total_memory) as total "
       f"WHERE {W} span=1m BY memory_statistic_name | stats sum(used) as used sum(total) as total by _time "
       f"| join type=left _time [| mstats avg(mdt_xe_cpu_stats_one_minute) as cpu WHERE {W} span=1m] "
       "| where _time + 60 <= now() | eval \"CPU %\"=round(cpu, 0), \"Memory %\"=round(used / total * 100, 1) | fields _time \"CPU %\" \"Memory %\"")

bases = {
    "ds_wlc": "| mcatalog values(extracted_source) as wlc WHERE index=cisco_metrics metric_name=mdt_wl_info_ap_ip_addr | mvexpand wlc",
    "ds_clients_now": CLIENTS + "| stats sum(c) as c by _time | stats latest(c) as clients",
    "ds_aps": f"| mstats latest(mdt_wl_info_ap_ip_addr) WHERE {W} BY oper_data_wtp_mac | stats count as aps",
    "ds_sys_now": SYS,
    "ds_ssids": f"| mstats latest(mdt_wl_info_vap_ssid) WHERE {W} BY vap_ssid dot11_oper_data_ms_mac_address "
                "| stats dc(dot11_oper_data_ms_mac_address) as Clients by vap_ssid | rename vap_ssid as SSID | sort - Clients",
    "ds_clients": CLIENTS + f"| stats sum(c) as c by _time ssid_counters_slot_id | eval {BAND('ssid_counters_slot_id')} "
                  "| timechart avg(c) as c by band | fillnull value=0",
    "ds_sys": SYS,
    # Worst AP per band: max across APs, so one busy cell is not averaged away.
    "ds_rf": (f"| mstats max(mdt_wl_ap_stats_tx_util_percentage) as tx max(mdt_wl_ap_stats_rx_util_percentage) as rx "
              f"max(mdt_wl_ap_stats_rx_noise_channel_utilization) as noise max(mdt_wl_ap_stats_non_wifi_inter) as nonwifi "
              f"WHERE {W} span=1m BY rrm_measurement_radio_slot_id | where _time + 60 <= now() | eval {BAND('rrm_measurement_radio_slot_id')}"),
}
chains = {  # name: (base, post-process)
    "ds_cpu_now": ("ds_sys_now", "| stats latest(\"CPU %\") as cpu"),
    "ds_mem_now": ("ds_sys_now", "| stats latest(\"Memory %\") as mem"),
    **{f"ds_{k}": ("ds_rf", f"| timechart max({k}) by band") for k in ("tx", "rx", "noise", "nonwifi")},
}
LAST15 = {"earliest": "-15m", "latest": "now"}
WINDOW = {k: LAST15 for k in ("ds_clients_now", "ds_aps", "ds_sys_now", "ds_ssids")}

dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q, **({"queryParameters": WINDOW[k]} if k in WINDOW else {})}}
               for k, q in bases.items()}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})

def tile(title, d, **opts):
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": d},
            "options": {"majorColor": "#708794", **opts}}

def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}

def band_chart(title, d):
    return chart("splunk.line", title, d, seriesColorsByField=COLORS, legendDisplay="bottom", nullValueDisplay="connect")

viz = {
    "viz_clients_now": tile("Connected clients (last 15 min)", "ds_clients_now"),
    "viz_aps": tile("Connected APs (last 15 min)", "ds_aps"),
    "viz_cpu_now": tile("WLC CPU (last 15 min)", "ds_cpu_now", unit="%", unitPosition="after"),
    "viz_mem_now": tile("WLC memory (last 15 min)", "ds_mem_now", unit="%", unitPosition="after", numberPrecision=1),
    "viz_ssids": chart("splunk.table", "SSIDs with clients (last 15 min)", "ds_ssids", count=10),
    "viz_clients": chart("splunk.area", "Clients by band", "ds_clients", stackMode="stacked", seriesColorsByField=COLORS, legendDisplay="bottom"),
    "viz_sys": chart("splunk.line", "WLC CPU and memory %", "ds_sys", legendDisplay="bottom", yAxisMin=0),
    "viz_tx": band_chart("TX utilization by band, busiest AP", "ds_tx"),
    "viz_rx": band_chart("RX utilization by band, busiest AP", "ds_rx"),
    "viz_noise": band_chart("Noise channel utilization by band, worst AP", "ds_noise"),
    "viz_nonwifi": band_chart("Non-WiFi interference by band, worst AP", "ds_nonwifi"),
}

inputs = {
    "input_time": {"type": "input.timerange", "title": "Time range",
                   "options": {"token": "global_time", "defaultValue": "-4h@m,now"}},
    "input_wlc": {"type": "input.dropdown", "title": "WLC", "dataSources": {"primary": "ds_wlc"},
                  "options": {"token": "wlc", "selectFirstSearchResult": True, "items": ">frame(label, value) | objects()"},
                  "context": {"label": ">primary | seriesByName(\"wlc\") | renameSeries(\"label\")",
                              "value": ">primary | seriesByName(\"wlc\") | renameSeries(\"value\")"}},
}

rows = [  # (item, x, y, w, h)
    ("viz_clients_now", 0, 0, 288, 130), ("viz_aps", 288, 0, 288, 130), ("viz_cpu_now", 576, 0, 288, 130),
    ("viz_mem_now", 864, 0, 288, 130), ("viz_ssids", 1152, 0, 288, 130),
    ("viz_clients", 0, 130, 960, 300), ("viz_sys", 960, 130, 480, 300),
    ("viz_tx", 0, 430, 720, 300), ("viz_rx", 720, 430, 720, 300),
    ("viz_noise", 0, 730, 720, 300), ("viz_nonwifi", 720, 730, 720, 300),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_wlc"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1030},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "WLC", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Wireless Overview",
    "description": "One WLC: clients and APs, CPU and memory, clients by band, and per-band utilization, noise and interference of the busiest AP.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Wireless Overview</label>\n'
       '    <description>One WLC: clients, APs, CPU and memory, and per-band RF utilization of the busiest AP</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
