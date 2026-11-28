# full_protocol_24_3round_20261126

A frozen copy of the 3-round protein design run, taken on 2026-11-26 so that further variants can be
built without disturbing it. `protocol/` is byte-identical to `full_protocol_24_3round` as it stood
that day, and the run map matches it step for step.

It has been refreshed twice since, each time to take in a change worth keeping rather than to
record a design that had been superseded:

- **Controls kept cold** (2026-11-26). The first version left that plate on a room-temperature
  nest. It holds PCR products and protein that keep better cold, and it is unsealed, so it would
  dry out; it now lives on the Flex cold block.
- **Cell-free water tips reused** (2026-11-27). The water step dispenses from above the wells and
  never touches the cake, so its tips are clean and now carry on into the first template column.
  That takes the step from 5 tip columns to 4, which fits 24 columns into exactly two 50 µL boxes:
  one gripper swap instead of two, and none of the 48 tips that used to go out in part-full boxes.
- **One tip column per master mix, laid down slowly** (2026-11-27). Golden Gate and the Flex PCR
  step each used a fresh tip column per destination column; the destinations are empty at that
  point and all take the same mix from the same well, so one column now serves all three. Both are
  also slowed, 3 µL/s on the OT-2 and 150 µL/s on the Flex, because the mixes are viscous. Tips
  over the run fall to 834 and the OT-2 needs no tip-box swap at all.

**Status: draft. No part of this has been run on the robots.** It has been checked by simulation
and by the run map; see "What has been checked" below.

Open `viz/pd_run_map.html` for the run, and `viz/liquid/` for the liquid handling of each protocol.
`PLAN.md` holds the full detail: run order, deck layouts, tip budget, assumptions and open items.

## What this variant is

Three rounds of Golden Gate → PCR → 1:50 dilution → cell-free → FDGlu, one after another, about
34.5 h by the current estimates (the thermocycler PCR program is 2.5-3 h; 2.75 h is used here). Each round fetches its own combination list from the design server
after uploading the previous round's Hidex read.

What distinguishes it from the single run it grew out of:

- **Three rounds** from one set of reagents, with the fragments plate shared by all of them: Golden
  Gate mix in column 9 at 3x volume, PCR mix in columns 10, 11 and 12, one per round.
- **The fragments plate lives sealed on an external cooling block** next to the peeler. Each round
  it is peeled, used, resealed and returned, all before the 3 h PCR program starts, because nothing
  else can run during PCR.
- **The 1:50 dilution happens entirely on the OT-2**: 98 µL of water in 5 × 19.6 µL (20 µL tips),
  then 2 µL of PCR product, mixed at 20 µL.
- **Cell-free uses lyophilized plates**, one per round, reagents already in columns 1-4. They are
  rehydrated on the Flex with 24 µL of water, then 6 µL of diluted PCR, mixed slowly.
- **SYBR Green is gone**, together with the Hidex read that went with it.
- **Every plate is the Opentrons tough plate** (991-00076). Only the FDGlu assay plate is different:
  a Corning flat bottom, because it is read in the Hidex.

## How the controls plate is kept cold

The controls plate holds PCR products and protein, so it wants to be cold, and it is unsealed, so it
would dry out if it stood about. It therefore **lives on the Flex cold block B1 for the whole run**
rather than on a nest, and leaves only twice a round:

| Where | Time over the 34.5 h run | |
|---|---|---|
| Flex cold block B1 | **25.9 h** | cold |
| Staging D4 | 3.2 h | parked while the fragments plate needs B1 |
| OT-2 slot 1 | 1.1 h | the three dilutions |
| Its own nest | 0.4 h | the start and the end of the run |

Two gripper moves per round do the toggling: B1 → D4 before the fragments plate arrives for the PCR
master mix, and D4 → B1 once it has gone. The cost is nine extra gripper moves and the staging slot
that used to hold a spare 200 µL tip box, so the Flex 200 µL budget now has no margin: the run draws
exactly one box of 96 tips.

**Still at room temperature**, both deliberately:

- **The lyophilized cell-free plates**, as intended for lyophilized reagents.
- **The reagent reservoirs** on both robots, including the FDGlu substrate (9.6 mL over three
  rounds).

Sealing the controls plate would close the remaining gap - it is open whenever it is not in use, as
the run map's hover text shows - but that needs somewhere sealed and cold to keep it, which is the
second external cold block that does not exist yet.

The fragments plate is the opposite case: it is sealed and on the external cooling block whenever it
is not in use, which is what the external block was added for.

## What has been checked

- **The Opentrons simulator** runs all 20 protocol runs of the three rounds: no well over capacity,
  no tip box run dry, and every volume traceable to a declared reagent.
- **The run map** tracks every plate through 386 steps with no movement or deck conflict, and knows
  which of the run-time tip swaps actually fire (one on the OT-2 in round 3, two on the Flex in
  rounds 2 and 3).
- **Not checked:** nothing has run on the robots, the durations are estimates, and the labware
  position checks listed in `PLAN.md` are still outstanding - the move to the tough plate changed
  the declared well depth of every plate.

## Reproducing the pages

```
./build.sh full_protocol_24_3round_20261126          # run map from the protocol source
python3 -I tools/simulate_protocols.py --version full_protocol_24_3round_20261126 \
    --flex-python /tmp/otenv/bin/python --ot2-python /tmp/ot2env/bin/python
./build.sh full_protocol_24_3round_20261126          # again, so the liquid pages and real swaps appear
```

`viz/` is generated; do not hand-edit it. The repository README explains the two virtualenvs the
simulator needs.
