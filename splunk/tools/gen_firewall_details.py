# Generates the Firewall Details dashboard (Dashboard Studio JSON in views/firewall_details.xml).
# Edit this script, not the XML:  python3 splunk/tools/gen_firewall_details.py  then scripts/splunk-deploy
# Data: gnmic PAN-OS subscriptions. Interfaces: panos_if_stats (30s counters per interface), panos_if_info (300s link state,
# negotiated speed, duplex, auto-negotiation). PAN-OS XML API over gNMI (panos_xml_*, parsed by the panos-xmlapi processor in mdt.yaml):
# session (60s), dp (60s), ha (60s), counters (300s), env (300s), system and license (3600s).
import json, os, sys

OUT = os.path.join(sys.path[0], "..", "mdt_infra_monitoring", "default", "data", "ui", "views", "firewall_details.xml")

IDX = '`mdt_metrics_index` extracted_source="$tk_fw$"'
GREEN, AMBER, RED = "#65A637", "#F8BE34", "#D93F3C"  # threshold colours (tiles)
DAY = 86400

# Interface counters per minute in the mdt_if_counters shape, so mdt_if_rates turns them into bit/s and errors per sample.
# Then 5-minute averages per interface; the open bucket is dropped so the last point is not a partial one.
FLOW = ("| mstats latest(mdt_panos_if_stats_in_octets) as in_octets latest(mdt_panos_if_stats_out_octets) as out_octets "
        "latest(mdt_panos_if_stats_in_errors) as in_errors latest(mdt_panos_if_stats_out_errors) as out_errors "
        "WHERE `mdt_metrics_index` extracted_source=\"$tk_fw$\" span=1m BY extracted_source interface_name "
        "| eval node=extracted_source, interface=interface_name | fields - extracted_source interface_name "
        "| `mdt_if_rates` | bin _time span=5m "
        "| stats avg(in_bps) as in_bps avg(out_bps) as out_bps sum(in_errs) as in_errs sum(out_errs) as out_errs by _time interface "
        "| where _time + 300 <= now()")

# Metric names: mdt_<subscription>_<value>. Label-valued (string) leaves are value-1 series with the string as a label
# of the same name (state="active"); a series exists only while its value is current (the gnmic output expires it).
COMPAT = [("vpnclient", "VPN client"), ("app", "App"), ("threat", "Threat"), ("av", "Antivirus"), ("url", "URL filtering"),
          ("gpclient", "GlobalProtect client"), ("build", "Build"), ("iot", "IoT"), ("dlp", "DLP"), ("oc", "OpenConfig")]
SIGS = [("app", "App"), ("threat", "Threat"), ("av", "Antivirus"), ("url", "URL filtering"), ("wildfire", "WildFire")]
VERSIONS = [("sw", "Software"), ("app", "App"), ("threat", "Threat"), ("av", "Antivirus"), ("wildfire", "WildFire"), ("url", "URL filtering")]

