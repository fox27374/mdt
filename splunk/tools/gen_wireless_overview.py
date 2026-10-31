# Generates the Wireless Overview dashboard (Dashboard Studio JSON in views/wireless_overview.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_wireless_overview.py  then scripts/splunk-deploy
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "wireless_overview.xml")

W = '`mdt_metrics_index` site="$site$" extracted_source="$wlc$"'
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

# Radios as "Radio <slot>" columns: slot is not the band on every AP (XOR radios), so no band names.
# A slot without a channel is no radio (2-slot APs report a slot 2 with channel 0): left out.
# ponytail: TX power from the band entry numbered like the slot; an XOR radio serving another band shows that entry's power.
RK = "radio_oper_data_wtp_mac radio_oper_data_radio_slot_id"
RADIOS = (f"| mstats latest(mdt_wl_radio_info_curr_freq) as ch latest(mdt_wl_radio_info_chan_width) as w WHERE {W} BY {RK} "
          f"| join type=left {RK} [| mstats latest(mdt_wl_radio_info_curr_tx_power_in_dbm) as p WHERE {W} BY {RK} radio_band_info_band_id "
          "| where radio_band_info_band_id=radio_oper_data_radio_slot_id | fields - radio_band_info_band_id] "
          f"| join type=left {RK} [| mstats latest_time(_value) as t WHERE {W} metric_name=mdt_wl_radio_info_oper_state BY {RK} oper_state | sort 0 - t | dedup {RK} | fields - t] "
          "| where ch > 0 "
          "| eval cell=if(isnotnull(oper_state) AND oper_state!=\"radio-up\", \"down\", \"ch \".ch.\" / \".w.\" MHz\".if(isnotnull(p), \" / \".p.\" dBm\", \"\")), "
          "col=\"Radio \".radio_oper_data_radio_slot_id | xyseries radio_oper_data_wtp_mac col cell | rename radio_oper_data_wtp_mac as wtp_mac")
# Every AP the WLC knows (name map), joined or not (an AP downloading an image is missing from the join state).
APS = (f"| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_eth_mac BY eth_mac ap_name_mac_map_wtp_name "
       f"| join type=left eth_mac [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_wtp_mac BY ethernet_mac_wtp_mac_map_ethernet_mac wtp_mac "
       "| rename ethernet_mac_wtp_mac_map_ethernet_mac as eth_mac | fields eth_mac wtp_mac] "
       f"| join type=left wtp_mac [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_ap_ip_addr BY oper_data_wtp_mac ap_ip_addr "
       "| where ap_ip_addr!=\"0.0.0.0\" | rename oper_data_wtp_mac as wtp_mac | fields wtp_mac ap_ip_addr] "
       f"| join type=left wtp_mac [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_ap_operation_state BY capwap_data_wtp_mac ap_operation_state "
       "| rename capwap_data_wtp_mac as wtp_mac | fields wtp_mac ap_operation_state] "
       # "default location" is the WLC's value for an AP without one.
       f"| join type=left wtp_mac [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_location BY capwap_data_wtp_mac location "
       "| where location!=\"default location\" | rename capwap_data_wtp_mac as wtp_mac | fields wtp_mac location] "
       # Clients per AP: each client counted once, on the AP it reported last.
       f"| join type=left eth_mac [| mstats latest_time(_value) as t WHERE {W} metric_name=mdt_wl_client_stats_ap_mac_address BY dot11_oper_data_ms_mac_address ap_mac_address "
       "| sort 0 - t | dedup dot11_oper_data_ms_mac_address | stats count as clients by ap_mac_address | rename ap_mac_address as eth_mac] "
       f"| join type=left wtp_mac [{RADIOS}] "
       "| eval State=coalesce(ap_operation_state, \"not joined\")")

# Every client in the last 15 minutes, one row each: latest hostname, IP, SSID, AP and radio. All keys are the client MAC.
def latest(metric, key, field):
    return (f"| mstats latest_time(_value) as t WHERE {W} metric_name={metric} BY {key} {field} "
            f"| sort 0 - t | dedup {key} | rename {key} as mac | fields mac {field}")
