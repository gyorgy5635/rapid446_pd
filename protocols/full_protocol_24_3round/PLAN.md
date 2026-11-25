# 3-round PD run: plan and status

Status: **draft, not run on any robot.** Started 2026-11-24 as a variant of `full_protocol_24_20261124`
(SYBR Green removed, controls routed rack → OT-2). Run map: `./build.sh full_protocol_24_3round`, then open
`viz/pd_run_map.html`. Estimated 28.5 h for 3 rounds (durations are estimates).

## What changes compared with the single run

1. **Three rounds** of Golden Gate → PCR → dilution → cell-free → FDGlu, one after the other. Each round gets its own
   combinations from the design server (closed loop), with the Hidex result of the previous round uploaded first.
2. **Fragments plate is shared by all rounds.** Fragment sources in columns 1-5, GG master mix in column 9 (3x volume),
   PCR master mix in column 10 / 11 / 12 for round 1 / 2 / 3.
3. **Fragments plate lives sealed on a new external cooling block** next to the peeler. Each round it is peeled, used
   on the OT-2 (GG) and the Flex (PCR master mix), resealed and returned to the block, before the 3 h PCR program
   starts (nothing else can run during PCR).
4. **1:50 PCR dilution on the OT-2 only**: 98 µL water (5 × 19.6 µL, 20 µL tips) then 2 µL PCR, mixed at 20 µL.
   The Flex dilution step is gone.
5. **One plate type**: every PCR plate is the Opentrons 200 µL tough plate, so a plate keeps the same labware
   definition wherever it goes (the single run mixed NEST 100 µL and Opentrons 200 µL for the same plate).
6. **Cell-free on lyophilized plates**: three plates (one per round) at room temperature, reagents in columns 1-4.
   On the Flex: 24 µL water, then per column mix the diluted PCR, add 6 µL, mix 5 × 20 µL slowly
   (30 µL total, 250x final dilution of the PCR product). RMF/mix A/mix B steps are gone.
7. **Tips are counted across runs**, no manual tip-box swaps (see Tip plan). Separate 50 µL boxes for single-tip
   and 8-channel work on the Flex.
8. **More nests**: one plate per type and round on rack 1, plus one added nest for the controls plate.

## Run order (one round)

| Stage | Steps |
|---|---|
| Golden Gate | fragments: cold block → peel → OT-2 C1 · GG plate Rn → OT-2 C3 · OT-2 GG (mix col 9 + fragments) · seal GG → thermocycler · 1 h |
| PCR | GG plate: thermocycler → peel → OT-2 C3 · fragments OT-2 → Flex B1 · PCR plate Rn → Flex C1 · Flex PCR master mix (col 9+n) · PCR plate → OT-2 C1 · OT-2 water + GG → PCR · seal PCR → thermocycler (lid closed, not started) · fragments Flex → seal → cold block · GG plate → its nest · **PCR program 3 h** |
| Dilute | PCR plate: thermocycler → peel → OT-2 C1 · dilution plate Rn → OT-2 C3 · controls → OT-2 D1 · OT-2 1:50 dilution · PCR plate → reseal → its nest |
| Cell-free | diluted plate OT-2 → Flex C1 · cell-free plate Rn → Flex B2 · Flex rehydrate + 6 µL template · diluted plate → its nest · cell-free plate → seal → Flex heater-shaker D1, 150 min 37 °C |
| FDGlu | controls OT-2 → Flex B1 · FDGlu plate Rn → Flex B3 · cell-free plate D1 → peel → B2 · Flex FDGlu setup · FDGlu plate → Hidex, read, upload |
| Cleanup | FDGlu plate Hidex → its nest · cell-free plate → its nest · controls → its nest |

Temperature modules are switched on once at the start and off after round 3.

## Plates and nests

