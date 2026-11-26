# full_protocol_24_3round_20261126

A frozen copy of the 3-round protein design run, taken on 2026-11-26 so that further variants can be
built without disturbing it. `protocol/` is byte-identical to `full_protocol_24_3round` as it stood
that day, and the run map matches it step for step.

**Status: draft. No part of this has been run on the robots.** The protocol is frozen as of
2026-11-26; the only later change is the thermocycler PCR duration in `config/durations.json`,
corrected on 2026-11-26 from 1.5 h to 2.75 h, which is a measurement of the instrument rather than
a design choice. It has been checked by simulation
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

## Labware that stays out at room temperature

Three pieces of labware sit at room temperature for long stretches. None of this is accidental, but
it is the part of the design most worth a second opinion from someone who knows the chemistry.

- **The controls plate lives on rack 2, nest 1, at room temperature.** It has no cooled home: it
  waits there between rounds, moves to OT-2 slot 1 (an ordinary slot, not a cold block) for the
  dilution, and only reaches a cooled surface when it arrives on the Flex cold block B1 for the
  FDGlu assay. By the run map's estimates it spends about **3.5 h uncooled per round**, covering the
  dilution, the cell-free assembly and the 150 min incubation. The single-run protocol parked it on
  the Flex cold block instead; that detour was dropped when the Flex stopped using it.
- **The lyophilized cell-free plates** are stored and used at room temperature, as intended for
  lyophilized reagents.
- **The reagent reservoirs** on both robots are at room temperature for the whole run, including the
  FDGlu substrate (9.6 mL drawn over the three rounds).

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
