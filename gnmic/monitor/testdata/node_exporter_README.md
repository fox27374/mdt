# Node Exporter Fixtures

This directory contains fixtures captured from the Prometheus node_exporter running on the test host (kof-ibk-debian4). The fixtures were captured on 2026-10-08.

## Image Tag and Podman Command

The image tag used was **v1.12.1** from `docker.io/prom/node-exporter`.

The exact `podman run` command that worked was:

```
podman run -d --name ne-fixture --net host --pid host -v /:/host:ro docker.io/prom/node-exporter:v1.12.1 --path.rootfs=/host --web.listen-address=127.0.0.1:19100
```

Note: The `rslave` option (`,rslave`) was not used, as it was not required in this rootless setup.

## Filesystem Combinations

The following `(device, fstype, mountpoint)` combinations appear for `node_filesystem_size_bytes`:

- `/dev/sda1` (ext4) at `/` — real disk
- `tmpfs` at `/run` — virtual memory filesystem
- `tmpfs` at `/run/lock` — virtual memory filesystem
- `tmpfs` at `/run/user/1000` — user runtime directory
- `tmpfs` at `/run/user/10782` — user runtime directory

All mountpoints are host-relative (for example `/` not `/host`).

## Network Interfaces

The following network interface names appear in the data:

- `lo` (loopback): no `node_network_speed_bytes` sample
- `ens192` (Ethernet): 1.25e+09 bytes per second (1.25 gigabytes per second = 10 Gbit/s)
- `docker0` (bridge): -125000 bytes per second (speed unknown)

**Unit:** bytes per second. A negative value indicates the speed is unknown or not applicable.

## CPU Information

The test host has **2 CPUs** (cpu="0" and cpu="1").

The `mode` label values of `node_cpu_seconds_total` are:

- `idle`
- `iowait`
- `irq`
- `nice`
- `softirq`
- `steal`
- `system`
- `user`

## Notes

No missing metric families or unexpected label names were observed. The second scrape (taken 30 seconds after the first) shows correctly increasing values for `node_cpu_seconds_total` and `node_network_receive_bytes_total`, confirming the counters are working as expected.