bases = {
    "ds_sites": "| mcatalog values(site) as site WHERE `mdt_metrics_index` | mvexpand site | rename site as label | eval value=label",
    "ds_fws": "| mstats count(_value) WHERE `mdt_metrics_index` site=\"$site$\" metric_name=mdt_panos_* BY extracted_source "
              "| rename extracted_source as node | fields node | sort node",
    "ds_flow": FLOW,
    # One row per front-panel port (ethernet<x>/<y>) for the port_faceplate viz: link state (panos_if_info, 300s: latest
    # label within 15 min), negotiated speed in bit/s, and errors over the time range. Fields the firewall does not
    # report are empty or 0 so the tooltip does not break.
    "ds_fw_ports": ("| mstats latest_time(_value) as t WHERE " + IDX + " metric_name=mdt_panos_if_info_oper_status earliest=-15m "
                    "BY interface_name oper_status | sort 0 - t | dedup interface_name | fields interface_name oper_status "
                    "| append [| mstats latest_time(_value) as t WHERE " + IDX + " metric_name=mdt_panos_if_info_admin_status earliest=-15m "
                    "BY interface_name admin_status | sort 0 - t | dedup interface_name | fields interface_name admin_status] "
                    "| append [| mstats latest_time(_value) as t WHERE " + IDX + " metric_name=mdt_panos_if_info_negotiated_port_speed earliest=-15m "
                    "BY interface_name negotiated_port_speed | sort 0 - t | dedup interface_name | fields interface_name negotiated_port_speed] "
                    "| stats values(oper_status) as oper_status values(admin_status) as admin_status values(negotiated_port_speed) as speed "
                    "by interface_name | where match(interface_name, \"^ethernet\\d+/\\d+$\") "
                    "| rename interface_name as interface "
                    "| join type=left interface [" + FLOW + " | stats sum(in_errs) as in_errs sum(out_errs) as out_errs by interface] "
                    "| rex field=speed \"SPEED_(?<n>\\d+)(?<unit>[GM])B\" "
                    "| eval speed=if(isnull(n), null(), n * if(unit==\"G\", 1000000000, 1000000)), "
                    "state=case(lower(admin_status)==\"down\", \"admin down\", lower(oper_status)==\"up\", \"up\", true(), \"down\"), "
                    "neighbour=\"\", macs=0, mac_list=\"\", poe_w=\"\", poe_state=\"\", pd_class=\"\", port_channel=\"\" "
                    # Model from panos_xml_system (60 min+ series): joined on a constant key, one value for the firewall.
                    "| eval k=1 | join type=left k [| mstats latest(_value) as v WHERE " + IDX + " metric_name=mdt_panos_xml_system_model extracted_source=\"$tk_fw$\" "
                    "earliest=-2d BY model | head 1 | eval k=1 | fields k model] | fillnull value=\"\" model "
                    "| fillnull value=0 in_errs out_errs "
                    "| fields interface state speed in_errs out_errs neighbour macs mac_list poe_w poe_state pd_class port_channel model"),
    # Session counters (panos_xml_session, 60s) and the 5-minute buckets the session charts use.
    "ds_sessions": "| mstats latest(mdt_panos_xml_session_num_active) as active latest(mdt_panos_xml_session_num_max) as max "
                   "WHERE " + IDX + " span=5m",
    "ds_sess_proto": "| mstats latest(mdt_panos_xml_session_num_tcp) as tcp latest(mdt_panos_xml_session_num_udp) as udp "
                     "latest(mdt_panos_xml_session_num_icmp) as icmp WHERE " + IDX + " span=5m",
    "ds_sess_rate": "| mstats latest(mdt_panos_xml_session_cps) as cps latest(mdt_panos_xml_session_kbps) as kbps "
                    "latest(mdt_panos_xml_session_pps) as pps WHERE " + IDX + " span=5m",
    "ds_installed": "| mstats latest(mdt_panos_xml_session_num_installed) as inst WHERE " + IDX + " span=5m",
    # Dataplane (panos_xml_dp, 60s): minute window, one value per 5 minutes.
    "ds_dp": "| mstats latest(mdt_panos_xml_dp_cpu_avg) as cpu_avg latest(mdt_panos_xml_dp_cpu_max) as cpu_max WHERE " + IDX + " span=5m",
    "ds_dp_res": "| mstats latest(mdt_panos_xml_dp_session_avg) as session_avg latest(mdt_panos_xml_dp_session_max) as session_max "
                 "latest(mdt_panos_xml_dp_packet_buffer_avg) as packet_buffer_avg latest(mdt_panos_xml_dp_packet_buffer_max) as packet_buffer_max "
                 "latest(mdt_panos_xml_dp_packet_descriptor_avg) as packet_descriptor_avg "
                 "latest(mdt_panos_xml_dp_packet_descriptor_max) as packet_descriptor_max WHERE " + IDX + " span=5m",
    # Counters (panos_xml_counters, 300s): drop and error counters, cumulative since boot.
    "ds_drops": "| mstats latest(_value) as v WHERE " + IDX + " metric_name=mdt_panos_xml_counters_value span=5m BY counter",
    "ds_drop_table": "| mstats earliest(_value) as first latest(_value) as total WHERE " + IDX + " metric_name=mdt_panos_xml_counters_value "
                     "BY counter desc | eval change=total-first | sort 0 -change "
                     "| rename counter as Counter, desc as Description, change as \"Change in range\", total as \"Total since boot\" "
                     "| table Counter Description \"Change in range\" \"Total since boot\"",
    # HA role: state of the local unit (newest bucket).
    "ds_ha_role": "| mstats latest(_value) as v WHERE " + IDX + " metric_name=mdt_panos_xml_ha_state span=1m BY unit state "
                  "| sort 0 -_time | dedup unit | where unit=\"local\" | eval \"HA role\"=state | fields \"HA role\"",
    "ds_alarms": "| mstats latest(_value) as alarms WHERE " + IDX + " metric_name=mdt_panos_xml_env_alarms earliest=-15m "
                 "| rename alarms as \"Sensors in alarm\" | fields \"Sensors in alarm\"",
    "ds_temps": "| mstats latest(_value) as Reading WHERE " + IDX + " metric_name=mdt_panos_xml_env_temp_c earliest=-15m BY sensor "
                "| rename sensor as Sensor | sort Sensor | table Sensor Reading",
    "ds_fans": "| mstats latest(_value) as RPM WHERE " + IDX + " metric_name=mdt_panos_xml_env_rpm earliest=-15m BY sensor "
               "| rename sensor as Fan | sort Fan | table Fan RPM",
    "ds_psu": "| mstats latest(_value) as v WHERE " + IDX + " metric_name=mdt_panos_xml_env_status earliest=-15m BY sensor status "
              "| rename sensor as \"Power supply\" | table \"Power supply\" status",
    "ds_lic": "| mstats latest(_value) as exp WHERE " + IDX + " metric_name=mdt_panos_xml_license_expires earliest=-2d BY feature "
              "| eval Expires=strftime(exp, \"%Y-%m-%d\"), days_left=round((exp - now()) / " + str(DAY) + ", 0) "
              "| sort days_left | rename feature as Feature, days_left as \"Days left\" | table Feature Expires \"Days left\"",
}


