#!/usr/bin/env bash
# Start a new protocol version from an existing one.
#   ./new_version.sh full_protocol_24 full_protocol_24_v2 "Shorter PCR, no SybrGreen read"
# Copies protocol/ and config/ (not viz/), marks the copy as a local variant, and builds it.
# Edit protocols/<new>/protocol/... then run ./build.sh <new>.
# Compare with: diff -ru protocols/<from>/protocol protocols/<new>/protocol
set -euo pipefail
cd "$(dirname "$0")"
from="${1:?usage: new_version.sh <from> <new-name> [title]}"
to="${2:?usage: new_version.sh <from> <new-name> [title]}"
title="${3:-$to}"
[[ "$to" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "name may contain only letters, digits, _ . -" >&2; exit 1; }
[[ -d "protocols/$from" ]] || { echo "no such version: protocols/$from" >&2; exit 1; }
[[ ! -e "protocols/$to" ]] || { echo "protocols/$to already exists" >&2; exit 1; }
mkdir -p "protocols/$to"
cp -r "protocols/$from/protocol" "protocols/$from/config" "protocols/$to/"
python3 -I - "protocols/$to/config/source.json" "$from" "$to" "$title" <<'PY'
import json, sys
path, base, name, title = sys.argv[1:]
src = json.load(open(path))
src.update({"name": name, "title": title, "derived_from": base, "branch": None,
            "commit": None, "commit_date": None, "repo_blob_url": None,
            "base_commit": src.get("commit") or src.get("base_commit")})
json.dump(src, open(path, "w"), indent=2)
PY
./build.sh "$to"
echo "Created protocols/$to (variant of $from)." >&2