| Location | Holds |
|---|---|
| `cold_block_ext` (TODO real name) | Fragments plate, sealed, all rounds |
| `rack2_row1_nest1` | Controls plate, reused every round (rack2 is the second 5 × 3 nest rack) |
| `rack2_row1_nest2` | Full spare OT-2 20 µL tip box, for the slot 3 swap |
| `rack2_row2_nest1` | Left empty: the spent slot 3 tip box is parked here |
| `rack1_row1_nest{n}` | Golden Gate plate, round n |
| `rack1_row2_nest{n}` | PCR plate, round n |
| `rack1_row3_nest{n}` | Dilution plate, round n |
| `rack1_row4_nest{n}` | Lyophilized cell-free plate, round n |
| `rack1_row5_nest{n}` | FDGlu assay plate, round n |

Every used plate goes back to the nest it came from, so nothing collides between rounds. Rack 1 is full (15 nests);
rack 2 holds the controls plate in row 1 nest 1 and has 14 free nests for spares or a fourth round.

## Deck layouts

**OT-2** (numbered slots in brackets): C1 (4) and C3 (6) cold blocks, D1 (1) controls plate during the dilution
only, A1 (10) reservoir, A3 (12) trash. 20 µL tips on C2, B1, B2, B3, A2 (5 fixed racks) and D3 (3).

**D2 (2) must stay empty.** The PF400 cannot place into slot 1 while slot 2 is occupied, and the controls plate
goes into slot 1 every round. Of the tip slots only D3 is reachable by the arm, so it is last in the rack order and
is the one that gets swapped: when it runs out, `ot2_tip_swap.yaml` parks the spent box on `rack2_row2_nest1` and
brings the full spare from `rack2_row1_nest2`. This is a physical constraint the Opentrons simulator cannot see —
it simulated the old deck, with tips in slot 2, quite happily.

**Flex**: A1 200 µL tips, A2 50 µL tips (8-channel), A3 50 µL tips (single-tip only), B1 cold block, C1 cold block,
B2 cell-free plate, B3 FDGlu plate, D1 heater-shaker, D2 reservoir, D3 waste chute, A4 PF400 handoff,
staging **B4 + C4 spare 50 µL boxes, D4 spare 200 µL box**.

Only A1-A3 hold tip boxes: the simulator rejects a box in C2 or C3, because with a single-tip (partial nozzle)
configuration the pipette would collide with it on the way to B2/B3 (`PartialTipMovementNotAllowedError`). Spares
therefore wait in staging, and `flex_tips_swap.py` has the gripper drop the empty box down the waste chute and put
the spare in its place, between protocol runs.

## Tip plan (24 combinations per round)

Counted by the simulator over the whole 3-round run (24 combinations), not estimated:

| Tips | Per round | 3 rounds | Boxes | Margin |
|---|---|---|---|---|
| OT-2 20 µL | 208 tips (GG 120, PCR 48, dilution 40) | 624 tips | 5 fixed racks (480) + 2 boxes in slot 3 | 48 tips |
| Flex 200 µL (A1) | 32 tips (PCR mix 24, FDGlu 8) | 96 tips | exactly 1 box; spare on D4 unused | 0 |
| Flex 50 µL 8-channel (A2) | 72 tips (cell-free 40, FDGlu 32) | 216 tips | 1 on deck + 2 spares, 2 gripper swaps | 72 tips |
| Flex 50 µL single (A3) | 6 tips (FDGlu) | 18 tips | 1 box | 78 tips |

The OT-2 needs **one** PF400 tip-box swap, in round 3 before the PCR step: the five fixed racks and the first
slot-3 box cover 576 tips, and the run needs 624. On the Flex the 8-channel 50 µL box is swapped twice by the
gripper (rounds 2 and 3). The 200 µL box comes out exactly full at 96 tips, so the D4 spare is there for the case
where a round has more combinations.

Swaps are decided at run time by the tip counter, so the run map draws every swap that *could* happen (marked
"only if needed") and does not apply them to the tracked deck. That is why it shows 386 steps and about 30.8 h,
against 1 OT-2 and 2 Flex swaps actually firing. `full_run.py` counts tips (`TipLedger` in `helper_functions.py`) and passes the first unused tip into each
protocol (`$ot2_tip_start`, `$flex200_tip_start`, `$flex50_tip_start`, `$flex50_single_start`). If a 200 µL step would
run past the A1 box, the Flex gripper swaps in the B4 spare (`flex_tips_200_swap.py`, A1 → C4, B4 → A1; no PF400).
If any other box would run out, the run stops with an error instead of crashing a pipette.

