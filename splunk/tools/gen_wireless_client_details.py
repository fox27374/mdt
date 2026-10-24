# Generates the Wireless Client Details dashboard (Dashboard Studio JSON in views/wireless_client_details.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_wireless_client_details.py  then scripts/splunk-deploy
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "wireless_client_details.xml")

W = 'index=cisco_metrics extracted_source="$wlc$"'
C = "$tk_client$"
# Latest hostname per client MAC (a client can rename itself).
HOSTNAMES = (f"| mstats latest_time(_value) as t WHERE {W} metric_name=mdt_wl_info_device_hostname BY client_wsa_info_client_mac device_hostname "
             "| sort 0 - t | dedup client_wsa_info_client_mac | rename client_wsa_info_client_mac as mac | fields mac device_hostname")
# AP by Ethernet MAC (what a client's AP reference carries): name, and the IP via the radio MAC. APs without an address report 0.0.0.0.
APS = (f"| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_eth_mac BY eth_mac ap_name_mac_map_wtp_name "
       f"| join type=left eth_mac [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_wtp_mac BY ethernet_mac_wtp_mac_map_ethernet_mac wtp_mac "
       "| rename ethernet_mac_wtp_mac_map_ethernet_mac as eth_mac] "
       f"| join type=left wtp_mac [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_ap_ip_addr BY oper_data_wtp_mac ap_ip_addr "
       "| where ap_ip_addr!=\"0.0.0.0\" | rename oper_data_wtp_mac as wtp_mac] "
       f"| join type=left wtp_mac [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_info_location BY capwap_data_wtp_mac location "
       "| where location!=\"default location\" | rename capwap_data_wtp_mac as wtp_mac | fields wtp_mac location] "
       "| rename ap_name_mac_map_wtp_name as ap_name | fields eth_mac ap_name ap_ip_addr location")

# Rows for ds_roam_timeline (assoc_time is UTC, "...Z" or "+00:00"; first 19 chars parsed): input has run_latency, slot, roam_type, ap_name, bssid, assoc_time (one per association).
ROAM_ROWS = ("| addinfo | eval start=strptime(substr(assoc_time, 1, 19).\" +0000\", \"%Y-%m-%dT%H:%M:%S %z\") "
             "| sort 0 - start | streamstats current=f last(start) as next_start "
             "| eval stop=coalesce(next_start, min(now(), info_max_time)), bar_start=max(start, info_min_time), ap=coalesce(ap_name, bssid), slot_n=tonumber(slot) "
             "| eval band=case(slot_n==0, \"2.4 GHz\", slot_n==1, \"5 GHz\", slot_n==2, \"6 GHz\", true(), \"slot \".slot) "
             "| eval roam=case(match(roam_type, \"11r\"), \"802.11r\", match(roam_type, \"okc\"), \"OKC\", match(roam_type, \"none\"), \"none\", true(), replace(roam_type, \"^dot11-roam-type-\", \"\")) "
             "| eval category_dot=case(match(roam_type, \"none\"), \"Join\", run_latency < 100, \"Good\", run_latency <= 500, \"Slow\", true(), \"Bad\") "
             # Dots only for associations that started inside the range; bars for any that reach into it.
             "| eval kind=if(start >= info_min_time, mvappend(\"bar\", \"dot\"), \"bar\") | mvexpand kind "
             "| eval _time=if(kind==\"bar\", bar_start, start), duration=if(kind==\"bar\", stop - bar_start, null()), "
             "category=if(kind==\"bar\", \"Connected\", category_dot) "
             "| where kind==\"dot\" OR duration > 0 "
             "| rename roam as \"Roam type\", band as Band, bssid as BSSID, run_latency as \"Roam time (ms)\" "
             "| fields _time ap duration category \"Roam type\" Band BSSID \"Roam time (ms)\" | sort 0 _time")

