# Generates the Client Details dashboard (Dashboard Studio JSON in views/client_details.xml): one client, on the Wireless tab
# (layout_1) or the Wired tab (layout_2).
# Edit this script, not the XML:  python3 splunk/tools/gen_client_details.py  then scripts/splunk-deploy
import json, os, sys
from client_sources import WIRED_BODY, ARP_IPS

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "client_details.xml")

W = '`mdt_metrics_index` site="$site$" extracted_source="$wlc$"'
C = "$tk_client$"
# Latest hostname per client MAC (a client can rename itself). Last 30 days, whatever the search's range: the WLC sometimes
# reports a connected client's hostname once and then no more (seen on an iPhone).
HOSTNAMES = (f"| mstats latest_time(_value) as t WHERE {W} metric_name=mdt_wl_info_device_hostname earliest=-30d latest=now BY client_wsa_info_client_mac device_hostname "
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

# ds_roam_timeline feeds the roam_timeline viz with one search. kind=assoc: one row per association from the WLC
# history (t: epoch of assoc_time, UTC "...Z" or "+00:00", first 19 chars parsed; category: Join / Good < 100 ms /
# Slow 100-500 ms / Bad). kind=seen: one row per minute the client reported (for gaps and last seen).
# addinfo adds info_min_time / info_max_time (the dashboard range). Stays and gaps are built in the viz.
ROAM_TIMELINE = (f"| mstats latest(_value) as run_latency WHERE {W} metric_name=mdt_wl_client_roam_run_latency client_mac=\"{C}\" "
                 "BY ap_name bssid roam_type slot assoc_time | dedup assoc_time "
                 "| eval kind=\"assoc\", t=strptime(substr(assoc_time, 1, 19).\" +0000\", \"%Y-%m-%dT%H:%M:%S %z\"), ap=coalesce(ap_name, bssid), slot_n=tonumber(slot) "
                 "| eval band=case(slot_n==0, \"2.4 GHz\", slot_n==1, \"5 GHz\", slot_n==2, \"6 GHz\", true(), \"slot \".slot) "
                 "| eval roam=case(match(roam_type, \"11r\"), \"802.11r\", match(roam_type, \"okc\"), \"OKC\", match(roam_type, \"none\"), \"none\", true(), replace(roam_type, \"^dot11-roam-type-\", \"\")) "
                 "| eval category=case(match(roam_type, \"none\"), \"Join\", run_latency < 100, \"Good\", run_latency <= 500, \"Slow\", true(), \"Bad\") "
                 "| fields kind t ap band roam run_latency category bssid "
                 f"| append [| mstats latest(_value) WHERE {W} metric_name=mdt_wl_client_stats_ap_mac_address dot11_oper_data_ms_mac_address=\"{C}\" span=1m BY ap_mac_address "
                 "| stats count by _time | eval kind=\"seen\", t=_time | fields kind t] "
                 # tz_offset: the viewer's Splunk time zone (strftime uses it), so the viz shows the same clock as the other panels.
                 "| addinfo | eval tz_offset=strftime(now(), \"%z\") | sort 0 t")

bases = {
    "ds_sites": "| mcatalog values(site) as site WHERE `mdt_metrics_index` | mvexpand site | rename site as label | eval value=label",
    "ds_wlc": "| mcatalog values(extracted_source) as wlc WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_wl_info_ap_ip_addr | mvexpand wlc",
    "ds_clients": (f"| mstats latest(_value) WHERE {W} metric_name=mdt_wl_client_stats_most_recent_rssi BY traffic_stats_ms_mac_address "
                   f"| rename traffic_stats_ms_mac_address as mac | join type=left mac [{HOSTNAMES}] "
                   "| eval label=if(isnotnull(device_hostname), device_hostname.\" (\".mac.\")\", mac) | sort label | table label mac"),
    # Identity and radio values now; each appendcols adds one column, empty when the client sent nothing.
    # Not seen in the last 15 minutes: the name tile says "Not connected" and the radio tile when it was last seen
    # (last 30 days); the other tiles show "-" instead of an empty-result warning.
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
               f"| appendcols [| mstats latest_time(_value) as last_seen WHERE {W} metric_name=mdt_wl_client_stats_most_recent_rssi traffic_stats_ms_mac_address=\"{C}\" earliest=-30d latest=now] "
               "| append [| makeresults | eval connected=0 | fields - _time] | head 1 "
               "| eval connected=if(isnotnull(rssi), 1, 0), "
               "band=case(slot==2, \"6 GHz\", ch <= 14, \"2.4 GHz\", ch > 14, \"5 GHz\"), "
               "radio=if(isnotnull(ch), band.\" ch \".ch.if(isnotnull(phy), \", \".phy, \"\"), null()) "
               "| eval device_hostname=if(connected==1, coalesce(device_hostname, \"(none)\"), \"Not connected\"), "
               "radio=if(connected==1, radio, if(isnotnull(last_seen), \"Last seen \".strftime(last_seen, if(last_seen < relative_time(now(), \"-24h\"), \"%Y-%m-%d %H:%M\", \"%H:%M\")), \"Not seen in 30 days\")) "
               "| foreach ip_addr vap_ssid rssi snr speed [eval <<FIELD>>=coalesce(<<FIELD>>, \"-\")]"),
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
    "ds_roam_timeline": ROAM_TIMELINE,
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
    "ds_ap_now": ("ds_roam", "| where last >= relative_time(now(), \"-15m\") | head 1 | eval ap=coalesce(ap_name, eth_mac) | appendpipe [| stats count | where count=0 | eval ap=\"-\"] | fields ap"),
    "ds_roam_table": ("ds_roam", "| eval AP=coalesce(ap_name, eth_mac), \"AP IP\"=ap_ip_addr, Location=location, "
                      "\"First seen\"=strftime(first, \"%Y-%m-%d %H:%M\"), \"Last seen\"=strftime(last, \"%Y-%m-%d %H:%M\") "
                      "| table AP \"AP IP\" Location \"First seen\" \"Last seen\""),
}
LAST15 = {"earliest": "-15m", "latest": "now"}
WINDOW = {"ds_now": LAST15}