## Protocol changes

| File | Change |
|---|---|
| `pd_golden_gate_ot2_v2.py` | GG mix from column 9 (`master_mix_start_well` 64). Tips from the counter across 7 racks. |
| `pd_pcr_v2_flex.py` | PCR mix column from the round (`$pcr_mm_start_well` = 72/80/88). 200 µL start tip from the counter. |
| `pd_pcr_v2_ot2.py` | Tips from the counter (was a fixed start at A4 of D3). |
| `pd_dilute_1to50_ot2.py` | **New.** 98 µL water (5 × 19.6, one tip column, dispensed at the top), 2 µL PCR, mix 5 × 20 µL; controls column as before. |
| `cell_free_lyo_flex.py` | **New.** 24 µL water to columns 1-4 (one tip column, at the top), per column: premix diluted PCR 3 × 20 µL, add 6 µL, mix 5 × 20 µL at 20% speed. |
| `pd_fdglu_flex_v2.py` | Single tips from the A3 box (front to back), 8-channel tips across A2/C2/C3, 200 µL from the counter. RMF removal volume 30 µL (was 27.6). |
| all protocols | Every PCR plate is now `opentrons_96_wellplate_200ul_pcr_full_skirt` (Opentrons tough plate). The FDGlu assay plate stays `corning_96_wellplate_360ul_flat` (flat bottom, for the Hidex read) and the reservoirs stay `nest_12_reservoir_15ml`. |
| `flex_tips_200_swap.py`, `pcr_B2_to_A4.py` | **New** Flex gripper moves. |
| `helper_functions.py` | `TipLedger`, `combination_counts`, round/tip variables passed into protocols. |
| `workflows/transfers/*.yaml`, `rounds/*_r{1,2,3}.yaml` | New transfers for the cold block, resealing, returning plates; one file per round where the nest differs. |

## Simulation (real Opentrons simulator)

