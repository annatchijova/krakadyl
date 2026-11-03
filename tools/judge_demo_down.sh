#!/usr/bin/env bash
# Stop the KRAKADYL judge demo published by tools/judge_demo_up.sh.
# Matches only the demo processes (demo-specific ports 8010/4173).
set -u -o pipefail

for pattern in "uvicorn.*krakadyl.api.app.*8010" "ngrok.*krakadyl-tunnels.yml" "vite preview.*4173"; do
  for pid in $(pgrep -f "$pattern" 2>/dev/null); do
    echo "stopping $pid ($pattern)"
    kill "$pid" 2>/dev/null || true
  done
done
sleep 2
for pattern in "uvicorn.*krakadyl.api.app.*8010" "ngrok.*krakadyl-tunnels.yml" "vite preview.*4173"; do
  for pid in $(pgrep -f "$pattern" 2>/dev/null); do kill -9 "$pid" 2>/dev/null || true; done
done
echo "demo stopped"
