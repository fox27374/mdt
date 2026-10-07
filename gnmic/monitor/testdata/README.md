# Live Test Fixtures for gnmic-monitor Parsers

This directory contains live data samples captured from the running MDT (Streaming Telemetry) stack, used for testing the gnmic-monitor parsers.

## Answering Documentation Questions

### 1. NATS Events

The payload is a JSON **array** (one array per NATS message). The subscription name is stored in the tag key `subscription-name` (e.g., `"subscription-name": "xe_mem_stats"`). The target is identified by the tag key `source`, which contains the configured target name (e.g., `"source": "ibk-lab-sw98"`). The `timestamp` field is in nanoseconds since epoch (e.g., `1791390138349328000`).

### 2. Collector API `/api/v1/targets`

The top-level JSON object is keyed by target name (e.g., `{"Lab-IBK-PA560-2": {...}, "ibk-lab-ewlc01": {...}}`). Within each target, the `config` object contains the `name` (configured name), `address` (IP:port), and `subscriptions` (array of subscription names). The `sample-interval` is a number representing nanoseconds (e.g., `30000000000` for 30 seconds). Each collector instance lists only the targets it owns; gnmic-1 lists different targets than gnmic-2 based on the clustering/locking mechanism.

### 3. gnmic Metrics

The label values of `name` in metrics like `gnmic_target_up` and `gnmic_target_connection_state` contain the target's configured name (e.g., `Lab-IBK-PA560-2`, `ibk-lab-sw98`, `ibk-lab-ewlc01`). The labels `source` and `subscription` in `gnmic_subscribe_number_of_failed_subscribe_request_messages_total` contain the target's configured name (e.g., `source="ibk-lab-sw99"`) and subscription name (e.g., `subscription="xe_if_stats"`).

### 4. Consul Service Registration

The registered service name is `mdt-gnmic-api`. The tags include `instance-name=gnmic-1` (or `gnmic-2`), `cluster-name=mdt`, and `__protocol=http`. Target lock keys in Consul KV follow the pattern `gnmic/mdt/targets/<target-name>` (e.g., `gnmic/mdt/targets/ibk-lab-sw98`), plus a leader election key at `gnmic/mdt/leader`.

### 5. NATS Server Info

The `/varz` endpoint returns a JSON object with integer fields: `connections` (number of connected clients), `in_msgs` (total messages received), and `out_msgs` (total messages sent). The `/healthz` endpoint returns `{"status":"ok"}` to indicate the server is operational.

## Fixture Files

- `api_targets_gnmic-1.json`, `api_targets_gnmic-2.json`: Responses from gnmic collector API
- `metrics_gnmic-1.txt`, `metrics_gnmic-2.txt`: Prometheus metrics (gnmic_* lines only)
- `nats_varz.json`, `nats_healthz.json`: NATS server stats and health
- `nats_mdt_1.json` through `nats_mdt_5.json`: Individual NATS messages from the `mdt` subject
- `consul_*.json`: Consul service registration and KV data
