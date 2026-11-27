#!/usr/bin/env python3
"""Render every Opentrons protocol of a version the way full_run.py does, simulate it, and tally
the tips and liquid each run uses.

full_run.py never hands a protocol file to the robot as it is on disk: helper_functions
.generate_ot2_protocol() substitutes the $variables first (combinations, the round's master-mix
column, the first unused tip, tip-swap slots). This replays that substitution for the whole
3-round sequence and runs the real Opentrons simulator on each result, so a failure here is a
failure the run would hit. It then parses the simulator's command log to report, per protocol:

  * tips picked up, per tip box, and whether a box ran out
  * liquid aspirated from each source well (how much to load) and dispensed into each
    destination well, with a warning when a well goes over its labware's capacity

The opentrons package is not a dependency of this repo. The Flex needs a recent version and the
OT-2 was dropped after 9.x, so two virtualenvs are needed:

    python3 -m venv /tmp/otenv  && /tmp/otenv/bin/pip  install opentrons           # Flex
    python3 -m venv /tmp/ot2env && /tmp/ot2env/bin/pip install 'opentrons==8.8.2'  # OT-2
    python3 -I tools/simulate_protocols.py --version full_protocol_24_3round \
        --flex-python /tmp/otenv/bin/python --ot2-python /tmp/ot2env/bin/python

Exit status is non-zero if any protocol fails to simulate.
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_COMBINATIONS = REPO / "incoming" / "combinations_oracle_1008.json"

# Well capacities the simulator does not enforce, for the overfill check (uL per well).
CAPACITY = {
    "opentrons_96_wellplate_200ul_pcr_full_skirt": 200,
    "corning_96_wellplate_360ul_flat": 360,
    "nest_12_reservoir_15ml": 15000,
    "nest_96_wellplate_100ul_pcr_full_skirt": 100,
}
TIPS_PER_BOX = 96


def load_combinations(path: Path):
    """The design-server payload full_run.py gets from collect_combinations()."""
    d = json.loads(path.read_text())
    return {"combinations": str(d["combinations"]),
            "use_combinations": str(d["use_combinations"]),
            "non_combinatorial_sources": str(d["non_combinatorial_sources"])}


def combination_counts(payload):
    """(combinations, columns, fragment transfers) without importing the version's helpers: the
    older single-run versions ship a helper_functions.py that predates these."""
    import ast
    import itertools
    use = payload["use_combinations"]
    use = use if isinstance(use, bool) else str(use) != "False"
    combos = (list(itertools.product(*ast.literal_eval(payload["combinations"]))) if use
              else ast.literal_eval(payload["non_combinatorial_sources"]))
    return len(combos), (len(combos) + 7) // 8, sum(len(c) for c in combos)


def plan_from_events(app: Path, payload_base, events):
    """Protocol runs in the order the run map says full_run.py submits them.

    Used for a version whose protocols take no tip-start or per-round variables, so the combination
    payload is all they need. The 3-round version does need those and gets the plan below instead.
    """
    sys.path.insert(0, str(app / "src"))
    import helper_functions as hf

    steps = []
    for step in events["steps"]:
        if step["kind"] != "protocol":
            continue
        phase = step["phase"]
        rnd = int(phase[1:].split()[0]) if phase[:1] == "R" and phase[1:2].isdigit() else 1
        steps.append((rnd, step["protocol"], hf.collect_ot2_replacement_variables(dict(payload_base))))
    n, cols, sources = combination_counts(payload_base)
    return steps, hf, {"combinations": n, "columns": cols, "fragment_transfers": sources, "swap_sites": []}


def needs_tip_plan(app: Path):
    """True when the version's protocols expect the tip-start variables full_run.py counts out."""
    return any("_tip_start" in f.read_text() for f in (app / "protocols").glob("*.py"))