def ha_row(metric, label, title, span=True):
    # Newest value per unit (label-valued leaf: the series that exists now).
    return ("| mstats latest(_value) as val WHERE " + IDX + " metric_name=mdt_panos_xml_ha_" + metric
            + (" span=1m" if span else " earliest=-6m") + " BY unit " + label
            + " | sort 0 -_time | dedup unit | eval Item=\"" + title + "\", val=" + label + " | fields unit Item val")


def ha_num_row(metric, title):
    return ("| mstats latest(_value) as val WHERE " + IDX + " metric_name=mdt_panos_xml_ha_" + metric + " earliest=-6m BY unit "
            "| eval Item=\"" + title + "\" | fields unit Item val")


ha_rows = [ha_row("state", "state", "State"), ha_num_row("priority", "Priority"), ha_num_row("state_duration", "Time in state (s)"),
           ha_row("serial", "serial", "Serial"), ha_row("build_rel", "build_rel", "Build"),
           ha_row("ha1_status", "ha1_status", "Link ha1"), ha_row("ha1_backup_status", "ha1_backup_status", "Link ha1-backup"),
           ha_row("ha2_status", "ha2_status", "Link ha2"), ha_row("conn_status", "conn_status", "Peer connection")]
ha_table = ha_rows[0] + "".join(" | append [" + r + "]" for r in ha_rows[1:])
ha_table += (" | chart values(val) as val over Item by unit "
             "| eval ord=case(Item=\"State\", 1, Item=\"Priority\", 2, Item=\"Time in state (s)\", 3, Item=\"Serial\", 4, Item=\"Build\", 5, "
             "Item=\"Link ha1\", 6, Item=\"Link ha1-backup\", 7, Item=\"Link ha2\", 8, Item=\"Peer connection\", 9) "
             "| sort 0 ord | fields - ord | rename local as Local, peer as Peer | table Item Local Peer")
