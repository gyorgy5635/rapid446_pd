#!/usr/bin/env python3
"""Turn each simulated protocol run into a liquid-handling page.

Reads the command logs written by tools/simulate_protocols.py (which runs the real Opentrons
simulator) and writes one self-contained HTML per run: which wells end up holding liquid, which
tips were used out of which box, and the full command list.

Volumes here are what the protocol *asks for*, netted from the simulator's aspirate and dispense
commands; the simulator does not track well contents. Starting contents come from
config/contents.json, so a well is only known to be full if that file says so.

Usage:
    python3 -I tools/build_liquid_player.py --version full_protocol_24_3round
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROWS = "ABCDEFGH"

# The simulator numbers OT-2 slots 1-11; deck.json and contents.json use coordinates like the Flex.
OT2_SLOT_COORD = {"1": "D1", "2": "D2", "3": "D3", "4": "C1", "5": "C2", "6": "C3",
                  "7": "B1", "8": "B2", "9": "B3", "10": "A1", "11": "A2", "12": "A3"}


def well_list(well, channels):
    """The wells one command touches: an 8-channel step takes a whole column."""
    if not well:
        return []
    row, col = well[0], well[1:]
    if channels and channels > 1 and row == "A":
        return [f"{r}{col}" for r in ROWS[:channels]]
    return [well]


def replay(log, reservoir_names):
    """Per-labware well totals and tip use, from one run's command log."""
    labware = defaultdict(lambda: {"wells": defaultdict(lambda: {"in": 0.0, "out": 0.0, "touched": 0}),
                                   "is_tips": False, "pickups": 0, "tips": 0, "tip_wells": []})
    active, mixing = {}, False
    for cmd in log:
        kind = cmd["kind"]
        if kind == "configure":
            style = (cmd["style"] or "").upper()
            active[cmd["mount"]] = 1 if "SINGLE" in style else 8 if "COLUMN" in style else (cmd["channels"] or 1)
            continue
        if kind == "mix":
            mixing = True
            continue
        key = f"{cmd['labware']}|{cmd['slot']}"
        n = active.get(cmd["mount"], cmd["channels"] or 1)
        if kind == "pick_up_tip":
            mixing = False
            box = labware[key]
            box["is_tips"] = True
            box["pickups"] += 1
            box["tips"] += n
            for w in well_list(cmd["well"], n):
                if w not in box["tip_wells"]:
                    box["tip_wells"].append(w)
        elif kind in ("aspirate", "dispense"):
            if mixing or cmd["labware"] is None or cmd["volume"] is None:
                continue
            lw = labware[key]
            is_res = cmd["labware"] in reservoir_names or "reservoir" in (cmd["labware"] or "")
            # every channel draws from the same reservoir well, but from its own well on a plate
            wells = [cmd["well"]] if is_res else well_list(cmd["well"], n)
            volume = cmd["volume"] * n if is_res else cmd["volume"]
            for w in wells:
                cell = lw["wells"][w]
                cell["in" if kind == "dispense" else "out"] += volume
                cell["touched"] += 1
        else:
            mixing = False
    return labware


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--template", type=Path, default=REPO / "tools" / "liquid_template.html")
    a = ap.parse_args()

    base = REPO / "protocols" / a.version
    sim = base / "viz" / "simulated"
    report_path = sim / "report.json"
    if not report_path.exists():
        print(f"no simulation output in {sim}; run tools/simulate_protocols.py first")
        return 0
    report = json.loads(report_path.read_text())
    events = json.loads((base / "viz" / "events.json").read_text())
    contents = events.get("contents") or {"reagents": {}, "labware": []}
    plate_names = {p["id"]: p["name"] for p in events["plates"]}
    start_by_plate = {c["plate"]: c for c in contents["labware"] if c.get("plate")}
    start_by_key = {c["key"]: c for c in contents["labware"]}

    # deck_plates recorded per protocol step: (round, protocol file) -> {slot: plate id}
    deck_of = {}
    for step in events["steps"]:
        if step["kind"] == "protocol" and step.get("deck_plates"):
            rnd = step["phase"].split(" ")[0][1:] if step["phase"].startswith("R") else ""
            deck_of[(rnd, step["protocol"])] = step["deck_plates"]

    out_dir = base / "viz" / "liquid"
    out_dir.mkdir(parents=True, exist_ok=True)
    template = a.template.read_text()
    index, written = [], 0

    for run in report["runs"]:
        if not run.get("ok"):
            continue
        stem = f"r{run['round']}_{Path(run['protocol']).stem}"
        log_path = sim / f"{stem}.log.json"
        if not log_path.exists():
            continue
        log = json.loads(log_path.read_text())
        reservoir_names = {lw["key"] for lw in contents["labware"] if lw["format"].startswith("reservoir")}
        state = replay(log, reservoir_names)

        deck = deck_of.get((str(run["round"]), run["protocol"]), {})
        node = "ot2_patrick" if run["robot"] == "OT-2" else "otflex_sandy"
        cards = []
        for key, lw in sorted(state.items()):
            load_name, slot = key.split("|")
            coord = OT2_SLOT_COORD.get(slot, slot) if run["robot"] == "OT-2" else slot
            plate_id = deck.get(coord)
            start = start_by_plate.get(plate_id) or start_by_key.get(f"{node}:{coord}")
            is_res = "reservoir" in load_name
            cards.append({
                "slot": slot if slot == coord else f"{slot} ({coord})", "load_name": load_name,
                "name": plate_names.get(plate_id) or (start or {}).get("label") or load_name,
                "is_tips": lw["is_tips"], "tips": lw["tips"], "pickups": lw["pickups"],
                "tip_wells": lw["tip_wells"],
                "rows": 1 if is_res else 8, "cols": 12,
                "start": (start or {}).get("wells", {}),
                "wells": {w: {"in": round(v["in"], 1), "out": round(v["out"], 1),
                              "net": round(v["in"] - v["out"], 1), "touched": v["touched"]}
                          for w, v in lw["wells"].items()},
            })

        commands = [{"k": c["kind"], "v": c["volume"], "w": c["well"], "s": c["slot"],
                     "t": c["text"][:160]} for c in log if c["kind"] != "configure"]
        page = {"version": a.version, "round": run["round"], "protocol": run["protocol"],
                "robot": run["robot"], "cards": cards, "commands": commands,
                "reagents": contents["reagents"],
                "counts": {"commands": len(commands),
                           "tips": sum(c["tips"] for c in cards),
                           "wells": sum(len(c["wells"]) for c in cards if not c["is_tips"])}}
        html = template.replace("/*__RUN__*/null",
                                json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
        (out_dir / f"{stem}.html").write_text(html)
        index.append({"key": stem, "round": run["round"], "protocol": run["protocol"],
                      "robot": run["robot"], "tips": page["counts"]["tips"]})
        written += 1

    (out_dir / "index.json").write_text(json.dumps(index, indent=1))
    print(f"wrote {written} liquid pages to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
