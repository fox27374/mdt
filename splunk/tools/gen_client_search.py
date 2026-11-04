# Generates the Client Search dashboard (Dashboard Studio JSON in views/client_search.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_client_search.py  then scripts/splunk-deploy
import json, os, sys
from client_sources import WIRED_BODY, ARP_IPS

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "client_search.xml")

# One row per client MAC. Wireless clients (WLC telemetry) come first; wired MACs come from the MAC tables of IOS-XE
# (mdt_xe_mac_info_port, dial-in; cisco.port_info, dial-out) and NX-OS (mdt_nx_mac_info_age). A MAC on a port with a
# CDP neighbour (uplink, AP, phone) is a fallback row; a MAC seen only there still shows once. A wireless client that is
# also on a wired port shows as wireless only. IPs come from ARP (own switch addresses dropped) and from the WLC.
Q = "$q$"

# Wireless clients: present in the range (rssi samples), latest WLC, hostname, SSID and AP (Ethernet MAC -> name).
WIRELESS = (
    "| mstats latest_time(_value) as t WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_wl_client_stats_most_recent_rssi BY site extracted_source traffic_stats_ms_mac_address "
    "| rename extracted_source as wlc, traffic_stats_ms_mac_address as mac | eval mac=lower(mac), prio=0, type=\"Wireless\" "
    "| sort 0 - t | dedup mac "
    # Latest hostname per client (a client can rename itself); the WLC's name for it is the Name, reverse DNS when empty.
    "| join type=left mac [| mstats latest_time(_value) as th WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_wl_info_device_hostname BY client_wsa_info_client_mac device_hostname "
    "| rename client_wsa_info_client_mac as mac, device_hostname as wl_name | eval mac=lower(mac) | sort 0 - th | dedup mac | fields mac wl_name] "
    "| join type=left mac [| mstats latest_time(_value) as ts WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_wl_info_vap_ssid BY vap_ssid dot11_oper_data_ms_mac_address "
    "| rename dot11_oper_data_ms_mac_address as mac, vap_ssid as ssid | eval mac=lower(mac) | sort 0 - ts | dedup mac | fields mac ssid] "
    "| join type=left mac [| mstats latest_time(_value) as ta WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_wl_client_stats_ap_mac_address BY dot11_oper_data_ms_mac_address ap_mac_address "
    "| rename dot11_oper_data_ms_mac_address as mac, ap_mac_address as eth_mac | eval mac=lower(mac), eth_mac=lower(eth_mac) | sort 0 - ta | dedup mac | fields mac eth_mac] "
    "| join type=left eth_mac [| mstats latest(_value) as x WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_wl_info_eth_mac BY eth_mac ap_name_mac_map_wtp_name "
    "| rename ap_name_mac_map_wtp_name as ap_name | eval eth_mac=lower(eth_mac) | dedup eth_mac | fields eth_mac ap_name]"
)

# Wired MAC table entries and ARP IPs: shared with Client Details (client_sources.py).
WIRED = "| append [" + WIRED_BODY + "]"

# Filter: MAC (any format, compared without separators), IP and name as case-insensitive substrings. A query that looks like
# an IPv4 address or a partial one is never read as a MAC. * is dropped: the input defaults to * (an empty text input leaves
# its token unset and the table would not run). Name = WLC hostname, else reverse DNS of the first IP.
FILTER = (
    "| eval ip=mvindex(ips, 0) "
    "| lookup dnslookup clientip AS ip OUTPUT clienthost AS dns_name "
    "| eval Name=coalesce(wl_name, dns_name, \"-\") "
    "| eval q=lower(trim(replace(\"" + Q + "\", \"\\*\", \"\"))), qh=replace(q, \"[^0-9a-f]\", \"\") "
    "| eval mac_q=if(len(qh) >= 2 AND NOT match(q, \"^[0-9]{1,3}(\\.[0-9]{1,3}){1,3}\\.?$\") AND match(q, \"^[0-9a-f:.-]+$\"), 1, 0) "
    "| eval hit_mac=if(mac_q=1 AND like(replace(mac, \"[^0-9a-f]\", \"\"), \"%\".qh.\"%\"), 1, 0) "
    "| eval hit_ip=if(like(lower(mvjoin(ips, \" \")), \"%\".q.\"%\"), 1, 0) "
    "| eval hit_name=if(like(lower(Name), \"%\".q.\"%\"), 1, 0) "
    "| where q=\"\" OR hit_mac=1 OR hit_ip=1 OR hit_name=1"
)