bases["ds_ha_table"] = ha_table

# Sync and compatibility: group-level values, then one row per compat field that is not Match (only those have a series).
sync_rows = []
for metric, title in [("mode", "Mode"), ("running_sync", "Running sync"), ("state_sync", "State sync")]:
    sync_rows.append("| mstats latest(_value) as v WHERE " + IDX + " metric_name=mdt_panos_xml_ha_" + metric + " span=1m BY " + metric
                     + " | sort 0 -_time | head 1 | eval Item=\"" + title + "\", Value=" + metric + " | fields Item Value")
for f, title in COMPAT:
    sync_rows.append("| mstats latest(_value) as v WHERE " + IDX + " metric_name=mdt_panos_xml_ha_" + f + "_compat earliest=-6m BY "
                     + f + "_compat | eval Item=\"" + title + " compat\", Value=" + f + "_compat | fields Item Value")
bases["ds_ha_sync"] = sync_rows[0] + "".join(" | append [" + r + "]" for r in sync_rows[1:]) + " | table Item Value"

# Versions and signature ages (system, 3600s). URL release date comes from the processor (version prefix).
ver_rows = [("| mstats latest(_value) as v WHERE " + IDX + " metric_name=mdt_panos_xml_system_" + f + "_version earliest=-2d BY "
             + f + "_version | sort 0 -_time | head 1 | eval Item=\"" + name + "\", Version=" + f + "_version | fields Item Version")
            for f, name in VERSIONS]
ver_rows.append("| mstats latest(_value) as up WHERE " + IDX + " metric_name=mdt_panos_xml_system_uptime earliest=-2d "
                "| eval Item=\"Uptime (days)\", Version=round(up / " + str(DAY) + ", 1) | fields Item Version")
bases["ds_versions"] = ver_rows[0] + "".join(" | append [" + r + "]" for r in ver_rows[1:]) + " | table Item Version"

sig_rows = [("| mstats latest(_value) as rel WHERE " + IDX + " metric_name=mdt_panos_xml_system_" + f + "_release earliest=-2d "
             "| eval Signature=\"" + name + "\", Released=strftime(rel, \"%Y-%m-%d %H:%M\"), age=round((now() - rel) / " + str(DAY) + ", 1) "
             "| fields Signature Released age") for f, name in SIGS]
bases["ds_sigs"] = sig_rows[0] + "".join(" | append [" + r + "]" for r in sig_rows[1:]) + \
    " | rename age as \"Age (days)\" | table Signature Released \"Age (days)\""

# Health issues: one count per group (HA, Alarms, Licences, Signatures); a group counts 1 when any of its checks fires.
ha_checks = [("| mstats count(_value) as n WHERE " + IDX + " metric_name=mdt_panos_xml_ha_*_compat earliest=-6m", "exists"),
             ("| mstats count(_value) as n WHERE " + IDX + " metric_name=mdt_panos_xml_ha_running_sync running_sync!=\"synchronized\" earliest=-6m", "exists")]
ha_checks += [("| mstats count(_value) as n WHERE " + IDX + " metric_name=mdt_panos_xml_ha_" + m + " " + m + "!=\"up\" earliest=-6m", "exists")
              for m in ["ha1_status", "ha1_backup_status", "ha2_status", "conn_status"]]
checks = [("HA", q, t) for q, t in ha_checks]
checks.append(("Alarms", "| mstats latest(_value) as n WHERE " + IDX + " metric_name=mdt_panos_xml_env_alarms earliest=-15m | where n > 0", "rows"))
checks.append(("Licences", "| mstats latest(_value) as exp WHERE " + IDX + " metric_name=mdt_panos_xml_license_expires earliest=-2d BY feature "
               "| where exp < now() + 30 * " + str(DAY), "rows"))
