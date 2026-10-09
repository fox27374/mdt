# Podman Exporter Fixtures

This directory contains fixtures captured from prometheus-podman-exporter running on the test host (kof-ibk-debian4). The fixtures were captured on 2026-10-09.

## Image and Run Command

The image used was **quay.io/navidys/prometheus-podman-exporter:latest** (exporter version 2.0.0). It talks to the rootless podman API socket of user `claude`, started with `podman system service --time=0 unix:///<dir>/podman.sock`.

The command that worked:

```
podman run -d --name fx-exporter --net host --userns=keep-id --user 10782:10782 \
  -e HOME=/tmp -e CONTAINER_HOST=unix:///run/podman/podman.sock \
  -v <dir>/podman.sock:/run/podman/podman.sock \
  quay.io/navidys/prometheus-podman-exporter:latest --web.listen-address=127.0.0.1:19882
```

Notes:
- `--userns=keep-id` and `--user <uid>` are needed so the container user can open the host socket (rootless).
- `HOME` must be set, otherwise the exporter fails with `stat /.config`.
- `CONTAINER_HOST` must be set, otherwise the exporter fails with `"" is not a supported schema`.

## Files

- `podman_exporter.txt`: first scrape, with 4 running containers (`fx-a`, `fx-b`, `fx-c`, `fx-exporter`) and one exited container (`fx-t`).
- `podman_exporter_second.txt`: second scrape, 30 seconds later. Counters (`podman_container_cpu_seconds_total`) have increased.

## Metric Families

Per container (all carry `id` = 12-character short container ID, plus `pod_id` and `pod_name`, which are empty here):

- `podman_container_cpu_seconds_total` (counter): total CPU time in seconds.
- `podman_container_cpu_system_seconds_total` (counter): CPU time in kernel mode.
- `podman_container_mem_usage_bytes` (gauge): memory in use.
- `podman_container_mem_limit_bytes` (gauge): memory limit. Without `--memory`, this is the host memory size (about 4.1e9 bytes on this host), not zero.
- `podman_container_pids` (gauge)
- `podman_container_state` (gauge): 2 = running, 5 = exited (podman state enum).
- `podman_container_info` (gauge, value 1): labels `id`, `name`, `image`, `image_id`, `pod_id`, `pod_name`, `ports`. The container name is only in this family.
- Also present but not used: `*_block_*`, `*_net_*`, `*_rootfs_size_bytes`, `*_rw_size_bytes`, `*_created_seconds`, `*_started_seconds`, `*_exited_seconds`, `*_exit_code`, `*_health`.

Collector status: `podman_scrape_collector_success{collector="container"}` (1 = ok).

## Notes

- Join `podman_container_info` to the other families by `id`.
- `pod_id` and `pod_name` are empty for plain containers.
- Stopped containers still show `podman_container_info` and `podman_container_state`, but may have no CPU or memory series.