# Rows: the table columns, plus the hidden drilldown parts.
ROWS = (
    "| eval IP=ips, MAC=mac, Type=type, "
    "Where=if(type=\"Wireless\", coalesce(wlc, \"-\").\" · \".coalesce(ap_name, eth_mac, \"-\").\" · \".coalesce(ssid, \"-\"), "
    "coalesce(node, \"-\").\" · \".coalesce(port, \"-\").\" · VLAN \".coalesce(vlan, \"-\")), "
    "\"Last seen\"=strftime(t, \"%Y-%m-%d %H:%M\"), "
    # Drilldown parts (hidden: leading _). Studio URL-encodes a token, so the URL template holds the path and each part fills one slot.
    # Port-channels have no Interface Details (drop-if-stats-interfaces drops their stats): those open Switch Details.
    # Client ports (wired, no CDP neighbour) and wireless clients open Client Details: its Wired tab (layout_2) or Wireless tab (layout_1).
    "_view=case(type=\"Wireless\", \"client_details\", match(port, \"(?i)^po\"), \"switch_details\", is_cdp=1, \"interface_details\", true(), \"client_details\"), "
    "_tab=case(type=\"Wireless\", \"layout_1\", _view=\"client_details\", \"layout_2\", true(), \"layout_1\"), "
    "_wlc=coalesce(wlc, \"-\"), _node=coalesce(node, \"-\"), _port=coalesce(ifname, port, \"-\"), _site=coalesce(site, \"-\") "
    "| sort 0 - t "
    "| table Type MAC IP Name Where \"Last seen\" _view _tab _wlc _node _port _site"
)

SEARCH = (WIRELESS + " " + WIRED + " | sort 0 mac prio - t | dedup mac "
          "| join type=left mac [" + ARP_IPS + "] " + FILTER + " " + ROWS)

dataSources = {
    "ds_sites": {"type": "ds.search", "name": "sites", "options": {"query": "| mcatalog values(site) as site WHERE `mdt_metrics_index` | mvexpand site | rename site as label | eval value=label | append [| makeresults | eval label=\"All sites\", value=\"*\"] | fields label value"}},
    "ds_clients": {"type": "ds.search", "name": "clients", "options": {"query": SEARCH}}}

viz = {
    "viz_clients": {"type": "splunk.table", "title": "Clients: wired and wireless, latest sighting in range. Click a row to open its client (wired on a client port, or wireless), its switch port (uplink), or its port-channel's switch",
                    "dataSources": {"primary": "ds_clients"},
                    "options": {"count": 100, "showInternalFields": False},
                    "eventHandlers": [{"type": "drilldown.customUrl", "options": {
                        "url": "/app/mdt_infra_monitoring/$row._view.value$?tab=$row._tab.value$&form.wlc=$row._wlc.value$&form.tk_client=$row.MAC.value$&form.tk_wired=$row.MAC.value$&form.tk_node=$row._node.value$&form.tk_interface=$row._port.value$&form.global_time.earliest=$global_time.earliest$&form.global_time.latest=$global_time.latest$&form.site=$row._site.value$",
                        "newTab": False}}],
                    "showProgressBar": True},
}

inputs = {
    "input_site": {"type": "input.dropdown", "title": "Site", "dataSources": {"primary": "ds_sites"},
                   "options": {"token": "site", "defaultValue": "ibk-lab", "items": ">frame(label, value) | objects()"},
                   "context": {"label": ">primary | seriesByName(\"label\") | renameSeries(\"label\")",
                               "value": ">primary | seriesByName(\"value\") | renameSeries(\"value\")"}},
    "input_time": {"type": "input.timerange", "title": "Time range",
                   "options": {"token": "global_time", "defaultValue": "-24h@h,now"}},
    "input_q": {"type": "input.text", "title": "Search: MAC (any format), IP or name (* = all)",
                "options": {"token": "q", "defaultValue": "*"}},
}

layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_site", "input_q"],
    "layoutDefinitions": {"layout_1": {"type": "grid", "options": {"width": 1440, "height": 700},
        "structure": [{"item": "viz_clients", "type": "block", "position": {"x": 0, "y": 0, "w": 1440, "h": 700}}]}},
    "tabs": {"items": [{"label": "Clients", "layoutId": "layout_1"}]},
}

definition = {
    "title": "Client Search",
    "description": "Find a client by MAC (any format), IP or name: wired and wireless, where it was last seen.",
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Client Search</label>\n'
       '    <description>Find a client by MAC, IP or name: where it is connected, as wired or wireless</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