# ---- Wired tab: one wired client on its access port (client_sources.py holds the MAC table and ARP sources) ----
# Client ports: a MAC on a port with no CDP neighbour (prio=1) that is not a port-channel. Wired clients are the MAC table
# entries only; the port's status, PoE and traffic come from the port the client was last seen on.
PO = "NOT match(port, \"(?i)^po\")"
WD = "$tk_wired$"
# Port names: the full telemetry name to the short one, as Interface Details does (SHORT there): Te1/0/3 for TenGigabitEthernet1/0/3.
def short(f):
    return ("case(" + ", ".join(f"match({f}, \"^{l}\\d\"), replace({f}, \"^{l}\", \"{s}\")" for l, s in [
        ("TenGigabitEthernet", "Te"), ("TwentyFiveGigE", "Twe"), ("TwoGigabitEthernet", "Tw"), ("FortyGigabitEthernet", "Fo"), ("FiftyGigE", "Fi"),
        ("HundredGigE", "Hu"), ("FastEthernet", "Fa"), ("AppGigabitEthernet", "Ap"), ("GigabitEthernet", "Gi"), ("Ethernet", "Eth"), ("(?i)port-channel", "Po")])
        + f", true(), {f})")

# Counters of the port per 5-minute bucket: Interface Details' FLOW for this side only (no far end: a client port has no CDP neighbour).
PAIRS = [("in_oct", "in_octets"), ("out_oct", "out_octets"), ("in_err", "in_errors"), ("out_err", "out_errors"),
         ("crc", "crc"), ("ov_rx", "oversize_rx"), ("un_rx", "undersize_rx"), ("frag_rx", "fragment_rx"),
         ("jab_rx", "jabber_rx"), ("tx_err", "tx_errors"), ("ov_tx", "oversize_tx")]
RAW = [r for _, r in PAIRS]
CNT = [d for d, _ in PAIRS]
SUMS = " ".join(f"sum({d}) as {d} count({d}) as {d}_n" for d in CNT)
# The port the table's newest sighting names: the base's first row (smart source, sorted newest first).
W_NODE, W_IF = "$wired_seen:result.node$", "$wired_seen:result.iface$"
FLOW_PORT = (
    f"| `mdt_if_counters({W_NODE},{W_IF}, $site$)` | append [| `mdt_if_detail({W_NODE},{W_IF})`] "
    "| stats max(in_octets) as in_octets max(out_octets) as out_octets max(in_errors) as in_errors max(out_errors) as out_errors "
    + " ".join(f"max({r}) as {r}" for r in RAW[4:]) + " by _time node interface "
    "| sort 0 node interface _time "
    "| streamstats current=f window=1 last(_time) as p_t " + " ".join(f"last({r}) as p_{r}" for r in RAW) + " by node interface "
    "| eval dt=_time - p_t | where dt > 0 "
    "| eval " + ", ".join(f"{d}=if({r} >= p_{r}, {r} - p_{r}, null())" for d, r in PAIRS) + " "
    "| eval in_bps=in_oct * 8 / dt, out_bps=out_oct * 8 / dt "
    f"| bin _time span=5m | stats avg(in_bps) as in_bps avg(out_bps) as out_bps {SUMS} by _time node interface "
    "| where _time + 300 <= now()"
)
# Syslog naming the port by its path (as Interface Details LOGS).
tokpath = f"if(match(\"{W_IF}\", \"^\\D\"), replace(\"{W_IF}\", \"^\\D+\", \"\"), \"{W_IF}\")"
LOGS_PORT = (f"`mdt_syslog_index` host=\"{W_NODE}\" | eval severity=mvindex(severity, 0), message=mvindex(message, 0) "
             f"| eval tp={tokpath} | where match(message, \"(?<![\\d/])\" . tp . \"(?![\\d/])\") "
             "| table _time severity message | sort - _time | head 200")

