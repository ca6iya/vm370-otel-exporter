#!/bin/sh
# Seed /data/cp.txt from the contract sample when the volume is empty, then
# serve /metrics. Extra flags are appended as-is.
set -eu

mkdir -p /data
TEXT="${VM370_TEXT:-/data/cp.txt}"
if [ ! -s "$TEXT" ]; then
  cp /app/examples/cp-sample.txt "$TEXT"
fi

if [ "$#" -eq 0 ] || [ "${1#-}" != "$1" ]; then
  set -- python -m vm370_otel_exporter --text "$TEXT" "$@"
  if [ -n "${VM370_OTLP:-}" ]; then
    set -- "$@" --otlp "$VM370_OTLP"
    if [ "${VM370_OTLP_INSECURE:-0}" = "1" ]; then
      set -- "$@" --otlp-insecure
    fi
  fi
fi

exec "$@"