for f, _ in SIGS:
    limit = DAY if f == "wildfire" else 7 * DAY  # threat/app/av: warn after 7 days, WildFire after 1 day
    checks.append(("Signatures", "| mstats latest(_value) as rel WHERE " + IDX + " metric_name=mdt_panos_xml_system_" + f
                   + "_release earliest=-2d | where rel < now() - " + str(limit), "rows"))
health = "| makeresults | eval grp=\"seed\", n=0 | fields grp n"
for grp, q, kind in checks:
    part = q + (" | eval n=if(n > 0, 1, 0), grp=\"" + grp + "\" | fields grp n" if kind == "exists"
                else " | stats count as n | eval grp=\"" + grp + "\"")
    health += " | append [" + part + "]"
bases["ds_health"] = health + " | stats max(n) as n by grp | stats sum(n) as \"Health issues\""

# Per-interface time series, only interfaces that carried traffic (or errors) in the range.
def per_if(value):
    return (f"| eval v={value} | eventstats max(v) as m by interface | where m > 0 "
            "| xyseries _time interface v | fillnull value=0")

chains = {  # name: (base, post-process)
    "ds_active": ("ds_sessions", "| timechart span=5m max(active) as \"Active sessions\""),  # timechart: empty buckets stay null, so gaps show
    "ds_util": ("ds_sessions", "| eval \"Session table %\"=round(active / max * 100, 2) | fields _time \"Session table %\""),
    "ds_proto": ("ds_sess_proto", "| timechart span=5m max(tcp) as TCP max(udp) as UDP max(icmp) as ICMP"),
    "ds_cps": ("ds_sess_rate", "| timechart span=5m max(cps) as \"Connections/s\""),
    "ds_kbps": ("ds_sess_rate", "| timechart span=5m max(kbps) as \"kbps\" max(pps) as \"pps\""),
    # Sessions installed since the previous bucket (num_installed grows by the sessions set up).
    "ds_new_sess": ("ds_installed", "| sort 0 _time | delta inst as d | where d >= 0 | eval \"New sessions per 5 min\"=d "
                                    "| fields _time \"New sessions per 5 min\""),
    "ds_cps_now": ("ds_sess_rate", "| sort 0 _time | tail 1 | eval \"Connections/s\"=cps | fields \"Connections/s\""),
    "ds_cpu_now": ("ds_dp", "| sort 0 _time | tail 1 | eval \"Dataplane CPU %\"=round(cpu_avg, 1) | fields \"Dataplane CPU %\""),
    "ds_cpu": ("ds_dp", "| timechart span=5m max(cpu_avg) as \"CPU avg %\" max(cpu_max) as \"CPU max %\""),
    "ds_dp_pb": ("ds_dp_res", "| timechart span=5m max(packet_buffer_avg) as \"Packet buffer avg %\" max(packet_buffer_max) as \"Packet buffer max %\" "
                              "max(packet_descriptor_avg) as \"Descriptor avg %\" max(packet_descriptor_max) as \"Descriptor max %\""),
    "ds_dp_sess": ("ds_dp_res", "| timechart span=5m max(session_avg) as \"Session avg %\" max(session_max) as \"Session max %\""),
    "ds_drop_chart": ("ds_drops", "| sort 0 counter _time | streamstats current=f window=1 last(v) as prev by counter "
                                  "| eval change=v - prev | where change >= 0 "
                                  "| timechart span=5m sum(change) by counter limit=10 useother=f"),
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
                            # Negotiated speed / duplex and MTU (panos_if_info, 300s): one value-1 series per leaf with the value as label; MTU a number.
                            # One mstats per leaf: mstats BY drops series that lack a BY dimension.
                            "| join type=left interface [| mstats latest(_value) WHERE `mdt_metrics_index` metric_name=mdt_panos_if_info_negotiated_port_speed extracted_source=\"$tk_fw$\" earliest=-15m BY interface_name negotiated_port_speed "
                            "| append [| mstats latest(_value) WHERE `mdt_metrics_index` metric_name=mdt_panos_if_info_negotiated_duplex_mode extracted_source=\"$tk_fw$\" earliest=-15m BY interface_name negotiated_duplex_mode] "
                            "| append [| mstats latest(_value) as a WHERE `mdt_metrics_index` metric_name=mdt_panos_if_info_auto_negotiate extracted_source=\"$tk_fw$\" earliest=-15m BY interface_name | eval auto=if(a==1, \"yes\", \"no\")] "
                            "| append [| mstats latest(_value) as mtu WHERE `mdt_metrics_index` metric_name=mdt_panos_if_info_mtu extracted_source=\"$tk_fw$\" earliest=-15m BY interface_name] "
                            "| stats values(negotiated_port_speed) as speed values(negotiated_duplex_mode) as duplex values(auto) as auto max(mtu) as mtu by interface_name "
                            "| eval speed=replace(replace(speed, \"^.*SPEED_(.*?)B?$\", \"\\1\"), \"UNKNOWN\", \"unknown\"), duplex=if(match(lower(duplex), \"^(full|half)$\"), lower(duplex), null()) | rename interface_name as interface] "
                            "| sort 0 - in_max "
                            "| rename interface as Interface, speed as Speed, duplex as Duplex, auto as \"Auto-neg\", mtu as MTU, in_now as \"In now (Mb/s)\", out_now as \"Out now (Mb/s)\", "
                            "in_avg as \"In avg (Mb/s)\", out_avg as \"Out avg (Mb/s)\", in_max as \"In peak (Mb/s)\", "
                            "out_max as \"Out peak (Mb/s)\", in_errs as \"Errors in\", out_errs as \"Errors out\" "
                            "| table Interface Speed Duplex \"Auto-neg\" MTU \"In now (Mb/s)\" \"Out now (Mb/s)\" \"In avg (Mb/s)\" \"Out avg (Mb/s)\" "
                            "\"In peak (Mb/s)\" \"Out peak (Mb/s)\" \"Errors in\" \"Errors out\""),
}