wired_bases = {
    # Wired clients of the site on client ports, label "name (mac)" (reverse DNS of the first ARP IP) or the MAC.
    "ds_wired_clients": (WIRED_BODY + f" | where prio=1 AND {PO} | sort 0 - t | dedup mac "
                         f"| join type=left mac [{ARP_IPS}] | eval ip=mvindex(ips, 0) | lookup dnslookup clientip AS ip OUTPUT clienthost AS dns_name "
                         "| eval label=if(isnotnull(dns_name), dns_name.\" (\".mac.\")\", mac), value=mac | sort label | table label value"),
    # Every sighting of the client on a client port in the range, newest first: the first row is the current one.
    # Port status and PoE of the port join on the same key as the MAC table (ik).
    "ds_wired_seen": (WIRED_BODY + f" | where prio=1 AND {PO} AND mac=\"{WD}\" "
                      f"| join type=left mac [{ARP_IPS}] | eval ip=mvindex(ips, 0) | lookup dnslookup clientip AS ip OUTPUT clienthost AS dns_name "
                      "| eval iface=coalesce(ifname, port) "
                      "| join type=left ik [| `mdt_if_status(*, $site$)` | eval ik=lower(node).\"|\".`mdt_ifkey(interface)` | dedup ik | fields ik oper_up speed] "
                      "| join type=left node iface [| `mdt_poe_port(*)` | rename interface as iface | fields node iface poe_w] "
                      "| sort 0 - t | fields node port iface vlan tf t ips dns_name oper_up speed poe_w"),
    "ds_wired_flow": FLOW_PORT,
    "ds_wired_logs": LOGS_PORT,
}
wired_chains = {  # name: (base, post-process); one row for the tiles (head 1 = current sighting)
    "ds_wired_name": ("ds_wired_seen", "| head 1 | eval Name=coalesce(dns_name, \"-\") | fields Name"),
    "ds_wired_ip": ("ds_wired_seen", "| head 1 | eval \"IP address(es)\"=coalesce(mvjoin(ips, \", \"), \"-\") | fields \"IP address(es)\""),
    "ds_wired_switch": ("ds_wired_seen", "| head 1 | eval Switch=node | fields Switch"),
    "ds_wired_port": ("ds_wired_seen", f"| head 1 | eval Port={short('iface')} | fields Port"),
    "ds_wired_vlan": ("ds_wired_seen", "| head 1 | eval VLAN=coalesce(vlan, \"-\") | fields VLAN"),
    "ds_wired_last": ("ds_wired_seen", "| head 1 | eval \"Last seen\"=strftime(t, \"%Y-%m-%d %H:%M\") | fields \"Last seen\""),
    # "up · 1 Gb/s" (speed left out when no source reports it).
    "ds_wired_status": ("ds_wired_seen", "| head 1 | eval Status=case(isnull(oper_up), \"-\", oper_up==1, \"up\", true(), \"down\"), "
                        "Speed=case(speed >= 1000000000, round(speed / 1000000000, 1).\" Gb/s\", speed > 0, round(speed / 1000000, 0).\" Mb/s\") "
                        "| eval \"Port status\"=Status.coalesce(\" · \".Speed, \"\") | fields \"Port status\""),
    "ds_wired_poe": ("ds_wired_seen", "| head 1 | eval PoE=if(isnull(poe_w), \"-\", tostring(round(poe_w, 1))) | fields PoE"),
    # Same columns as the Wireless tab's roam table: where the client was, first and last seen over the range.
    "ds_wired_table": ("ds_wired_seen", f"| eval Switch=node, Port={short('iface')}, VLAN=coalesce(vlan, \"-\"), "
                       "\"First seen\"=strftime(tf, \"%Y-%m-%d %H:%M\"), \"Last seen\"=strftime(t, \"%Y-%m-%d %H:%M\") "
                       "| eval _iface=iface | table Switch Port VLAN \"First seen\" \"Last seen\" _iface"),
    "ds_wired_throughput": ("ds_wired_flow", "| eval \"In (Mb/s)\"=round(in_bps / 1000000, 2), \"Out (Mb/s)\"=round(out_bps / 1000000, 2) "
                            "| table _time \"In (Mb/s)\" \"Out (Mb/s)\""),
    # As Interface Details: oversize is capped at the input errors the other kinds leave, transmit at the output errors.
    "ds_wired_errors": ("ds_wired_flow", "| eval ie=coalesce(in_err, 0), oe=coalesce(out_err, 0), CRC=coalesce(crc, 0), Undersize=coalesce(un_rx, 0), "
                        "Fragment=coalesce(frag_rx, 0), Jabber=coalesce(jab_rx, 0) "
                        "| eval Oversize=min(coalesce(ov_rx, 0), max(0, ie - CRC - Undersize - Fragment - Jabber)), Transmit=min(coalesce(tx_err, 0), oe) "
                        "| eval Other=max(0, ie + oe - CRC - Oversize - Undersize - Fragment - Jabber - Transmit) "
                        "| table _time CRC Oversize Undersize Fragment Jabber Transmit Other"),
}
bases.update(wired_bases)
chains.update(wired_chains)

dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q, **({"queryParameters": WINDOW[k]} if k in WINDOW else {})}}
               for k, q in bases.items()}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})
# Smart source for the wired tab: its tokens ($wired_seen:result.node$) read the newest sighting, the first row.
dataSources["ds_wired_seen"]["options"]["enableSmartSources"] = True

# Clickable tiles are link blue, like the links in tables.
LINK = "#4ea6e8"

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
    "viz_roam_timeline": {"type": "mdt_infra_monitoring.roam_timeline", "title": "Roaming timeline",
                          "dataSources": {"primary": "ds_roam_timeline"}, "options": {}},
    "viz_roam": chart("splunk.table", "APs the client was on (a gap over 5 minutes starts a new row)", "ds_roam_table", count=20),
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
    "input_client": {"type": "input.dropdown", "title": "Client", "dataSources": {"primary": "ds_clients"},
                     "options": {"token": "tk_client", "selectFirstSearchResult": True, "items": ">frame(label, value) | objects()"},
                     "context": {"label": ">primary | seriesByName(\"label\") | renameSeries(\"label\")",
                                 "value": ">primary | seriesByName(\"mac\") | renameSeries(\"value\")"}},
}

tiles = ["viz_name", "viz_ip", "viz_ssid", "viz_ap", "viz_radio", "viz_rssi_now", "viz_snr_now", "viz_speed_now"]
TW = [220, 160, 160, 180, 260, 150, 150, 160]  # widths add up to 1440
rows = [(t, sum(TW[:i]), 0, w, 110) for i, (t, w) in enumerate(zip(tiles, TW))] + [  # (item, x, y, w, h)
    ("viz_roam_timeline", 0, 110, 1440, 160),
    ("viz_rssi", 0, 270, 720, 280), ("viz_snr", 720, 270, 720, 280),
    ("viz_speed", 0, 550, 720, 280), ("viz_retries", 720, 550, 720, 280),
    ("viz_throughput", 0, 830, 1440, 280),
    ("viz_roam", 0, 1110, 1440, 300),
]
# ---- Wired tab: tiles, table, port charts and syslog (layout_2) ----
def place(item, x, y, w, h):  # in-canvas inputs are structure items of type "input" (the Splunk examples place them the same way)
    return {"item": item, "type": "input" if item.startswith("input_") else "block", "position": {"x": x, "y": y, "w": w, "h": h}}

inputs["input_wired"] = {"type": "input.dropdown", "title": "Wired client", "dataSources": {"primary": "ds_wired_clients"},
                         "options": {"token": "tk_wired", "selectFirstSearchResult": True, "items": ">frame(label, value) | objects()"},
                         "context": {"label": ">primary | seriesByName(\"label\") | renameSeries(\"label\")",
                                     "value": ">primary | seriesByName(\"value\") | renameSeries(\"value\")"}}

