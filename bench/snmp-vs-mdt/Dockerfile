# SNMP poller image for the MDT-vs-SNMP bench: net-snmp (snmpbulkwalk) and python3 only.
FROM docker.io/library/debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends snmp python3 \
 && rm -rf /var/lib/apt/lists/*
ENV HOME=/tmp
COPY poller.py /app/poller.py