dataSources = {k: {"type": "ds.search", "name": k[3:], "options": {"query": q}} for k, q in bases.items()}
dataSources.update({k: {"type": "ds.chain", "name": k[3:], "options": {"extend": b, "query": q}} for k, (b, q) in chains.items()})


def tile(title, d, thresholds=None, **opts):
    if thresholds:  # (values, colours): colour per band, bands from the thresholds
        values, colours = thresholds
        opts = {**opts, "colorMode": "block", "rangeValues": values, "rangeColors": colours}
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": d},
            "options": {"majorColor": "#708794", **opts}}


def chart(kind, title, d, **opts):
    return {"type": kind, "title": title, "dataSources": {"primary": d}, "options": opts, "showProgressBar": True}


def table(title, d, **opts):
    return chart("splunk.table", title, d, count=opts.pop("count", 30), **opts)


viz = {
    # Top row, every tab.
    "viz_ha_role": tile("HA role (this unit)", "ds_ha_role"),
    "viz_active": tile("Active sessions", "ds_active"),
    "viz_util": tile("Session table used", "ds_util", ([80, 90], [GREEN, AMBER, RED]), unit="%", unitPosition="after"),
    "viz_cps": tile("Connections/s", "ds_cps_now"),
    "viz_cpu": tile("Dataplane CPU", "ds_cpu_now", ([70, 90], [GREEN, AMBER, RED]), unit="%", unitPosition="after"),
    "viz_health": tile("Health issues", "ds_health", ([1], [GREEN, RED])),
    # Traffic.
    "viz_ports": {"type": "mdt_infra_monitoring.port_faceplate", "title": "Ports", "dataSources": {"primary": "ds_fw_ports"}, "options": {}},
    "viz_in_total": tile("Total in (5 min average)", "ds_in_total", unit="Mb/s", unitPosition="after"),
    "viz_out_total": tile("Total out (5 min average)", "ds_out_total", unit="Mb/s", unitPosition="after"),
    "viz_err_ifs": tile("Interfaces with errors", "ds_err_ifs"),
    "viz_in": chart("splunk.line", "In by interface, Mb/s (5 min average)", "ds_in", legendDisplay="bottom"),
    "viz_out": chart("splunk.line", "Out by interface, Mb/s (5 min average)", "ds_out", legendDisplay="bottom"),
    "viz_sessions": chart("splunk.line", "Active sessions", "ds_active", legendDisplay="off", nullValueDisplay="gaps"),
    "viz_errs": {**chart("splunk.column", "Errors per 5 min by interface (in + out)", "ds_errs",
                         stackMode="stacked", legendDisplay="bottom"),
                 "containerOptions": {"visibility": {"hideWhenNoData": True}}},
    "viz_proto": chart("splunk.line", "Active sessions by protocol", "ds_proto", legendDisplay="bottom", nullValueDisplay="gaps"),
    "viz_new_sess": chart("splunk.column", "New sessions per 5 min", "ds_new_sess", legendDisplay="off"),
    "viz_cps_chart": chart("splunk.line", "Connections per second", "ds_cps", legendDisplay="off", nullValueDisplay="gaps"),
    "viz_kbps": chart("splunk.line", "Throughput (kbps) and packets per second", "ds_kbps", legendDisplay="bottom", nullValueDisplay="gaps"),
    "viz_table": table("Interfaces, whole time range", "ds_table", count=30),
    # Health.
    "viz_cpu_chart": chart("splunk.line", "Dataplane CPU %, average and max over cores (minute window)", "ds_cpu",
                           legendDisplay="bottom", nullValueDisplay="gaps"),
    "viz_dp_pb": chart("splunk.line", "Packet buffer and descriptor %", "ds_dp_pb", legendDisplay="bottom", nullValueDisplay="gaps"),
    "viz_dp_sess": chart("splunk.line", "Session table % (dataplane)", "ds_dp_sess", legendDisplay="bottom", nullValueDisplay="gaps"),
    "viz_ha_table": table("HA: local vs peer", "ds_ha_table", count=20),
    "viz_ha_sync": table("HA sync and compatibility (only mismatches are listed)", "ds_ha_sync", count=20),
    "viz_alarms": tile("Sensors in alarm", "ds_alarms", ([1], [GREEN, RED])),
    "viz_psu": table("Power supplies", "ds_psu", count=10),
    "viz_temps": table("Temperatures (C)", "ds_temps", count=20),
    "viz_fans": table("Fans (rpm)", "ds_fans", count=20),
    "viz_versions": table("Versions and uptime", "ds_versions", count=20),
    "viz_sigs": table("Signature ages (warn: threat, app, av over 7 days; WildFire over 1 day)", "ds_sigs", count=10),
    "viz_lic": table("Licences (days left; expired when below 0)", "ds_lic", count=30),
    # Drops.
    "viz_drop_chart": chart("splunk.column", "Top 10 drop and error counters, change per 5 min", "ds_drop_chart",
                            stackMode="stacked", legendDisplay="bottom"),
    "viz_drop_table": table("Drop and error counters, whole time range (total since boot)", "ds_drop_table", count=100),
}

