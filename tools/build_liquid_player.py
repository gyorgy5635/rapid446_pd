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


def take(comp, pure, volume, short_note=None):
    """Remove `volume` from a well, proportionally to what is in it; return what came out.

    A well whose starting volume contents.json gives is finite: drawing more than it holds is a
    real shortfall and is recorded, not quietly topped up. A well that is declared without a volume
    is a stock of unknown size, so the remainder comes from that reagent. A well nothing declares
    at all yields "unknown".
    """
    out, total = {}, sum(comp.values())
    if total > 1e-9:
        frac = min(1.0, volume / total)
        for r, v in list(comp.items()):
            moved = v * frac
            out[r] = out.get(r, 0.0) + moved
            comp[r] = v - moved
            if comp[r] < 1e-9:
                del comp[r]
    short = volume - sum(out.values())
    if short > 1e-9:
        if short_note is not None:
            # a well of known volume that has nothing left: the pipette takes air, and the caller
            # reports the shortfall. "unknown" stays reserved for a gap in contents.json.
            short_note.append(round(short, 1))
            out["air"] = out.get("air", 0.0) + short
        else:
            out[pure or "unknown"] = out.get(pure or "unknown", 0.0) + short
    return out


def timeline(log, lw_state):
    """One entry per command: the wells it touches, the volume each gains or loses, and what that
    liquid is made of.

    lw_state maps a labware key to {"comp": {well: {reagent: uL}}, "pure": {well: reagent},
    "reservoir": bool} and is updated as the run proceeds, so the caller can carry a plate's
    contents into the next run that uses it.

    An 8-channel step is modelled as one payload shared by its channels: each well of a column
    normally holds the same thing, so the mixture carried is their average.
    """
    out, active, carried = [], {}, defaultdict(dict)   # mount -> {channel index: mixture}
    mix_level = None          # inside a mix(): its own aspirate/dispense pairs move nothing
    for cmd in log:
        kind, level = cmd["kind"], cmd.get("level", 0)
        if mix_level is not None and level <= mix_level:
            mix_level = None
        if kind == "configure":
            style = (cmd["style"] or "").upper()
            active[cmd["mount"]] = 1 if "SINGLE" in style else 8 if "COLUMN" in style else (cmd["channels"] or 1)
            continue
        n = active.get(cmd["mount"], cmd["channels"] or 1)
        key = f"{cmd['labware']}|{cmd['slot']}" if cmd["labware"] else None
        entry = {"k": kind, "v": cmd["volume"], "w": cmd["well"], "s": cmd["slot"],
                 "t": cmd["text"][:160], "lw": key}
        if kind == "mix":
            mix_level = level
            entry["wells"] = well_list(cmd["well"], n)
        elif kind == "pick_up_tip":
            entry["tips"] = well_list(cmd["well"], n)
        elif kind in ("aspirate", "dispense") and mix_level is None and key and cmd["volume"] is not None:
            st = lw_state.setdefault(key, {"comp": {}, "pure": {}, "sized": set(),
                                           "reservoir": "reservoir" in cmd["labware"]})
            # Each channel is followed separately: a column is not always uniform (the FDGlu run
            # empties three wells of one column), so averaging the payload would invent liquid.
            chan = [cmd["well"]] * n if st["reservoir"] else well_list(cmd["well"], n)
            wells = [cmd["well"]] if st["reservoir"] else chan
            entry["wells"] = wells
            entry["dv"] = (cmd["volume"] * n if st["reservoir"] else cmd["volume"]) * (1 if kind == "dispense" else -1)
            held = carried[cmd["mount"]]
            moved = defaultdict(dict)      # well -> mixture moved in or out
            if kind == "aspirate":
                held.clear()
                for i, w in enumerate(chan):
                    short = [] if w in st["sized"] else None
                    got = take(st["comp"].setdefault(w, {}), st["pure"].get(w), cmd["volume"], short)
                    held[i] = got
                    for r, v in got.items():
                        moved[w][r] = moved[w].get(r, 0.0) + v
                    if short:
                        entry.setdefault("dry", []).append([w, short[0]])
            else:
                for i, w in enumerate(chan):
                    pay = held.get(i, {})
                    total_held = sum(pay.values())
                    give = {}
                    if total_held > 1e-9:
                        frac = min(1.0, cmd["volume"] / total_held)
                        for r, v in list(pay.items()):
                            give[r] = v * frac
                            pay[r] = v - give[r]
                            if pay[r] < 1e-9:
                                del pay[r]
                    rest = cmd["volume"] - sum(give.values())
                    if rest > 1e-9:
                        give["air"] = give.get("air", 0.0) + rest
                    comp = st["comp"].setdefault(w, {})
                    for r, v in give.items():
                        comp[r] = comp.get(r, 0.0) + v
                        moved[w][r] = moved[w].get(r, 0.0) + v
            entry["comps"] = {w: {r: round(v, 3) for r, v in mix.items() if abs(v) > 1e-6}
                              for w, mix in moved.items()}
        out.append(entry)
    return out


