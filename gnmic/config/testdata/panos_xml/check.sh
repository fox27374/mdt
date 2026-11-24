#!/usr/bin/env bash
# Runs the panos-xmlapi processor from gnmic/config/mdt.yaml over the fixtures in this directory and diffs the
# output with expected/<name>.json (keys sorted). Each panos_xml_<name>.jsonl is one NATS message: a JSON array of
# events, as gnmic emits it. Runs the gnmic image the stack uses, so jq (gojq) and strptime are the ones in production.
#   gnmic/config/testdata/panos_xml/check.sh               (needs podman and jq)
#   scripts/mdthost 'bash gnmic/config/testdata/panos_xml/check.sh'   (the container test host)
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
cfg=$(cd "$dir/../.." && pwd)
img=${GNMIC_IMAGE:-ghcr.io/openconfig/gnmic:0.46.0}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0
for in in "$dir"/panos_xml_*.jsonl; do
  name=$(basename "$in" .jsonl)
  # Mounted where the stack mounts it (/app/config: tls-ca paths in mdt.yaml point there).
  podman run --rm --entrypoint /app/gnmic -v "$cfg":/app/config:ro -v "$dir":/fx:ro "$img" \
    --config /app/config/mdt.yaml processor --name panos-xmlapi --input "/fx/$name.jsonl" > "$tmp/$name.json"
  if diff -u <(jq -S . "$dir/expected/$name.json") <(jq -S . "$tmp/$name.json"); then
    echo "ok   $name"
  else
    echo "FAIL $name"; fail=1
  fi
done
exit $fail
