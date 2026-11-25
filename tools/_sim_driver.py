#!/usr/bin/env python3
"""Run one Opentrons protocol in the simulator and print its command log as JSON.

Runs *inside* a virtualenv that has the opentrons package (see tools/simulate_protocols.py, which
calls this). Kept separate so the repo itself never imports opentrons, and so the Flex and the
OT-2 can use different opentrons versions.

The run log has no machine-readable command type, so commands are classified by the text the
simulator prints; everything else (pipette channels, well, labware, volume) comes from the
objects in the payload. The channel count is what turns "picked up a tip" into "used 8 tips".

Each entry's nesting level is kept too: a mix() or a transfer() prints its own aspirate and
dispense commands one level deeper, and those move no net liquid, so a reader has to tell them
from the real ones.
"""
import json
import sys

from opentrons import simulate

KINDS = (("Configure pipette", "configure"), ("Picking up tip", "pick_up_tip"), ("Aspirating", "aspirate"), ("Dispensing", "dispense"),
         ("Dropping tip", "drop_tip"), ("Mixing", "mix"), ("Transferring", "transfer"),
         ("Moving", "move_labware"), ("Delaying", "delay"), ("Touching tip", "touch_tip"),
         ("Blowing out", "blow_out"))


def kind_of(text):
    stripped = text.strip()
    for prefix, kind in KINDS:
        if stripped.startswith(prefix):
            return kind
    return "other"


def describe(location):
    """(well, labware load name, deck slot) for a Well, or a Location wrapping one."""
    well = location
    labware_like = getattr(location, "labware", None)   # aspirate/dispense pass a types.Location
    if labware_like is not None and hasattr(labware_like, "as_well"):
        well = labware_like.as_well()
    name = getattr(well, "well_name", None)
    labware = getattr(well, "parent", None)
    load_name = getattr(labware, "load_name", None)
    # labware.parent is the deck slot, or the adapter/module it sits on; walk up to the slot.
    parent = getattr(labware, "parent", None)
    for _ in range(4):
        if parent is None or isinstance(parent, str):
            break
        parent = getattr(parent, "parent", None)
    return name, load_name, (str(parent) if parent is not None else None)


def main():
    # argv[2] is an output path, not stdout: protocols print() their own progress to stdout.
    path, out_path = sys.argv[1], sys.argv[2]
    with open(path) as fh:
        run_log, _bundle = simulate.simulate(fh, path)

    out = []
    for entry in run_log:
        payload = entry.get("payload", {})
        text = payload.get("text", "") or ""
        instrument = payload.get("instrument")
        location = payload.get("location")
        well = labware = slot = None
        if location is not None:
            try:
                well, labware, slot = describe(location)
            except Exception:  # noqa: BLE001 - a log entry must never break the report
                pass
        out.append({
            "kind": kind_of(text),
            "level": entry.get("level", 0),
            "style": str(payload.get("style") or "") or None,   # nozzle layout: SINGLE, COLUMN, ALL...
            "mount": str(getattr(instrument, "mount", "") or "") or None,
            "text": text.strip(),
            "volume": payload.get("volume"),
            "channels": getattr(instrument, "channels", None),
            "pipette": getattr(instrument, "name", None),
            "well": well,
            "labware": labware,
            "slot": slot,
        })
    with open(out_path, "w") as fh:
        json.dump(out, fh)


if __name__ == "__main__":
    main()