bases = {
    "ds_wlc": "| mcatalog values(extracted_source) as wlc WHERE index=cisco_metrics metric_name=mdt_wl_info_ap_ip_addr | mvexpand wlc",
    "ds_clients": (f"| mstats latest(_value) WHERE {W} metric_name=mdt_wl_client_stats_most_recent_rssi BY traffic_stats_ms_mac_address "
                   f"| rename traffic_stats_ms_mac_address as mac | join type=left mac [{HOSTNAMES}] "
                   "| eval label=if(isnotnull(device_hostname), device_hostname.\" (\".mac.\")\", mac) | sort label | table label mac"),
    # Identity and radio values now; each appendcols adds one column, empty when the client sent nothing.
    "ds_now": (f"| mstats latest(mdt_wl_client_stats_most_recent_rssi) as rssi latest(mdt_wl_client_stats_most_recent_snr) as snr "
               f"latest(mdt_wl_client_stats_speed) as speed WHERE {W} traffic_stats_ms_mac_address=\"{C}\" "
               f"| appendcols [{HOSTNAMES} | where mac=\"{C}\" | fields device_hostname] "
               f"| appendcols [| mstats latest_time(_value) as t WHERE {W} metric_name=mdt_wl_info_ip_addr sisf_db_mac_mac_addr=\"{C}\" BY ip_addr "
               "| sort - t | head 1 | fields ip_addr] "
               f"| appendcols [| mstats latest_time(_value) as t WHERE {W} metric_name=mdt_wl_info_vap_ssid dot11_oper_data_ms_mac_address=\"{C}\" BY vap_ssid "
               "| sort - t | head 1 | fields vap_ssid] "
               f"| appendcols [| mstats latest(mdt_wl_info_current_channel) as ch latest(mdt_wl_info_ms_ap_slot_id) as slot WHERE {W} dot11_oper_data_ms_mac_address=\"{C}\"] "
               f"| appendcols [| mstats latest_time(_value) as t WHERE {W} metric_name=mdt_wl_info_ewlc_ms_phy_type dot11_oper_data_ms_mac_address=\"{C}\" BY ewlc_ms_phy_type "
               "| sort - t | head 1 | eval phy=replace(ewlc_ms_phy_type, \"^client-dot11([a-z]+).*\", \"802.11\\\\1\") | fields phy] "
               "| eval device_hostname=coalesce(device_hostname, \"(none)\"), "
               "band=case(slot==2, \"6 GHz\", ch <= 14, \"2.4 GHz\", ch > 14, \"5 GHz\"), "
               "radio=if(isnotnull(ch), band.\" ch \".ch.if(isnotnull(phy), \", \".phy, \"\"), null())"),
    "ds_metrics": (f"| mstats latest(mdt_wl_client_stats_most_recent_rssi) as rssi latest(mdt_wl_client_stats_most_recent_snr) as snr "
                   f"latest(mdt_wl_client_stats_speed) as speed max(mdt_wl_client_stats_data_retries) as retries max(mdt_wl_client_stats_pkts_tx) as ptx "
                   f"max(mdt_wl_client_stats_bytes_tx) as btx max(mdt_wl_client_stats_bytes_rx) as brx "
                   f"WHERE {W} traffic_stats_ms_mac_address=\"{C}\" span=1m "
                   # Counters: delta to the previous point, nothing across a reset. A packet can be retried several times, so retry % = retries / (packets sent + retries).
                   "| sort 0 _time | streamstats current=f last(retries) as pr last(ptx) as pp last(btx) as pbt last(brx) as pbr last(_time) as pt "
                   "| eval dr=if(retries >= pr, retries - pr, null()), dp=if(ptx >= pp, ptx - pp, null()), dt=_time - pt "
                   "| eval tx_kbps=if(btx >= pbt, round((btx - pbt) * 8 / dt / 1000, 1), null()), rx_kbps=if(brx >= pbr, round((brx - pbr) * 8 / dt / 1000, 1), null())"),
    # One row per stay on an AP: a new stay starts when the AP changes or the client was gone for over 5 minutes.
    "ds_roam": (f"| mstats latest(_value) WHERE {W} metric_name=mdt_wl_client_stats_ap_mac_address dot11_oper_data_ms_mac_address=\"{C}\" "
                "span=1m BY ap_mac_address | rename ap_mac_address as eth_mac | sort 0 _time "
                "| streamstats current=f last(eth_mac) as prev last(_time) as pt "
                "| eval new=if(isnull(prev) OR prev!=eth_mac OR _time - pt > 300, 1, 0) | streamstats sum(new) as stay "
                "| stats min(_time) as first max(_time) as last first(eth_mac) as eth_mac by stay "
                f"| join type=left eth_mac [{APS}] | sort - last"),
    # One row per association from the WLC history (mm-if-client-history). Each association gives a bar (time on
    # the AP, duration in seconds up to the next association or the range end) and a dot (roam time category).
    "ds_roam_timeline": (f"| mstats latest(_value) as run_latency WHERE {W} metric_name=mdt_wl_client_roam_run_latency client_mac=\"{C}\" "
                         "BY ap_name bssid roam_type slot assoc_time | dedup assoc_time " + ROAM_ROWS),
}
chains = {  # name: (base, post-process)
    "ds_rssi": ("ds_metrics", "| rename rssi as \"RSSI (dBm)\" | fields _time \"RSSI (dBm)\""),
    "ds_snr": ("ds_metrics", "| rename snr as \"SNR (dB)\" | fields _time \"SNR (dB)\""),
    "ds_speed": ("ds_metrics", "| rename speed as \"Speed (Mb/s)\" | fields _time \"Speed (Mb/s)\""),
    # 5-minute buckets: a quiet client sends a handful of packets a minute, too few for a steady ratio.
    "ds_retries": ("ds_metrics", "| bin _time span=5m | stats sum(dr) as dr sum(dp) as dp by _time | where _time + 300 <= now() "
                   "| eval \"Retry %\"=if(dp + dr > 0, round(dr / (dp + dr) * 100, 1), null()), \"Problem above\"=10 | fields _time \"Retry %\" \"Problem above\""),
    "ds_throughput": ("ds_metrics", "| rename tx_kbps as \"TX (kb/s)\", rx_kbps as \"RX (kb/s)\" | fields _time \"TX (kb/s)\" \"RX (kb/s)\""),
    # AP tile: the stay that reached into the last 15 minutes.
    "ds_ap_now": ("ds_roam", "| where last >= relative_time(now(), \"-15m\") | head 1 | eval ap=coalesce(ap_name, eth_mac) | fields ap"),
    "ds_roam_table": ("ds_roam", "| eval AP=coalesce(ap_name, eth_mac), \"AP IP\"=ap_ip_addr, Location=location, "
                      "\"First seen\"=strftime(first, \"%Y-%m-%d %H:%M\"), \"Last seen\"=strftime(last, \"%Y-%m-%d %H:%M\") "
                      "| table AP \"AP IP\" Location \"First seen\" \"Last seen\""),
}
LAST15 = {"earliest": "-15m", "latest": "now"}
WINDOW = {"ds_now": LAST15}

dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q, **({"queryParameters": WINDOW[k]} if k in WINDOW else {})}}
               for k, q in bases.items()}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})

def tile(title, d, field, **opts):
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": d},
            "options": {"majorValue": f"> primary | seriesByName(\"{field}\")", "majorColor": "#708794", **opts}}

def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}

viz = {
    "viz_name": tile("Client name", "ds_now", "device_hostname"),
    "viz_ip": tile("Client IP", "ds_now", "ip_addr"),
    "viz_ssid": tile("SSID", "ds_now", "vap_ssid"),
    "viz_ap": tile("AP", "ds_ap_now", "ap"),
    "viz_rssi_now": tile("RSSI", "ds_now", "rssi", unit="dBm", unitPosition="after"),
    "viz_snr_now": tile("SNR", "ds_now", "snr", unit="dB", unitPosition="after"),
    "viz_speed_now": tile("Speed", "ds_now", "speed", unit="Mb/s", unitPosition="after"),
    "viz_radio": tile("Radio", "ds_now", "radio"),
    "viz_rssi": chart("splunk.line", "RSSI (dBm)", "ds_rssi", legendDisplay="off"),
    "viz_snr": chart("splunk.line", "SNR (dB)", "ds_snr", legendDisplay="off"),
    "viz_speed": chart("splunk.line", "Speed (Mb/s)", "ds_speed", legendDisplay="off"),
    "viz_retries": chart("splunk.line", "Retry %: retries as share of all transmissions (5 min)", "ds_retries", legendDisplay="bottom",
                         lineDashStylesByField={"Problem above": "dash"}, seriesColorsByField={"Retry %": "#1e93c6", "Problem above": "#dc4e41"}),
    "viz_throughput": chart("splunk.line", "Throughput (kb/s)", "ds_throughput", legendDisplay="bottom"),
    "viz_roam_timeline": chart("splunk.timeline", "Roaming timeline: one lane per AP; bars = time on the AP, dots = associations coloured by roam time (green < 100 ms, yellow 100-500 ms, red > 500 ms, grey first join)",
                               "ds_roam_timeline", x='> primary | seriesByName("_time")', y='> primary | seriesByName("ap")',
                               duration='> primary | seriesByName("duration")', durationUnit="seconds",
                               category='> primary | seriesByName("category")', dataColors='> primary | seriesByName("category") | matchValue(categoryColors)',
                               additionalTooltipFields=["Roam type", "Band", "BSSID", "Roam time (ms)"], legendDisplay="bottom"),
    "viz_roam": chart("splunk.table", "APs the client was on (a gap over 5 minutes starts a new row)", "ds_roam_table", count=20),
}