inputs = {
    "input_site": {"type": "input.dropdown", "title": "Site", "dataSources": {"primary": "ds_sites"},
                   "options": {"token": "site", "defaultValue": "ibk-lab", "items": ">frame(label, value) | objects()"},
                   "context": {"label": ">primary | seriesByName(\"label\") | renameSeries(\"label\")",
                               "value": ">primary | seriesByName(\"value\") | renameSeries(\"value\")"}},
    "input_time": {"type": "input.timerange", "title": "Time range",
                   "options": {"token": "global_time", "defaultValue": "-4h@m,now"}},
    "input_fw": {"type": "input.dropdown", "title": "Firewall", "dataSources": {"primary": "ds_fws"},
                 "options": {"token": "tk_fw", "selectFirstSearchResult": True, "items": ">frame(label, value) | objects()"},
                 "context": {"label": ">primary | seriesByName(\"node\") | renameSeries(\"label\")",
                             "value": ">primary | seriesByName(\"node\") | renameSeries(\"value\")"}},
}

TOP = [("viz_ha_role", 0), ("viz_active", 240), ("viz_util", 480), ("viz_cps", 720), ("viz_cpu", 960), ("viz_health", 1200)]
# (item, x, y, w, h). Every tab starts with the top row.
tab_rows = {
    "layout_traffic": [
        ("viz_ports", 0, 110, 1440, 200),
        ("viz_in_total", 0, 320, 480, 110), ("viz_out_total", 480, 320, 480, 110), ("viz_err_ifs", 960, 320, 480, 110),
        ("viz_in", 0, 430, 720, 320), ("viz_out", 720, 430, 720, 320),
        ("viz_errs", 0, 750, 720, 300), ("viz_sessions", 720, 750, 720, 300),
        ("viz_proto", 0, 1050, 720, 300), ("viz_new_sess", 720, 1050, 720, 300),
        ("viz_cps_chart", 0, 1350, 720, 300), ("viz_kbps", 720, 1350, 720, 300),
        ("viz_table", 0, 1650, 1440, 420),
    ],
    "layout_health": [
        ("viz_cpu_chart", 0, 110, 720, 300), ("viz_dp_pb", 720, 110, 720, 300),
        ("viz_dp_sess", 0, 410, 720, 260), ("viz_ha_table", 720, 410, 720, 260),
        ("viz_ha_sync", 0, 670, 720, 260), ("viz_versions", 720, 670, 720, 260),
        ("viz_sigs", 0, 930, 720, 260), ("viz_lic", 720, 930, 720, 260),
    ],
    "layout_env": [
        ("viz_alarms", 0, 110, 1440, 110),
        ("viz_psu", 0, 220, 480, 300), ("viz_temps", 480, 220, 480, 300), ("viz_fans", 960, 220, 480, 300),
    ],
    "layout_drops": [
        ("viz_drop_chart", 0, 110, 1440, 380), ("viz_drop_table", 0, 490, 1440, 620),
    ],
}
tabs = [("Traffic", "layout_traffic"), ("Health", "layout_health"), ("Environment", "layout_env"), ("Drops", "layout_drops")]