CLIENT_LIST = (f"| mstats latest(mdt_wl_client_stats_most_recent_rssi) as rssi latest(mdt_wl_client_stats_most_recent_snr) as snr "
               f"latest(mdt_wl_client_stats_speed) as speed WHERE {W} BY traffic_stats_ms_mac_address | rename traffic_stats_ms_mac_address as mac "
               f"| join type=left mac [{latest('mdt_wl_info_device_hostname', 'client_wsa_info_client_mac', 'device_hostname')}] "
               f"| join type=left mac [{latest('mdt_wl_info_ip_addr', 'sisf_db_mac_mac_addr', 'ip_addr')}] "
               f"| join type=left mac [{latest('mdt_wl_info_vap_ssid', 'dot11_oper_data_ms_mac_address', 'vap_ssid')}] "
               f"| join type=left mac [{latest('mdt_wl_client_stats_ap_mac_address', 'dot11_oper_data_ms_mac_address', 'ap_mac_address')}] "
               f"| join type=left ap_mac_address [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_eth_mac BY eth_mac ap_name_mac_map_wtp_name "
               "| rename eth_mac as ap_mac_address | fields ap_mac_address ap_name_mac_map_wtp_name] "
               f"| join type=left mac [| mstats latest(mdt_wl_info_current_channel) as ch latest(mdt_wl_info_ms_ap_slot_id) as slot WHERE {W} "
               "BY dot11_oper_data_ms_mac_address | rename dot11_oper_data_ms_mac_address as mac] "
               "| eval Band=case(slot==2, \"6 GHz\", ch <= 14, \"2.4 GHz\", ch > 14, \"5 GHz\") "
               "| rename device_hostname as Name, mac as MAC, ip_addr as IP, vap_ssid as SSID, ap_name_mac_map_wtp_name as AP, ch as Channel, "
               "rssi as \"RSSI (dBm)\", snr as \"SNR (dB)\", speed as \"Speed (Mbps)\" "
               "| sort 0 Name MAC | table Name MAC IP SSID AP Band Channel \"RSSI (dBm)\" \"SNR (dB)\" \"Speed (Mbps)\"")