def plan(app: Path, payload_base):
    """The (round, protocol, variables) triples full_run.py would generate, in run order."""
    sys.path.insert(0, str(app / "src"))
    import helper_functions as hf

    n_combos, n_cols, n_sources = hf.combination_counts(payload_base)
    tips = {
        "ot2_20": hf.TipLedger("OT-2 20 uL", racks=6, spare_slots=["rack2_row1_nest2"], swap_start=60),
        "flex_200": hf.TipLedger("Flex 200 uL", racks=1, tip_type="opentrons_flex_96_tiprack_200ul",
                                 deck_slot="A1", spare_slots=["D4"]),
        "flex_50": hf.TipLedger("Flex 50 uL 8-channel", racks=1, tip_type="opentrons_flex_96_tiprack_50ul",
                                deck_slot="A2", spare_slots=["B4", "C4"]),
        "flex_50_single": hf.TipLedger("Flex 50 uL single", racks=1, unit="tip"),
    }
    steps = []

    def step(rnd, name, base, **tip_starts):
        steps.append((rnd, name, hf.collect_ot2_replacement_variables(dict(base, tip_starts=tip_starts))))

    def swap(rnd, base, ledger):
        spare = ledger.swap()
        swap_vars = {"tip_type": ledger.tip_type, "deck_slot": ledger.deck_slot, "spare_slot": spare}
        steps.append((rnd, "flex_tips_swap.py",
                      hf.collect_ot2_replacement_variables(dict(base, swap_vars=swap_vars))))

    # Every tip-swap check full_run.py makes, in the same order, recorded so the run map can show
    # which swaps really fire and grey out the ones that never do. The index is the check's
    # position within its round, which is how the two sides line up.
    sites, site_no = [], {}

    def site(rnd, name, needed):
        i = site_no[rnd] = site_no.get(rnd, -1) + 1
        fired = bool(tips[name].needs_swap(needed))
        sites.append({"round": rnd, "index": i, "ledger": name, "fired": fired,
                      # a fired swap puts a fresh box in this deck slot, before the step that follows
                      "deck_slot": tips[name].deck_slot or "3", "before_step": len(steps)})
        return fired

    for rnd in (1, 2, 3):
        base = dict(payload_base, round_vars={"round_num": rnd, "pcr_mm_start_well": 8 * (8 + rnd)})
        gg_cols = n_cols + (n_sources + 7) // 8
        if site(rnd, "ot2_20", gg_cols):        # PF400 workflow, not a protocol: nothing to simulate
            tips["ot2_20"].swap()
        step(rnd, "pd_golden_gate_ot2_v2.py", base, ot2_tip_start=tips["ot2_20"].take(gg_cols))
        if site(rnd, "flex_200", n_cols):
            swap(rnd, base, tips["flex_200"])
        step(rnd, "pd_pcr_v2_flex.py", base, flex200_tip_start=tips["flex_200"].take(n_cols))
        if site(rnd, "ot2_20", 2 * n_cols):
            tips["ot2_20"].swap()
        step(rnd, "pd_pcr_v2_ot2.py", base, ot2_tip_start=tips["ot2_20"].take(2 * n_cols))
        if site(rnd, "ot2_20", n_cols + 2):
            tips["ot2_20"].swap()
        step(rnd, "pd_dilute_1to50_ot2.py", base, ot2_tip_start=tips["ot2_20"].take(n_cols + 2))
        if site(rnd, "flex_50", n_cols + 2):
            swap(rnd, base, tips["flex_50"])
        step(rnd, "cell_free_lyo_flex.py", base, flex50_tip_start=tips["flex_50"].take(n_cols + 2))
        if site(rnd, "flex_200", 1):
            swap(rnd, base, tips["flex_200"])
        if site(rnd, "flex_50", n_cols + 1):
            swap(rnd, base, tips["flex_50"])
        step(rnd, "pd_fdglu_flex_v2.py", base,
             flex200_tip_start=tips["flex_200"].take(1),
             flex50_tip_start=tips["flex_50"].take(n_cols + 1),
             flex50_single_start=tips["flex_50_single"].take(6))
    return steps, hf, {"combinations": n_combos, "columns": n_cols, "fragment_transfers": n_sources,
                       "swap_sites": sites}