def grid(rows):
    items = [(i, x, 0, 240, 110) for i, x in TOP] + rows
    return {"type": "grid", "options": {"width": 1440, "height": max(y + h for _, _, y, _, h in items)},
            "structure": [{"item": i, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}} for i, x, y, w, h in items]}


layout = {
    "type": "grid",
    "globalInputs": ["input_time", "input_site", "input_fw"],
    "layoutDefinitions": {k: grid(rows) for k, rows in tab_rows.items()},
    "tabs": {"items": [{"label": label, "layoutId": lid} for label, lid in tabs]},
}

DESCRIPTION = ("One Palo Alto firewall: sessions, dataplane health, HA, sensors, versions and licences (PAN-OS XML API over gNMI), "
               "throughput and errors per interface, and drop counters")
definition = {
    "title": "Firewall Details",
    "description": DESCRIPTION,
    "inputs": inputs,
    "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {
        "earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}, "refresh": "90s", "refreshType": "delay"}}}},
    "visualizations": viz,
    "dataSources": dataSources,
    "layout": layout,
    "applicationProperties": {},
}

xml = ('<dashboard version="2" theme="dark">\n    <label>Firewall Details</label>\n'
       '    <description>' + DESCRIPTION + '</description>\n'
       '    <definition><![CDATA[\n' + json.dumps(definition, indent=1) + '\n    ]]></definition>\n</dashboard>\n')
open(sys.argv[1] if len(sys.argv) > 1 else OUT, "w").write(xml)