viz.update({
    "viz_wired_name": tile("Name", "ds_wired_name", "Name"),
    "viz_wired_ip": tile("IP address(es)", "ds_wired_ip", "IP address(es)"),
    # Click: Switch Details for the switch.
    "viz_wired_switch": {**tile("Switch", "ds_wired_switch", "Switch", majorColor=LINK), "eventHandlers": [{"type": "drilldown.customUrl", "options": {
                         "url": "/app/mdt_infra_monitoring/switch_details?form.tk_node=$wired_seen:result.node$"
                                "&form.global_time.earliest=$global_time.earliest$&form.global_time.latest=$global_time.latest$&form.site=$site$",
                         "newTab": False}}]},
    # Click: Interface Details for the port (full telemetry name, this site and time range). Only values as tokens.
    "viz_wired_port": {**tile("Port", "ds_wired_port", "Port", majorColor=LINK), "eventHandlers": [{"type": "drilldown.customUrl", "options": {
                       "url": "/app/mdt_infra_monitoring/interface_details?form.tk_node=$wired_seen:result.node$&form.tk_interface=$wired_seen:result.iface$"
                              "&form.global_time.earliest=$global_time.earliest$&form.global_time.latest=$global_time.latest$&form.site=$site$",
                       "newTab": False}}]},
    "viz_wired_vlan": tile("VLAN", "ds_wired_vlan", "VLAN"),
    "viz_wired_last": tile("Last seen", "ds_wired_last", "Last seen"),
    "viz_wired_status": tile("Port status", "ds_wired_status", "Port status"),
    "viz_wired_poe": tile("PoE draw (W)", "ds_wired_poe", "PoE"),
    # One link per table (Studio has no per-column drilldown): a row opens Interface Details for its switch and port.
    "viz_wired_table": {**chart("splunk.table", "Where this client was seen (client ports, newest first). Click a row for its port", "ds_wired_table",
                                count=50, showInternalFields=False), "eventHandlers": [{"type": "drilldown.customUrl", "options": {
                        "url": "/app/mdt_infra_monitoring/interface_details?form.tk_node=$row.Switch.value$&form.tk_interface=$row._iface.value$"
                               "&form.global_time.earliest=$global_time.earliest$&form.global_time.latest=$global_time.latest$&form.site=$site$",
                        "newTab": False}}]},
    "viz_wired_throughput": chart("splunk.line", "Port throughput (5 min average)", "ds_wired_throughput", legendDisplay="bottom"),
    "viz_wired_errors": chart("splunk.column", "Port errors per 5 min by kind", "ds_wired_errors", stackMode="stacked", legendDisplay="bottom"),
    # Hidden when empty (most ports have no syslog) instead of a no-results warning.
    "viz_wired_logs": {**chart("splunk.table", "Syslog for this port, newest first", "ds_wired_logs", count=50), "containerOptions": {"visibility": {"hideWhenNoData": True}}},
})

# Wireless tab: its two inputs sit in a row at the top of the canvas, the tiles and charts move down below them.
rows = [(i, x, y + 90, w, h) for i, x, y, w, h in rows]
wired_tiles = ["viz_wired_name", "viz_wired_ip", "viz_wired_switch", "viz_wired_port", "viz_wired_vlan", "viz_wired_last", "viz_wired_status", "viz_wired_poe"]
WTW = [200, 280, 160, 160, 100, 180, 200, 160]  # widths add up to 1440
wired_rows = [("input_wired", 0, 0, 720, 90)] + [(t, sum(WTW[:i]), 90, w, 110) for i, (t, w) in enumerate(zip(wired_tiles, WTW))] + [
    ("viz_wired_table", 0, 200, 1440, 200),
    ("viz_wired_throughput", 0, 400, 720, 280), ("viz_wired_errors", 720, 400, 720, 280),
    ("viz_wired_logs", 0, 680, 1440, 300),
]
layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_site"],
    "layoutDefinitions": {
        "layout_1": {"type": "grid", "options": {"width": 1440, "height": 1660},
                     "structure": [place("input_wlc", 0, 0, 360, 90), place("input_client", 360, 0, 1080, 90)]
                                  + [place(i, x, y, w, h) for i, x, y, w, h in rows]},
        "layout_2": {"type": "grid", "options": {"width": 1440, "height": 980},
                     "structure": [place(i, x, y, w, h) for i, x, y, w, h in wired_rows]}},
    "tabs": {"items": [{"label": "Wireless", "layoutId": "layout_1"}, {"label": "Wired", "layoutId": "layout_2"}]},
}

definition = {
    "title": "Client Details",
    "description": "One client, wireless or wired. Wireless: name, IP, SSID, AP and radio, RSSI, SNR, speed, retry % and throughput over time, and the APs it was on. Wired: the client's port, its status and PoE, port traffic and errors, and syslog for the port.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Client Details</label>\n'
       '    <description>One client, wireless or wired: identity, AP or switch port, RSSI or port traffic, roaming or port errors, syslog</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