def audit_tips(runs, sites, out_dir):
    """Has any physical tip been picked up twice?

    The tip counter decides where each run should start; this checks what the robot would actually
    do with those numbers. Every pick-up is expanded to the wells it takes, per deck slot, and a
    well seen twice means two runs would reach for the same tip. A fired swap puts a fresh box in
    that slot, so its record starts again there.
    """
    fresh = defaultdict(list)       # index in the run order -> deck slots that get a fresh box
    for site in sites:
        if site["fired"]:
            fresh[site["before_step"]].append(site["deck_slot"])
    used, reused, boxes = defaultdict(dict), [], defaultdict(int)
    for i, run in enumerate(runs):
        for slot in fresh.get(i, []):
            used[slot].clear()
            boxes[slot] += 1
        log_path = out_dir / f"r{run['round']}_{Path(run['protocol']).stem}.log.json"
        if not run.get("ok") or not log_path.exists():
            continue
        active = {}
        for cmd in json.loads(log_path.read_text()):
            if cmd["kind"] == "configure":
                style = (cmd["style"] or "").upper()
                active[cmd["mount"]] = 1 if "SINGLE" in style else 8 if "COLUMN" in style else (cmd["channels"] or 1)
                continue
            if cmd["kind"] != "pick_up_tip":
                continue
            n = active.get(cmd["mount"], cmd["channels"] or 1)
            where = f"round {run['round']} {run['protocol']}"
            for w in well_list(cmd["well"], n):
                if w in used[cmd["slot"]]:
                    reused.append({"slot": cmd["slot"], "well": w,
                                   "first": used[cmd["slot"]][w], "again": where})
                used[cmd["slot"]][w] = where
    status = [{"slot": slot, "boxes_used": boxes[slot] + 1, "tips_used_in_current_box": len(wells),
               "tips_left_in_current_box": TIPS_PER_BOX - len(wells)}
              for slot, wells in sorted(used.items(), key=lambda kv: (len(kv[0]), kv[0]))]
    return {"reused": reused, "boxes": status}


def well_list(well, channels):
    """The tip wells one pick-up takes: an 8-channel pick-up takes a whole column."""
    row, col = well[0], well[1:]
    return [f"{r}{col}" for r in "ABCDEFGH"[:channels]] if channels and channels > 1 and row == "A" else [well]