`tools/simulate_protocols.py` renders every protocol exactly as `full_run.py` would for all 3 rounds (combinations
from `incoming/combinations_oracle_1008.json`, the round's master-mix column, the tip start positions) and runs the
Opentrons simulator on each, then reports tips and liquid from the command log. Two virtualenvs are needed, because
the Flex needs a recent opentrons and OT-2 support was dropped after 9.x:

    python3 -m venv /tmp/otenv  && /tmp/otenv/bin/pip  install opentrons
    python3 -m venv /tmp/ot2env && /tmp/ot2env/bin/pip install 'opentrons==8.8.2'
    python3 -I tools/simulate_protocols.py --version full_protocol_24_3round \
        --flex-python /tmp/otenv/bin/python --ot2-python /tmp/ot2env/bin/python

Current result: **20/20 runs simulate, no overfilled well, no tip box run dry.** The fullest well in any run is the
FDGlu plate at 140 µL of 360 µL. It found two real errors, both now fixed: tip boxes in C2/C3 collided with
single-tip moves (see the Flex layout), and the GG and PCR plates disagreed about labware.

### Reagents to load (simulator totals for 3 rounds, before dead volume)

| Reservoir | Well | Total |
|---|---|---|
| OT-2 slot A1 | A1 (water) | 8.5 mL |
| Flex D2 | A1 (water, cell-free) | 2.3 mL |
| Flex D2 | A6 (FDGlu substrate) | 9.6 mL |
| Flex D2 | A12 | receives the removed RMF |

A 12-well reservoir holds 15 mL per well, so each fits, but the FDGlu well at 9.6 mL has the least room to spare.

## Starting labware contents

`config/contents.json` records what is loaded by hand before the run, and the player draws it as a
well map per labware:

| Labware | Filled at the start |
|---|---|
| Fragments plate | columns 1-8 fragment stocks, column 9 Golden Gate mix (3x volume), columns 10/11/12 PCR mix for rounds 1/2/3 |
| Controls plate | column 1 (into the dilution plate) and wells 22-24 (into the FDGlu plate), every round |
| Cell-free plates | columns 1-4, lyophilized, room temperature (one plate per round) |
| OT-2 reservoir, slot 10 | A1 water |
| Flex reservoir, D2 | A1 water, A6 FDGlu substrate, A12 empty and receives the removed RMF |

Everything else starts empty and is listed in `empty_at_start`, so the extractor can warn when a
plate is neither described nor declared empty.

## Checks the run map now does

`./build.sh` follows the round loop (3 iterations) and tracks every plate. For this version (it has `config/deck.json`)
it also compares, at every pipetting step, the plates the protocol declares with the plates on that deck:
missing plate, wrong plate, a plate the protocol does not know about (**collision risk**), a plate on a tip-rack or
reservoir slot, and the same plate declared as different labware in different protocols. Tested by breaking the
script on purpose (forgot controls, left fragments on the Flex, never emptied the Hidex): all three were caught.

Current result: **no warnings**: no movement conflicts, no deck conflicts, no labware mismatches.

## Confirmed by the user (2026-11-25)

- The Opentrons tough plate (catalog **991-00076**) has run the `_24` protocol for more than 8 rounds. The existing
  `set_offset` values and the PF400 grip attributes work with it, so neither needed changing; only the plate
  resource's catalog number and description in `full_run.py` were wrong and are now fixed.
- `cold_block_ext` stays as the location name for now.
- Rack 2's nests are named like rack 1's: `rack2_row1_nest1`, which is what the workflows already use.
- The single-run variant `full_protocol_24_20261124` is ported to the tough plate as well. The baseline
  `full_protocol_24` keeps its `protocol/` untouched: it is a working copy used in previous runs.
- The lyophilized cell-free plates are tough plates too, so every plate in this run is the same labware.

## Assumptions I made (please confirm or correct)

1. Cold block and new nest are reached through the exchange's narrow side, like the rack and peeler.
2. Cell-free assembly happens on Flex B2 at room temperature; the diluted PCR waits on the cold block C1.
3. PCR plate is resealed before going back to its nest; GG, dilution, cell-free and FDGlu plates go back unsealed.
4. Controls plate: same wells every round (column 1 for the dilution, F3-H3 for FDGlu), so it needs 3x volume.
5. Dilution plate controls column: 20 µL undiluted controls, as in the single run.
6. Round 2 and 3 combinations come from `collect_combinations(oracle_id=<id returned by the previous upload>)`;
   round 1 uses 1008 as before. The REST module is not in this repo, so this is unverified.
7. "Verify combinations" pause only before round 1, so rounds 2-3 run unattended.
8. Temperature modules stay on for the whole run (the single run switched OT-2 and Flex C1 off before the cell-free
   incubation).
9. At most 24 combinations per round; more stops the run (cell-free plates have 3 sample columns + controls).
10. Mixing: diluted PCR premix 3 × 20 µL; reaction mix 5 × 20 µL at 20% flow; dilution mix 5 × 20 µL.

## Open items before a real run

- [ ] **MADSci**: create the cooling-block location and teach the PF400; replace the placeholder name
      `cold_block_ext` (in `workflows/transfers/*.yaml`, `full_run.py`, `config/`). Confirm rack 2's nests are named
      like rack 1 (`rack2_row1_nest1`), which is what the workflows assume.
- [ ] **Offsets for the new tip slots**: the plate offsets are unchanged and proven, but a labware position check is
      still needed for OT-2 tips on D2, C2, B1, B2, B3, A2 and Flex tips on A3 (and the staging spares B4, C4, D4).
- [ ] **OT-2 trash**: about 620 used 20 µL tips over 3 rounds. Check that the OT-2 trash bin holds that many.
- [ ] **Reagent volumes**: load at least the simulator totals above plus dead volume. On the fragments plate the
      simulator draws 108 µL per well from GG mix column 9 and 72 µL per well from each PCR mix column.
- [ ] Durations are estimates; real timings need `tools/export_madsci_history.py` on the lab network.