inputs = {
    "input_time": {"type": "input.timerange", "title": "Time range",
                   "options": {"token": "global_time", "defaultValue": "-4h@m,now"}},
    "input_wlc": {"type": "input.dropdown", "title": "WLC", "dataSources": {"primary": "ds_wlc"},
                  "options": {"token": "wlc", "selectFirstSearchResult": True, "items": ">frame(label, value) | objects()"},
                  "context": {"label": ">primary | seriesByName(\"wlc\") | renameSeries(\"label\")",
                              "value": ">primary | seriesByName(\"wlc\") | renameSeries(\"value\")"}},
    "input_client": {"type": "input.dropdown", "title": "Client", "dataSources": {"primary": "ds_clients"},
                     "options": {"token": "tk_client", "selectFirstSearchResult": True, "items": ">frame(label, value) | objects()"},
                     "context": {"label": ">primary | seriesByName(\"label\") | renameSeries(\"label\")",
                                 "value": ">primary | seriesByName(\"mac\") | renameSeries(\"value\")"}},
}

viz["viz_roam_timeline"]["context"] = {"categoryColors": [
    {"match": "Connected", "value": "#5C6773"}, {"match": "Join", "value": "#C9D1D9"},
    {"match": "Good", "value": "#118832"}, {"match": "Slow", "value": "#CBA700"}, {"match": "Bad", "value": "#D41F1F"}]}

tiles = ["viz_name", "viz_ip", "viz_ssid", "viz_ap", "viz_radio", "viz_rssi_now", "viz_snr_now", "viz_speed_now"]
TW = [220, 160, 160, 180, 260, 150, 150, 160]  # widths add up to 1440
rows = [(t, sum(TW[:i]), 0, w, 110) for i, (t, w) in enumerate(zip(tiles, TW))] + [  # (item, x, y, w, h)
    ("viz_rssi", 0, 110, 720, 280), ("viz_snr", 720, 110, 720, 280),
    ("viz_speed", 0, 390, 720, 280), ("viz_retries", 720, 390, 720, 280),
    ("viz_throughput", 0, 670, 1440, 280),
    ("viz_roam_timeline", 0, 950, 1440, 320),
    ("viz_roam", 0, 1270, 1440, 300),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_wlc", "input_client"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 1570},
        "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in rows]}},
    "tabs": {"items": [{"label": "Client", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Wireless Client Details",
    "description": "One wireless client: name, IP, SSID, AP and radio, RSSI, SNR, speed, retry % and throughput over time, and the APs it was on.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Wireless Client Details</label>\n'
       '    <description>One wireless client: identity, AP, RSSI, SNR, speed, retries and roaming</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
