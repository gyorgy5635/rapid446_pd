#!/usr/bin/env python3
"""Export archived workflow runs from a MADSci workcell manager (read-only).

Run this on a machine that can reach the workcell manager, then copy the output
file into this project as protocols/<version>/viz/madsci_history.json and run ./build.sh <version>.

Uses only the Python standard library, so it runs anywhere Python 3.8+ is installed.

    python3 export_madsci_history.py --workcell-url http://<workcell-host>:8005/ --number 500 \
        --out madsci_history.json
    # optional: keep only one or more experiment runs
    python3 export_madsci_history.py --workcell-url ... --experiment-id 01J... --out run.json

The workcell manager URL is the WORKCELL_SERVER_URL in your MADSci settings
(MADSci's default port for it is 8005). It is not the lab server URL (port 8000).
Calls GET {workcell}/workflows/archived?number=N, the same call as
WorkcellClient.get_archived_workflows().
"""
import argparse
import collections
import json
import sys
import urllib.parse
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workcell-url", required=True, help="workcell manager base URL, e.g. http://host:8005/")
    ap.add_argument("--number", type=int, default=500, help="how many archived workflows to fetch (newest first)")
    ap.add_argument("--experiment-id", action="append", default=[], help="keep only these experiment ids (repeatable)")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    base = a.workcell_url if a.workcell_url.endswith("/") else a.workcell_url + "/"
    url = base + "workflows/archived?" + urllib.parse.urlencode({"number": a.number})
    with urllib.request.urlopen(url, timeout=a.timeout) as r:
        data = json.load(r)
    if isinstance(data, list):
        data = {w.get("workflow_id", str(i)): w for i, w in enumerate(data)}

    def exp_id(w):
        return ((w.get("ownership_info") or {}).get("experiment_id")) or "(none)"

    if a.experiment_id:
        data = {k: w for k, w in data.items() if exp_id(w) in a.experiment_id}

    with open(a.out, "w") as f:
        json.dump(data, f)

    # Summary so you can pick an experiment id.
    groups = collections.defaultdict(list)
    for w in data.values():
        groups[exp_id(w)].append(w)
    print(f"Saved {len(data)} workflows to {a.out}", file=sys.stderr)
    for eid, ws in sorted(groups.items(), key=lambda kv: min((w.get("start_time") or "") for w in kv[1])):
        starts = sorted(w.get("start_time") or "" for w in ws)
        print(f"  experiment {eid}: {len(ws)} workflows, {starts[0][:19]} .. {starts[-1][:19]}", file=sys.stderr)


if __name__ == "__main__":
    main()