bases = {
    "ds_sites": "| mcatalog values(site) as site WHERE `mdt_metrics_index` | mvexpand site | rename site as label | eval value=label",
    "ds_wlc": "| mcatalog values(extracted_source) as wlc WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_wl_info_ap_ip_addr | mvexpand wlc",
    "ds_clients_now": CLIENTS + "| stats sum(c) as c by _time | stats latest(c) as clients",
    "ds_aps": APS,
    "ds_sys_now": SYS,
    # Configured SSIDs (WLAN config), with their clients; 0 for an SSID nobody is on.
    "ds_client_list": CLIENT_LIST,
    "ds_ssids": (f"| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_ssid BY ssid | eval Clients=0 "
                 f"| append [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_vap_ssid BY vap_ssid dot11_oper_data_ms_mac_address "
                 "| stats dc(dot11_oper_data_ms_mac_address) as Clients by vap_ssid | rename vap_ssid as ssid] "
                 "| stats max(Clients) as Clients by ssid | rename ssid as SSID | sort 0 - Clients SSID"),
    # PHY type as the WLC names it (client-dot11n-24-ghz-prot) shortened to 802.11n; latest per client.
    "ds_phy": (f"| mstats latest_time(_value) as t WHERE {W} metric_name=mdt_wl_info_ewlc_ms_phy_type BY dot11_oper_data_ms_mac_address ewlc_ms_phy_type "
               "| sort 0 - t | dedup dot11_oper_data_ms_mac_address "
               "| eval PHY=replace(ewlc_ms_phy_type, \"^client-dot11([a-z]+).*\", \"802.11\\1\") | stats count as Clients by PHY | sort PHY"),
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
    "ds_aps_joined": ("ds_aps", "| stats count as total count(eval(State==\"registered\")) as joined "
                      "| eval aps=joined.\" / \".total, short=total - joined"),
    # A not-joined AP's radio values are stale: left out.
    "ds_ap_table": ("ds_aps", "| foreach \"Radio *\" [eval <<FIELD>>=if(State==\"registered\", '<<FIELD>>', null())] "
                    "| fillnull value=0 clients | rename ap_name_mac_map_wtp_name as AP, ap_ip_addr as IP, location as Location, clients as Clients "
                    "| sort AP | table AP IP State Location Clients \"Radio *\""),
    **{f"ds_{k}": ("ds_rf", f"| timechart max({k}) by band") for k in ("tx", "rx", "noise", "nonwifi")},
}
LAST15 = {"earliest": "-15m", "latest": "now"}
WINDOW = {k: LAST15 for k in ("ds_clients_now", "ds_aps", "ds_client_list", "ds_sys_now", "ds_ssids", "ds_phy")}

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
    "viz_aps": tile("APs joined (last 15 min)", "ds_aps_joined", majorValue="> primary | seriesByName(\"aps\")",
                    majorColor="> primary | seriesByName(\"short\") | lastPoint() | rangeValue(shortColors)"),
    "viz_cpu_now": tile("WLC CPU (last 15 min)", "ds_cpu_now", unit="%", unitPosition="after"),
    "viz_mem_now": tile("WLC memory (last 15 min)", "ds_mem_now", unit="%", unitPosition="after", numberPrecision=1),
    "viz_ssids": chart("splunk.table", "SSIDs and their clients (last 15 min)", "ds_ssids", count=10),
    "viz_phy": chart("splunk.bar", "Clients by PHY (last 15 min)", "ds_phy", legendDisplay="off"),
    "viz_ap_table": {**chart("splunk.table", "Access points (last 15 min): radio = channel / width / TX power", "ds_ap_table", count=20),
                     "context": {"stateColors": [{"match": "registered", "value": "#53a051"}, {"match": "not joined", "value": "#dc4e41"}]}},
    # Click a client: Wireless Client Details for it, same site, WLC and time range (same tab, like the other drilldowns).
    "viz_client_list": {**chart("splunk.table", "Clients (last 15 min). Click a client to open its details", "ds_client_list", count=20),
                        "eventHandlers": [{"type": "drilldown.customUrl", "options": {
                            "url": "/app/mdt_infra_monitoring/wireless_client_details?form.site=$site$&form.wlc=$wlc$&form.tk_client=$row.MAC.value$&form.global_time.earliest=$global_time.earliest$&form.global_time.latest=$global_time.latest$",
                            "newTab": False}}]},
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
    "input_site": {"type": "input.dropdown", "title": "Site", "dataSources": {"primary": "ds_sites"},
                   "options": {"token": "site", "defaultValue": "ibk-lab", "items": ">frame(label, value) | objects()"},
                   "context": {"label": ">primary | seriesByName(\"label\") | renameSeries(\"label\")",
                               "value": ">primary | seriesByName(\"value\") | renameSeries(\"value\")"}},
    "input_wlc": {"type": "input.dropdown", "title": "WLC", "dataSources": {"primary": "ds_wlc"},
                  "options": {"token": "wlc", "selectFirstSearchResult": True, "items": ">frame(label, value) | objects()"},
                  "context": {"label": ">primary | seriesByName(\"wlc\") | renameSeries(\"label\")",
                              "value": ">primary | seriesByName(\"wlc\") | renameSeries(\"value\")"}},
}

viz["viz_aps"]["context"] = {"shortColors": [{"to": 1, "value": "#708794"}, {"from": 1, "value": "#dc4e41"}]}
viz["viz_ap_table"]["options"]["columnFormat"] = {"State": {"rowBackgroundColors": "> table | seriesByName(\"State\") | matchValue(stateColors)"}}

rows = [  # (item, x, y, w, h)
    ("viz_clients_now", 0, 0, 360, 130), ("viz_aps", 360, 0, 360, 130), ("viz_cpu_now", 720, 0, 360, 130), ("viz_mem_now", 1080, 0, 360, 130),
    ("viz_clients", 0, 130, 720, 300), ("viz_ssids", 720, 130, 360, 300), ("viz_phy", 1080, 130, 360, 300),
    ("viz_ap_table", 0, 430, 1440, 260),
    ("viz_client_list", 0, 690, 1440, 300),
    ("viz_tx", 0, 990, 720, 300), ("viz_rx", 720, 990, 720, 300),
    ("viz_noise", 0, 1290, 720, 300), ("viz_nonwifi", 720, 1290, 720, 300),
    ("viz_sys", 0, 1590, 1440, 260),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_site", "input_wlc"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1850},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "WLC", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Wireless Overview",
    "description": "One WLC: clients and APs, every client (click for its details), SSIDs and PHY types, access points with their radios, per-band utilization, noise and interference of the busiest AP, CPU and memory.",
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
