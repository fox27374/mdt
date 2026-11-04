# Wired clients, shared by the Client Search and Client Details generators (both import this: sys.path[0] is this folder).
# Edit this file, then run the generators.

# Wired MAC table entries (IOS-XE dial-in and dial-out, NX-OS), the latest per switch, port, VLAN and MAC. Body of an append
# (Client Search) or a top-level search (Client Details). t: latest sighting in the range, tf: earliest.
# The CDP join marks ports with a neighbour (is_cdp=1). Ports are keyed like mdt_ifkey names them, so both sides match.
WIRED_BODY = (
    "| mstats latest_time(_value) as t earliest_time(_value) as tf WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_xe_mac_info_port BY site extracted_source port matm_mac_entry_mac matm_mac_entry_vlan_id_number "
    "| rename extracted_source as node, matm_mac_entry_mac as mac, matm_mac_entry_vlan_id_number as vlan "
    "| append [| mstats latest_time(_value) as t earliest_time(_value) as tf WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_nx_mac_info_age BY site extracted_source port vlan mac type "
    "| rename extracted_source as node | where type!=\"gateway\" | eval vlan=replace(vlan, \"^vlan-\", \"\")] "
    # Dial-out has no VLAN (the yang_grpc receiver drops numeric keys, otel.yaml): the port's, from mdt_port_vlan.
    "| append [| mstats latest_time(_value) as t earliest_time(_value) as tf WHERE `mdt_metrics_index` site=\"$site$\" metric_name=cisco.port_info BY site extracted_source port mac "
    "| rename extracted_source as node] "
    # FHRP virtual MACs (HSRP v1/v2, VRRP) are gateways, not clients.
    "| eval mac=lower(mac) | where NOT match(mac, \"^(00:00:0c:07:ac|00:00:0c:9f:f|00:00:5e:00:01)\") | where NOT match(port, \"(?i)^(sup|cpu|vl|lo|nve|tu|app|mgmt|drop)\") "
    "| eval ik=lower(node).\"|\".`mdt_ifkey(port)` "
    "| join type=left ik [| `mdt_cdp(*, $site$)` | eval ik=lower(node).\"|\".`mdt_ifkey(interface)`, is_cdp=1 | dedup ik | fields ik is_cdp] "
    # MAC tables name ports short (Gi1/0/9); the Interface Details drilldown needs the telemetry name (GigabitEthernet1/0/9).
    "| join type=left ik [| `mdt_if_status(*, $site$)` | eval ik=lower(node).\"|\".`mdt_ifkey(interface)` | dedup ik | rename interface as ifname | fields ik ifname] "
    "| join type=left ik [| `mdt_port_vlan(*)` | eval ik=lower(node).\"|\".ik | fields ik port_vlan] | eval vlan=coalesce(vlan, port_vlan) "
    "| eval prio=if(is_cdp=1, 2, 1), type=\"Wired\""
)

# ARP: (address, MAC) pairs of the wired clients (XE without the switch's own interface entries, NX-OS) and the WLC's
# client IPs; one row per MAC with all its IPs (ips). Names of the labels come from gnmic (arp_oper_address, hardware).
ARP_IPS = (
    "| mstats latest_time(_value) as ta WHERE `mdt_metrics_index` metric_name=mdt_xe_arp_info_hardware BY extracted_source arp_oper_address arp_vrf_vrf hardware "
    "| join type=left extracted_source arp_oper_address arp_vrf_vrf [| mstats latest_time(_value) as tm WHERE `mdt_metrics_index` metric_name=mdt_xe_arp_info_mode "
    "BY extracted_source arp_oper_address arp_vrf_vrf mode | where mode=\"ios-arp-mode-interface\" | eval own=1 | fields extracted_source arp_oper_address arp_vrf_vrf own] "
    "| where isnull(own) | fields arp_oper_address hardware "
    "| append [| mstats latest_time(_value) as tn WHERE `mdt_metrics_index` metric_name=mdt_nx_arp_info_hardware BY extracted_source arp_oper_address hardware "
    "| fields arp_oper_address hardware] "
    "| append [| mstats latest_time(_value) as tw WHERE `mdt_metrics_index` metric_name=mdt_wl_info_ip_addr BY sisf_db_mac_mac_addr ip_addr "
    "| where ip_addr!=\"0.0.0.0\" | rename ip_addr as arp_oper_address, sisf_db_mac_mac_addr as hardware | fields arp_oper_address hardware] "
    "| eval mac=lower(hardware), ip=arp_oper_address | stats values(ip) as ips by mac"
)
