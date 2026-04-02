#!/bin/sh
# Auto-approve any pending device pairing requests after gateway starts.
# Runs in background, checks every 5 seconds for the first 120 seconds.

sleep 8
for i in $(seq 1 24); do
  # Extract pending request IDs (UUID format)
  pending=$(node dist/index.js devices list 2>/dev/null | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' 2>/dev/null)
  for req in $pending; do
    node dist/index.js devices approve "$req" 2>/dev/null && \
      echo "[auto-pair] Approved $req"
  done
  sleep 5
done