def totals(timeline_):
    """Per-labware well totals and tip use, summed from the timeline."""
    labware = defaultdict(lambda: {"wells": defaultdict(lambda: {"in": 0.0, "out": 0.0, "touched": 0}),
                                   "is_tips": False, "pickups": 0, "tips": 0, "tip_wells": []})
    for e in timeline_:
        if not e.get("lw"):
            continue
        lw = labware[e["lw"]]
        if e.get("tips"):
            lw["is_tips"] = True
            lw["pickups"] += 1
            lw["tips"] += len(e["tips"])
            for w in e["tips"]:
                if w not in lw["tip_wells"]:
                    lw["tip_wells"].append(w)
        if "dv" in e:
            for w in e["wells"]:
                cell = lw["wells"][w]
                cell["in" if e["dv"] > 0 else "out"] += abs(e["dv"])
                cell["touched"] += 1
    return labware


def cards_name(deck, node, slot, run, names):
    """Friendly name of the labware on a deck slot, for a warning line."""
    coord = OT2_SLOT_COORD.get(slot, slot) if run["robot"] == "OT-2" else slot
    return names.get(deck.get(coord))


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
            # "R2 · PCR" -> round 2; a single-run version has no prefix and is round 1
            phase = step["phase"]
            rnd = int(phase[1:].split()[0]) if phase[:1] == "R" and phase[1:2].isdigit() else 1
            deck_of[(rnd, step["protocol"])] = step["deck_plates"]

    out_dir = base / "viz" / "liquid"
    out_dir.mkdir(parents=True, exist_ok=True)
    template = a.template.read_text()
    index, written, unknown, dry, expected, skipped = [], 0, [], [], 0, 0

    # What each plate holds, carried from one run to the next: the dilution run has to see the PCR
    # products the PCR run put there. Keyed by tracked plate id, or by node:slot for a reservoir.
    world, seeded = {}, set()

    def identity(plate_id, node, coord):
        return plate_id or f"{node}:{coord}"

    for run in sorted(report["runs"], key=lambda r: (r["round"], report["runs"].index(r))):
        if not run.get("ok"):
            continue
        stem = f"r{run['round']}_{Path(run['protocol']).stem}"
        log_path = sim / f"{stem}.log.json"
        if not log_path.exists():
            continue
        log = json.loads(log_path.read_text())
        deck = deck_of.get((int(run["round"]), run["protocol"]), {})
        node = "ot2_patrick" if run["robot"] == "OT-2" else "otflex_sandy"

        # hand the labware on this deck whatever it already holds, then let the run change it
        lw_state, ident_of = {}, {}
        for cmd in log:
            if not cmd["labware"] or f"{cmd['labware']}|{cmd['slot']}" in lw_state:
                continue
            key, slot = f"{cmd['labware']}|{cmd['slot']}", cmd["slot"]
            coord = OT2_SLOT_COORD.get(slot, slot) if run["robot"] == "OT-2" else slot
            ident = identity(deck.get(coord), node, coord)
            start = start_by_plate.get(deck.get(coord)) or start_by_key.get(f"{node}:{coord}") or {}
            held = world.setdefault(ident, {})
            declared = start.get("wells") or {}
            if ident not in seeded:          # first run to use this labware: load the stocks
                for w, f in declared.items():
                    if f.get("volume_ul"):
                        held.setdefault(w, {})[f["reagent"]] = float(f["volume_ul"])
                seeded.add(ident)
            # a well is "sized" when we know what it starts with, including known-empty ones: then
            # drawing from it when empty is air, not liquid of unknown origin
            lw_state[key] = {"comp": held,
                             "pure": {w: f["reagent"] for w, f in declared.items()
                                      if f.get("volume_ul") is None},
                             "sized": {w for w, f in declared.items() if f.get("volume_ul") is not None}
                                      | set(start.get("expected_dry") or {}),
                             "reservoir": "reservoir" in cmd["labware"]}
            ident_of[key] = ident
        before = {k: json.loads(json.dumps(v["comp"])) for k, v in lw_state.items()}

        tl = timeline(log, lw_state)
        state = totals(tl)
        for key, st in lw_state.items():
            world[ident_of.get(key, key)] = st["comp"]
        for e in tl:
            if "unknown" in (e.get("comp") or {}):
                unknown.append(f"round {run['round']} {run['protocol']}: {e['t'][:90]}")
            for w, missing in e.get("dry") or []:
                coord = OT2_SLOT_COORD.get(e["s"], e["s"]) if run["robot"] == "OT-2" else e["s"]
                decl = start_by_plate.get(deck.get(coord)) or start_by_key.get(f"{node}:{coord}") or {}
                if w in (decl.get("expected_dry") or {}):
                    expected += 1          # the run draws from this empty well on purpose
                    continue
                dry.append(f"round {run['round']} {run['protocol']}: {w} of "
                           f"{cards_name(deck, node, e['s'], run, plate_names) or e['lw']} "
                           f"is {missing} uL short")
        cards = []
        for key, lw in sorted(state.items()):
            load_name, slot = key.split("|")
            coord = OT2_SLOT_COORD.get(slot, slot) if run["robot"] == "OT-2" else slot
            plate_id = deck.get(coord)
            start = start_by_plate.get(plate_id) or start_by_key.get(f"{node}:{coord}")
            is_res = "reservoir" in load_name
            cards.append({
                "comp0": {w: {r: round(v, 2) for r, v in c.items()}
                          for w, c in (before.get(key) or {}).items() if c},
                "key": key, "slot": slot if slot == coord else f"{slot} ({coord})", "load_name": load_name,
                "name": plate_names.get(plate_id) or (start or {}).get("label") or load_name,
                "is_tips": lw["is_tips"], "tips": lw["tips"], "pickups": lw["pickups"],
                "tip_wells": lw["tip_wells"],
                "rows": 1 if is_res else 8, "cols": 12,
                "start": (start or {}).get("wells", {}),
                "wells": {w: {"in": round(v["in"], 1), "out": round(v["out"], 1),
                              "net": round(v["in"] - v["out"], 1), "touched": v["touched"]}
                          for w, v in lw["wells"].items()},
            })

        if not cards:
            # nothing on the deck to show: a temperature setting or a gripper-only tip swap. No page
            # means the run map shows no link for that step, which is the honest result.
            skipped += 1
            continue
        commands = tl
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
    print(f"wrote {written} liquid pages to {out_dir}"
          + (f" ({skipped} run(s) handle no liquid and get no page)" if skipped else ""))
    if expected:
        print(f"  {expected} air draw(s) from wells contents.json expects to be empty")
    if dry:
        print(f"  {len(dry)} well(s) run dry; first few:")
        for line in dry[:5]:
            print(f"    {line}")
    if unknown:
        print(f"  {len(unknown)} command(s) move liquid of unknown origin; first few:")
        for line in unknown[:5]:
            print(f"    {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
