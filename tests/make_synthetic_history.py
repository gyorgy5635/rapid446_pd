#!/usr/bin/env python3
"""TEST FIXTURE ONLY: write a fake MADSci archived-workflow export shaped like the real API output.

Durations are the estimates times random noise; nothing here is measured. Used to exercise
extract_events.py --history without access to the workcell manager.

    python3 -I tests/make_synthetic_history.py --events viz/events.json --out /tmp/synthetic_history.json
"""
import argparse
import datetime as dt
import json
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ev = json.load(open(a.events))
    random.seed(7)
    steps_by_call = {}
    for st in ev["steps"]:
        steps_by_call.setdefault(st["call"], []).append(st)
    S = ev["steps"]
    after_pause = {next((x["call"] for x in S[st["i"] + 1:] if x["call"] is not None), None) for st in S if st["kind"] == "pause"}
    out = {}

    def run(exp_id, start, drop=(), fail_at=None, noise=0.25):
        t = start
        for c in ev["calls"]:
            if c["id"] in drop:
                continue
            t += dt.timedelta(seconds=random.uniform(3, 15))
            if c["id"] in after_pause:
                t += dt.timedelta(minutes=random.uniform(4, 12))  # operator pause
            wf_start, steps = t, []
            for k, (node, action) in enumerate(c["sig"]):
                est = steps_by_call[c["id"]][k]["duration_s"]
                d = est * random.uniform(1 - noise, 1 + noise)
                steps.append({"name": f"step {k}", "node": node, "action": action,
                              "start_time": t.isoformat() + "Z", "end_time": (t + dt.timedelta(seconds=d)).isoformat() + "Z",
                              "status": "succeeded"})
                t += dt.timedelta(seconds=d)
            wid = f"{exp_id}-{c['id']}"
            status = {"completed": True, "failed": False, "cancelled": False}
            if fail_at == c["id"]:
                out[wid + "-failed"] = {"workflow_id": wid + "-failed", "name": c["wf_name"], "steps": steps[:1],
                                        "start_time": wf_start.isoformat() + "Z", "end_time": t.isoformat() + "Z",
                                        "status": {"completed": False, "failed": True},
                                        "ownership_info": {"experiment_id": exp_id}}
                t += dt.timedelta(seconds=30)
            out[wid] = {"workflow_id": wid, "name": c["wf_name"], "steps": steps,
                        "start_time": wf_start.isoformat() + "Z", "end_time": t.isoformat() + "Z",
                        "status": status, "ownership_info": {"experiment_id": exp_id}}

    run("SYNTH-RUN-A", dt.datetime(2026, 7, 24, 8, 0))
    run("SYNTH-RUN-B", dt.datetime(2026, 8, 6, 8, 0), drop={20, 21}, fail_at=40)
    # an unrelated experiment that should not line up
    for i in range(6):
        out[f"other-{i}"] = {"workflow_id": f"other-{i}", "name": "something else", "steps": [{"node": "x", "action": "y"}],
                             "start_time": f"2026-09-01T0{i}:00:00Z", "end_time": f"2026-09-01T0{i}:30:00Z",
                             "status": {"completed": True}, "ownership_info": {"experiment_id": "SYNTH-OTHER"}}
    json.dump(out, open(a.out, "w"))
    print(f"wrote {len(out)} synthetic workflows to {a.out}")


if __name__ == "__main__":
    main()
