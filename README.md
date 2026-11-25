# PD workflow run map (prototype)

Animated, top-down view of labware movement for MADSci protein design protocols, generated
from the code. Each protocol version lives in its own folder under `protocols/`.

    ./build.sh                       # build every version
    ./build.sh full_protocol_24      # build one
    firefox protocols/full_protocol_24/viz/pd_run_map.html

## Layout of this folder
    tools/  tests/                   shared code (one copy for all versions)
    protocols/<version>/
      protocol/                      what goes to GitHub: src/full_run.py, workflows/, protocols/
      config/                        plates.json, layout.json, durations.json, source.json
      viz/                           generated: events.json, pd_run_map.html (+ madsci_history.json)
    incoming/                        material from the team (slides, readme)

`protocols/full_protocol_24` is the baseline: an unmodified copy of
AD-SDL/rapid446_applications `Protein_Design/full_protocol_24` at commit `e4bc261`
(branch `PD_full_loop`, 2026-11-11). Its source links point at that commit.

## Making a new protocol version
    ./new_version.sh full_protocol_24 full_protocol_24_v2 "24 samples, shorter PCR"
    # edit protocols/full_protocol_24_v2/protocol/...  (yaml, py)
    ./build.sh full_protocol_24_v2
    diff -ru protocols/full_protocol_24/protocol protocols/full_protocol_24_v2/protocol

The copy gets its own config, map and checks. Its `source.json` records `derived_from` and the
base commit and has no GitHub link until it is pushed. To publish it, copy its `protocol/`
contents into a new folder (or branch) in the GitHub repo, then put the repo, branch, commit and
`repo_blob_url` into `source.json` so the map links to the right lines.

## Playback
- Every step gets the same screen time (about 1.3 s at 1x). Real durations range from seconds to
  hours, so the step panel shows them as text instead.
- The PF400 runs on a linear rail. For each move the carriage slides to the plate, the arm reaches out,
  grips, carries the plate, and folds back home.
- Jaws on the plate show the grip side. `exchange_narrow` and `exchange_wide` are the same nest; the
  name says which side the arm grips. A plate placed wide and picked up narrow is shown as a re-grip.
- Link to a specific step with `pd_run_map.html#step-42`.

## Measured timings from MADSci
1. On a machine that can reach the workcell manager (standard library only, no MADSci install needed):

       python3 tools/export_madsci_history.py --workcell-url http://<workcell-host>:8005/ \
           --number 500 --out madsci_history.json

   Use the workcell manager URL (`WORKCELL_SERVER_URL`, default port 8005), not the lab server (port 8000).
   The script lists the experiment ids it found. Add `--experiment-id <id>` to keep only specific runs.
2. Copy the file to `protocols/<version>/viz/madsci_history.json` and run `./build.sh <version>`.

The importer groups workflows by `ownership_info.experiment_id`, skips failed and cancelled workflows,
and lines each run up against the script's workflow sequence. Runs where fewer than half of the
calls match are not used. Each step gets the median `end_time - start_time` across the runs used.
Idle time between workflows is assigned to the manual `input()` pause when one sits there, and
otherwise is shown as waiting time. Steps with no match keep their estimate, and the player labels
every duration as measured, from code, or estimate.
`tests/make_synthetic_history.py` produces a fake export for testing. Never copy its output into `viz/`.

## Deck setup by phase
Under the map there is one OT-2 + Flex picture per phase, generated from the tracked state.
Solid plates are on the deck when the phase starts. Dashed plates are brought in during the phase,
drawn in the slot where they are used (past the A4 handoff when they go further). Each card has an **Export PNG** button (2x resolution, with a title band, always in the light theme) and lists
the liquid-handling protocols, what is brought in, and what leaves the deck. Select a card to jump the map to that phase.

## Locations
The Locations panel lists every MADSci location named in the workflow files, grouped by instrument.
It shows what each one holds at the current step and how many moves use it. `otflex_sandy.deck_nest_A4`
is the Flex handoff: it is the only Flex slot the PF400 serves (the extractor warns if a workflow breaks
this). The Flex gripper moves plates between A4 and the other deck slots.

## How it works
1. `tools/extract_events.py` parses `protocols/<version>/protocol/src/full_run.py` with Python's AST (never runs it).
   Each `submit_workflow()` is expanded into its YAML steps. `pf400_piper transfer` steps and the
   Flex gripper protocols named `pcr_<SRC>_to_<DST>.py` become moves. Every plate is tracked
   from where `push_new_assay_plate_resource()` first registers it. Each move is checked to make
   sure the source holds a plate and the destination is free.
   `for x in (1, 2, 3)` / `for x in range(n)` loops are unrolled (phases are prefixed `R1 ·`, `R2 ·` when the
   variable name contains "round"), f-string workflow paths are resolved, `if` tests on loop variables are
   evaluated, and other `if` blocks are shown with their steps marked "(only if needed)".
   If the version has `config/deck.json`, every pipetting protocol is also compared with the tracked deck:
   missing or wrong plates, plates the protocol does not know about (collision risk), plates on tip-rack or
   reservoir slots, and one plate declared as different labware in different protocols.
2. `tools/build_player.py` embeds the event log and layout into `tools/player_template.html`.

## What you edit
| File | What it controls |
|---|---|
All paths below are inside `protocols/<version>/`.

| `config/plates.json`    | labware names, short labels, colors (keyed by starting location) |
| `config/layout.json`    | instrument positions (from incoming/PD.arrangement.pptx; OT-2 below the rail under the Hidex, nests to its right), deck fixtures, location aliases (`exchange_narrow`/`wide` -> `exchange`) |
| `config/durations.json` | duration estimates; `protocol.delay()` calls found in protocols are added automatically |
| `config/source.json`    | name and title shown in the player, repo/branch/commit, link base for source lines |
| `config/deck.json`      | optional: maps PF400 locations to Opentrons deck slots and turns on the deck check |

To change the layout, use **Edit layout** in the player: drag the instruments, click
**Copy layout JSON**, paste the result into `config/layout.json`, then run `./build.sh`.

## Updating the baseline from the repo
`protocols/full_protocol_24/protocol/` is a plain copy of `Protein_Design/full_protocol_24`
(src/, workflows/, protocols/). Refresh it from the repo, update `commit` and `repo_blob_url`
in its `source.json`, then run `./build.sh full_protocol_24`.

## Known limits
- Durations are placeholders until a MADSci history export is added, except the 150 min CFPS
  incubation (from `pcr_A4_to_D1.py`).
- Manual steps appear only where the script has `input()`. Steps people do by hand
  (adding master mix, etc.) are not in the code.
- Loops other than constant `for` loops (while, for over a variable) are expanded once, with a warning.
- The deck check reads protocol files with the AST; it does not simulate them (use `opentrons_simulate` for that).