def tally(log):
    """Tips and liquid from the structured command log (tools/_sim_driver.py).

    A pick-up consumes as many tips as the pipette has *active* nozzles, so the nozzle layout each
    mount was configured with is tracked (SINGLE takes 1 tip, COLUMN takes 8): the hardware channel
    count alone would count every single-tip pick-up as 8. An 8-channel step also touches 8 wells,
    so a plate column is expanded to its 8 wells, while a reservoir well is hit by every channel at
    once and takes 8x the volume. A mix() moves liquid in place, and the simulator prints its
    aspirate/dispense pairs one nesting level deeper, so those are skipped by level.
    """
    boxes = defaultdict(lambda: {"tips": 0, "pickups": 0})
    wells = defaultdict(lambda: {"aspirated": 0.0, "dispensed": 0.0})
    active = {}        # mount -> active nozzle count
    mix_level = None   # inside a mix(): its own aspirate/dispense pairs move nothing

    def nozzles(cmd):
        return active.get(cmd["mount"], cmd["channels"] or 1)

    for cmd in log:
        kind, level = cmd["kind"], cmd.get("level", 0)
        if mix_level is not None and level <= mix_level:
            mix_level = None
        if kind == "configure":
            style = (cmd["style"] or "").upper()
            active[cmd["mount"]] = 1 if "SINGLE" in style else 8 if "COLUMN" in style else (cmd["channels"] or 1)
            continue
        if kind == "mix":
            mix_level = level
            continue
        if kind == "pick_up_tip":
            box = boxes[f"{cmd['labware']} on {cmd['slot']}"]
            box["tips"] += nozzles(cmd)
            box["pickups"] += 1
        elif kind in ("aspirate", "dispense"):
            if mix_level is not None or cmd["labware"] is None or cmd["volume"] is None:
                continue
            n = nozzles(cmd)
            field = "aspirated" if kind == "aspirate" else "dispensed"
            if "reservoir" in (cmd["labware"] or ""):
                # every active channel draws from the same reservoir well
                wells[(cmd["labware"], cmd["slot"], cmd["well"])][field] += cmd["volume"] * n
            else:
                row, col = (cmd["well"] or "A1")[0], (cmd["well"] or "A1")[1:]
                rows = "ABCDEFGH"[:n] if n > 1 and row == "A" else row
                for r in rows:
                    wells[(cmd["labware"], cmd["slot"], f"{r}{col}")][field] += cmd["volume"]

    liquid = [{"labware": lw, "slot": slot, "well": w,
               "aspirated": round(v["aspirated"], 1), "dispensed": round(v["dispensed"], 1)}
              for (lw, slot, w), v in sorted(wells.items())]
    overfilled = [x for x in liquid if x["dispensed"] > CAPACITY.get(x["labware"], 1e9)]
    overdrawn = [k for k, v in boxes.items() if v["tips"] > TIPS_PER_BOX]
    return {"tip_boxes": {k: v["tips"] for k, v in boxes.items()},
            "tip_pickups": {k: v["pickups"] for k, v in boxes.items()},
            "liquid": liquid, "overfilled": overfilled, "boxes_overdrawn": overdrawn}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True, help="folder name under protocols/")
    ap.add_argument("--flex-python", default=sys.executable, help="interpreter with a recent opentrons")
    ap.add_argument("--ot2-python", default=sys.executable, help="interpreter with opentrons 8.x (OT-2 support)")
    ap.add_argument("--combinations", type=Path, default=DEFAULT_COMBINATIONS,
                    help="design-server payload JSON (default: the saved oracle 1008 example)")
    ap.add_argument("--out", type=Path, help="where to write rendered protocols and the report")
    ap.add_argument("--only", help="simulate just the protocols whose name contains this")
    a = ap.parse_args()

    base = REPO / "protocols" / a.version
    app = base / "protocol"
    out = a.out or (base / "viz" / "simulated")
    out.mkdir(parents=True, exist_ok=True)
    payload = load_combinations(a.combinations)
    if needs_tip_plan(app):
        steps, hf, counts = plan(app, payload)
    else:
        steps, hf, counts = plan_from_events(app, payload, json.loads((base / "viz" / "events.json").read_text()))
    print(f"{a.combinations.name}: {counts['combinations']} combinations, {counts['columns']} columns, "
          f"{counts['fragment_transfers']} fragment transfers per round\n")

    results, failures = [], 0
    for rnd, name, variables in steps:
        if a.only and a.only not in name:
            continue
        src = app / "protocols" / name
        is_ot2 = '"OT-2"' in src.read_text()
        rendered = Path(hf.generate_ot2_protocol(src, variables))
        target = out / f"r{rnd}_{name}"
        target.write_text(rendered.read_text())
        rendered.unlink()
        log_path = target.with_suffix(".log.json")
        proc = subprocess.run([a.ot2_python if is_ot2 else a.flex_python,
                               str(REPO / "tools" / "_sim_driver.py"), str(target), str(log_path)],
                              capture_output=True, text=True, cwd=out)
        ok = proc.returncode == 0 and log_path.exists()
        failures += not ok
        row = {"round": rnd, "protocol": name, "robot": "OT-2" if is_ot2 else "Flex", "ok": ok}
        if ok:
            row.update(tally(json.loads(log_path.read_text())))
        else:
            row["error"] = " | ".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])[:400]
        results.append(row)
        extra = ""
        if ok:
            extra = "  tips: " + (", ".join(
                f"{n} from {b.replace('opentrons_', '').replace('_96_', ' ').replace('filtertiprack', 'tips').replace('tiprack', 'tips')}"
                for b, n in row["tip_boxes"].items()) or "none")
            if row["overfilled"]:
                extra += f"  OVERFILL {len(row['overfilled'])} well(s)"
            if row["boxes_overdrawn"]:
                extra += f"  TIP BOX EMPTY: {', '.join(row['boxes_overdrawn'])}"
        print(f"{'ok  ' if ok else 'FAIL'} round {rnd} {name:28s}{extra}"
              f"{'' if ok else chr(10) + '     ' + row['error']}", flush=True)

    sites = counts.pop("swap_sites", [])
    audit = audit_tips(results, sites, out)
    summary = summarise(results)
    report = {"version": a.version, "combinations_file": str(a.combinations), "counts": counts,
              "swap_sites": sites, "tip_audit": audit,
              "summary": summary, "runs": results}
    (out / "report.json").write_text(json.dumps(report, indent=1))

    print("\nTip boxes at the end of the run (a swap starts a slot's count again):")
    for b in audit["boxes"]:
        print(f"  slot {b['slot']:<3} {b['tips_used_in_current_box']:3d} of {TIPS_PER_BOX} tips used"
              f"{' in box ' + str(b['boxes_used']) if b['boxes_used'] > 1 else ''}"
              f", {b['tips_left_in_current_box']} left")
    if audit["reused"]:
        print(f"  TIP REUSED: {len(audit['reused'])} tip(s) would be picked up twice:")
        for x in audit["reused"][:5]:
            print(f"    slot {x['slot']} well {x['well']}: {x['first']}, then {x['again']}")
    else:
        print("  no tip is picked up twice: the counter's starting positions do not overlap")

    print("\nTips for the whole run (a slot is refilled when the gripper swaps a box in):")
    for slot, n in sorted(summary["tips_per_slot"].items()):
        boxes = -(-n // TIPS_PER_BOX)
        print(f"  {n:5d} tips  {slot}   = {boxes} box{'es' if boxes != 1 else ''} of {TIPS_PER_BOX}")
    print("\nReagent to load (reservoirs are never swapped, so these are run totals, before dead volume):")
    for key, v in sorted(summary["reservoir_uses"].items()):
        robot, slot, well = key.split(" | ")
        print(f"  {v / 1000:6.2f} mL  {robot} reservoir on slot {slot}, well {well}")
    fullest = summary["fullest_well"]
    if fullest:
        print(f"\nFullest well in any single run: {fullest['dispensed']} uL into {fullest['well']} of "
              f"{fullest['labware']} (capacity {CAPACITY.get(fullest['labware'], '?')} uL)")
    print(f"\n{len(results) - failures}/{len(results)} simulated. Report: {out / 'report.json'}")
    return 1 if failures or audit["reused"] else 0


def summarise(results):
    """Totals across the whole run: tips per deck slot, reagent per reservoir well, fullest well."""
    tips, reservoirs, fullest = defaultdict(int), defaultdict(float), None
    for run in results:
        for box, n in run.get("tip_boxes", {}).items():
            tips[box] += n
        for row in run.get("liquid", []):
            if "reservoir" in row["labware"]:
                reservoirs[(run["robot"], row["slot"], row["well"])] += row["aspirated"]
            elif fullest is None or row["dispensed"] > fullest["dispensed"]:
                fullest = row
    return {"tips_per_slot": dict(tips),
            # json keys must be strings
            "reservoir_uses": {" | ".join(k): round(v, 1) for k, v in reservoirs.items()},
            "fullest_well": fullest}


if __name__ == "__main__":
    sys.exit(main())
