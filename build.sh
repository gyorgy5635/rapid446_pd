#!/usr/bin/env bash
# Build the run map for one protocol version, or for all of them.
#   ./build.sh                    # every folder under protocols/
#   ./build.sh full_protocol_24   # just one
# A version folder holds protocol/ (src, workflows, protocols), config/ and viz/.
# If viz/madsci_history.json exists, measured MADSci durations replace the estimates.
set -euo pipefail
cd "$(dirname "$0")"
names=("$@")
if [[ ${#names[@]} -eq 0 ]]; then
  for d in protocols/*/; do names+=("$(basename "$d")"); done
fi
for name in "${names[@]}"; do
  v="protocols/$name"
  [[ -f "$v/protocol/src/full_run.py" ]] || { echo "skip $name: no $v/protocol/src/full_run.py" >&2; continue; }
  echo "== $name" >&2
  mkdir -p "$v/viz"
  hist=()
  [[ -f "$v/viz/madsci_history.json" ]] && hist=(--history "$v/viz/madsci_history.json")
  python3 -I tools/extract_events.py --app "$v/protocol" --config "$v/config" --out "$v/viz/events.json" "${hist[@]}"
  # liquid-handling pages, only when tools/simulate_protocols.py has been run for this version
  if [[ -f "$v/viz/simulated/report.json" ]]; then
    python3 -I tools/build_liquid_player.py --version "$name"
  fi
  python3 -I tools/build_player.py --events "$v/viz/events.json" --layout "$v/config/layout.json" \
    --template tools/player_template.html --out "$v/viz/pd_run_map.html" --liquid "$v/viz/liquid"
done
