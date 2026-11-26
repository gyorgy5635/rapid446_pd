import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import random
from typing import Any, ClassVar, Optional, Union
from dotenv import load_dotenv

from madsci.common.types.experiment_types import ExperimentDesign
from madsci.common.types.resource_types import Collection, Resource, Slot

from madsci.experiment_application.experiment_script import ExperimentScript
from madsci.client.resource_client import ResourceClient
from pottery import Redlock

from redis import Redis
from pydantic import AnyUrl

from REST_connection.REST_connect import RESTHandlerPD
import helper_functions


load_dotenv()

# Set up redis for exchange location lock
redis_host = os.getenv("REDIS_HOST")
redis_port = os.getenv("REDIS_PORT")
redis_password = os.getenv("REDIS_PASSWORD")
exchange_auto_unlock_seconds = 86400 # 86400 seconds = 24 hours
exchange_lock_timeout = 7200 # 7200 seconds = 2 hours
exchange_waiters_key = "exchange_waiters"

redis = Redis(
    host=redis_host,
    port=redis_port,
    # password=redis_password,  
)


# TEST PING TO REDIS
try:
    redis.ping()
    print("Sent ping")
except Exception as e:
    print("Redis connection error.", flush=True)
    raise e








class PDApp(ExperimentScript,): # TODO
    """PD Experiment Application

    # TODO:

    """

    experiment_design = ExperimentDesign(
        experiment_name="PD_App",
    )
    # config = ExperimentApplicationConfig(node_url=AnyUrl("http://localhost:6000"))
    # experiment_client = ExperimentClient()
    # workcell_client = WorkcellClient()
    # location_client = LocationClient()
    # resource_client = ResourceClient()
    experiment_id = None
    experiment_label = None
    rest_handler = RESTHandlerPD()

    # def _validate_settings_path(self):
    #     if not os.path.isfile(self.experiment_settings_file):
    #         raise FileNotFoundError(
    #             f"Settings file not found: {self.experiment_settings_file}"
    #         )

    # def __init__(self) -> None:
    #     """Initializes the PD Experiment App"""

    #     super().__init__()
    #     self.init_assay_plate_resource_template()

    # def init_assay_plate_resource_template(self):
    #     """Initializes assay plate resource template"""

    #     self.resource_client.create_template(
    #         resource=Resource(
    #             resource_description="NEST PCR plate 200ul",
    #         ),
    #         template_name="opentrons_96_wellplate_200ul_pcr_full_skirt",
    #         description="Template for 200ul PCR plate",
    #         tags=["Plate", "ANSI/SLAS", "96 Well", "PCR", "Labware"],
    #     )

    #     self.resource_client.create_template(
    #         resource=Resource(
    #             resource_description="ot2 20ul tiprack",
    #         ),
    #         template_name="opentrons_96_filtertiprack_20ul",
    #         description="Template for ot2 20ul tiprack",
    #         tags=["Tiprack", "ANSI/SLAS", "96 Well", "Labware"],
    #     )

    #     self.resource_client.create_template(
    #         resource=Resource(
    #             resource_description="otflex 50ul tiprack",
    #         ),
    #         template_name="opentrons_flex_96_filtertiprack_50ul",
    #         description="Template for OT-Flex 50ul tiprack",
    #         tags=["Tiprack", "ANSI/SLAS", "96 Well", "Labware"],
    #     )

    #     self.resource_client.create_template(
    #         resource=Resource(
    #             resource_description="otflex 200ul tiprack",
    #         ),
    #         template_name="opentrons_flex_96_filtertiprack_200ul",
    #         description="Template for 200ul OT-Flex tiprack",
    #         tags=["Tiprack", "ANSI/SLAS", "96 Well", "Labware"],
    #     )

    #TODO: bandaid for lack of opentrons resources, pop plate as it goes into flex, make a new one when need to grab from staging
    def pop_assay_plate_resource(
            self,
            location_name: str,
        ) -> None | Resource:
            associated_resource_id = self.location_client.get_location_by_name(location_name).resource_id
            resource_object = self.resource_client.get_resource(associated_resource_id)
            popped_plate, updated_parent = self.resource_client.pop(resource=associated_resource_id)
            print(popped_plate)
            popped_resource_id = popped_plate.resource_id
            data = self.resource_client.remove_resource(resource=popped_resource_id)

    def push_new_assay_plate_resource(
            self,
            location_name: str,
            labware_type: str,
        ) -> None | Resource:
            """
            Pushes a new assay plate resource into the specified location, popping an existing plate in that location if necessary.
            """
            # get the resource id of the resource associated with the given location
            associated_resource_id = self.location_client.get_location_by_name(location_name).resource_id
            print("Location name: ", location_name)
            print("ASSC Resource id: ", associated_resource_id)
            # get the resource object from the resource id
            resource_object = self.resource_client.get_resource(associated_resource_id)

            # check if the resource object currently has child resources (a plate already at that location)
            old_plate = None
            if len(resource_object.children) > 0:
                    # there is already a plate at this location
                    self.logger.log_info(f"A plate with ID {resource_object.child.resource_id} already exists at location: {location_name}")

                    # pop the old plate
                    popped_plate, updated_parent = self.resource_client.pop(resource=associated_resource_id)
                    self.logger.log_info(f"Popped plate with ID {resource_object.child.resource_id} from location: {location_name}")
                    old_plate = popped_plate
            
            # # Create a new assay plate resource and push it into the resource object associated with the given location.
            # lid_resource = Resource(
            #     resource_name = f"lid_for_plate_{plate_num}_expID_{experiment_id}",
            #     attributes={
            #         "lid": True
            #     }
            # )
            if labware_type == "pcr":
                new_plate = Collection(
                    # resource_id="01KT9Q9MJF3WPYQT6TBZ9QPQ5J",
                    resource_name="Z_PCR_CORRECT_ATTRIBUTES_PLATE_2",
                    resource_class="Microplate",
                    attributes={
                        # Common attributes
                        "plate_height": 14, 
                        "description": "Opentrons Tough 96 Well Plate 200 uL PCR Full Skirt",
                        "catalog_number": "991-00076",

                        # PF400 specific attributes
                        "pf400_grip_height": 6,

                        # SciClops specific attributes
                        "sciclops_grip_height": 1,
                    },
                )
            
            elif labware_type == "ot2_tiprack":
                 new_plate = Collection(
                    # resource_id="01KT9Q9MJF3WPYQT6TBZ9QPQ5J",
                    resource_name="Z_PCR_CORRECT_ATTRIBUTES_PLATE_2",
                    resource_class="Microplate",
                    attributes={
                        # Common attributes
                        "plate_height": 64, 
                        "description": "Opentrons OT-2 Tiprack",

                        # PF400 specific attributes
                        "pf400_grip_height": 23,

                        # SciClops specific attributes
                        "sciclops_grip_height": 23,
                    },
                )
            
            elif labware_type == "otflex_tiprack":
                 new_plate = Collection(
                    # resource_id="01KT9Q9MJF3WPYQT6TBZ9QPQ5J",
                    resource_name="Z_PCR_CORRECT_ATTRIBUTES_PLATE_2",
                    resource_class="Microplate",
                    attributes={
                        # Common attributes
                        "plate_height": 100, 
                        "description": "Opentrons FLEX Tiprack",

                        # PF400 specific attributes
                        "pf400_grip_height": 55,

                        # SciClops specific attributes
                        "sciclops_grip_height": 55,
                    },
                )
            
            elif labware_type == "flat_bottom":
                new_plate = Collection(
                    # resource_id="01K7T1QAXCMSAJ3MAK2GAS24ZK",
                    resource_name="CORRECT_ATTRIBUTES_PLATE",
                    resource_class="Microplate",
                    attributes={
                        # Common attributes
                        "plate_height": 14, 
                        "lid_height": 10,
                        "plate_height_with_lid": 16,
                        "description": "96-well microplate with or without lid",

                        # PF400 specific attributes
                        "pf400_grip_height": 3,
                        "pf400_lid_only_grip_height":4,
                        "pf400_lid_removal_grip_height": 10,

                        # SciClops specific attributes
                        "sciclops_grip_height": 1, 
                        "sciclops_lid_grip_height": 4, 
                        "sciclops_lid_removal_grip_height": 12,
                    },
                )

            self.resource_client.add_resource(new_plate)
            self.logger.log_info(f"Created new plate resource {new_plate.resource_name}, {new_plate.resource_id}")

            self.resource_client.push(
                resource = associated_resource_id,
                child = new_plate.resource_id,
            )
            self.logger.log_info(f"Pushed new plate resource into location {location_name}")
            return new_plate, old_plate


            # create a new assay plate resource and push it into the resource object associated with the given location
            # if name == "opentrons_96_wellplate_200ul_pcr_full_skirt":

            # new_plate = self.resource_client.create_resource_from_template(
            #     template_name = name,
            #     resource_name = f"res_{experiment_id}_plate{plate_num}",
            # )

            # self.logger.log_info(f"Created new plate resource {new_plate.resource_name}, {new_plate.resource_id}")

            # self.resource_client.push(
            #     resource = associated_resource_id,
            #     child = new_plate.resource_id,
            # )
            # self.logger.log_info(f"Pushed new plate resource into location {location_name}")
            # return new_plate, old_plate
    
    def jitter(self) -> None:
        "Implements polite random jitter to assist in schedueling fairness between the running experiments."
        waiters = int(redis.get(exchange_waiters_key) or 0)
        print(f"Processes waiting for exchange lock = {waiters}", flush=True)
        if waiters > 0:
            print("Using polite jitter.", flush=True)
            time.sleep(random.uniform(1.0, 3.0))   # be polite
        else:
            print("Using fast jitter.",flush=True)
            time.sleep(random.uniform(0.1, 0.5))   # go fast

    def run_experiment(self) -> None:
        """3-round PD run: Golden Gate -> PCR -> 1:50 dilution -> lyophilized cell-free -> FDGlu, three times.

        The plan, layout, tip budget and open items are in PLAN.md in the version folder.
        Location names marked TODO are placeholders until the new nests exist in MADSci.
        """

        # PLATE SETUP ===========================================================
        # Fragments plate: starts SEALED on the external cooling block next to the peeler, shared by all rounds.
        # GG master mix in column 9 (3x volume); PCR master mix column 10/11/12 for round 1/2/3.
        new_plate, old_plate = self.push_new_assay_plate_resource(
            location_name="cold_block_ext",  # TODO: real MADSci name of the external cooling block
            labware_type="pcr"
        )

        # OT-2 20 uL tips in slot 3: the only tip box the PF400 can reach, swapped mid-run.
        new_plate, old_plate = self.push_new_assay_plate_resource(
            location_name="ot2_patrick.deck_nest_3",
            labware_type="ot2_tiprack"
        )

        # Full spare for that swap. rack2_row2_nest1 stays empty: the spent box is parked there.
        new_plate, old_plate = self.push_new_assay_plate_resource(
            location_name="rack2_row1_nest2",
            labware_type="ot2_tiprack"
        )

        # Controls plate: on an added nest, reused every round.
        new_plate, old_plate = self.push_new_assay_plate_resource(
            location_name="rack2_row1_nest1",  # TODO: real MADSci name of the added nest
            labware_type="pcr"
        )

        # Rack 1 holds one plate per type and round: row = plate type, nest = round number.
        for round_num in (1, 2, 3):
            # Golden Gate plate
            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name=f"rack1_row1_nest{round_num}",
                labware_type="pcr"
            )
            # PCR plate
            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name=f"rack1_row2_nest{round_num}",
                labware_type="pcr"
            )
            # Dilution plate (1:50)
            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name=f"rack1_row3_nest{round_num}",
                labware_type="pcr"
            )
            # Lyophilized cell-free plate (reagents in columns 1-4, room temperature)
            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name=f"rack1_row4_nest{round_num}",
                labware_type="pcr"
            )
            # FDGlu assay plate
            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name=f"rack1_row5_nest{round_num}",
                labware_type="flat_bottom"
            )

        # DEFINE PATHS AND VARIABLES ========
        experiment_id = self.experiment.experiment_id
        app_directory = Path(__file__).parent.parent
        wf_directory = app_directory / "workflows"
        run_directory = wf_directory / "run_instrument"
        transfers_directory = wf_directory / "transfers"
        rounds_directory = transfers_directory / "rounds"
        protocol_directory = app_directory / "protocols"

        # instrument runs
        run_ot2_wf = run_directory / "run_ot2_wf.yaml"
        run_flex_wf = run_directory / "run_flex.yaml"
        run_thermo_gg = run_directory / "run_thermo_gg.yaml"
        run_thermo_pcr = run_directory / "run_thermo_pcr.yaml"
        run_hidex = run_directory / "run_hidex.yaml"

        # transfers used every round (round-specific ones are built from rounds_directory below)
        fragments_cold_block_to_ot2 = transfers_directory / "fragments_cold_block_to_ot2.yaml"
        seal_and_thermocycle_gg = transfers_directory / "seal_and_thermocycle_gg.yaml"
        thermocycler_to_ot2 = transfers_directory / "thermocycler_to_ot2.yaml"
        fragments_to_flex = transfers_directory / "fragments_to_flex.yaml"
        pcr_plate_to_ot2_block = transfers_directory / "pcr_plate_to_ot2_block.yaml"
        pcr_plate_to_ot2_block_2 = transfers_directory / "pcr_plate_to_ot2_block_2.yaml"
        seal_and_thermocycle_pcr = transfers_directory / "seal_and_thermocycle_pcr.yaml"
        fragments_flex_seal_to_cold_block = transfers_directory / "fragments_flex_seal_to_cold_block.yaml"
        pcr_thermo_to_ot2 = transfers_directory / "pcr_thermo_to_ot2.yaml"
        controls_nest_to_flex = transfers_directory / "controls_nest_to_flex.yaml"
        controls_flex_to_ot2 = transfers_directory / "controls_flex_to_ot2.yaml"
        ot2_tip_swap = transfers_directory / "ot2_tip_swap.yaml"
        diluted_ot2_to_flex = transfers_directory / "diluted_ot2_to_flex.yaml"
        cfps_flex_seal_to_flex = transfers_directory / "cfps_flex_seal_to_flex.yaml"
        controls_plate_to_flex = transfers_directory / "controls_plate_to_flex.yaml"
        flex_a4_to_exchange = transfers_directory / "cfps_plate_to_peeler_to_flex.yaml"
        exchange_peel_to_flex = transfers_directory / "cfps_plate_to_peeler_to_flex_2.yaml"
        fdglu_to_hidex = transfers_directory / "fdglu_to_hidex.yaml"
        controls_flex_to_nest = transfers_directory / "controls_flex_to_nest.yaml"

        # protocols
        ot2_temp_on = protocol_directory / "set_ot2_temp_on.py"
        ot2_temp_off = protocol_directory / "set_ot2_temp_off.py"
        flex_temp_on = protocol_directory / "set_flex_temp_on.py"
        flex_temp_off = protocol_directory / "set_flex_temp_off.py"
        golden_gate_protocol = protocol_directory / "pd_golden_gate_ot2_v2.py"
        pcr_flex_protocol = protocol_directory / "pd_pcr_v2_flex.py"
        pcr_ot2_protocol = protocol_directory / "pd_pcr_v2_ot2.py"
        dilution_ot2_protocol = protocol_directory / "pd_dilute_1to50_ot2.py"
        cfps_lyo_flex_protocol = protocol_directory / "cell_free_lyo_flex.py"
        fdglu_flex_protocol = protocol_directory / "pd_fdglu_flex_v2.py"
        flex_tips_swap = protocol_directory / "flex_tips_swap.py"

        # Flex gripper moves (A4 is the PF400 handoff)
        A4_to_B1 = protocol_directory / "pcr_A4_to_B1.py"
        A4_to_B2 = protocol_directory / "pcr_A4_to_B2.py"
        A4_to_B3 = protocol_directory / "pcr_A4_to_B3.py"
        A4_to_C1 = protocol_directory / "pcr_A4_to_C1.py"
        A4_to_D1 = protocol_directory / "pcr_A4_to_D1.py"  # also runs the 150 min, 37 °C shake
        B1_to_A4 = protocol_directory / "pcr_B1_to_A4.py"
        B1_to_D4 = protocol_directory / "pcr_B1_to_D4.py"   # park the controls plate in staging
        D4_to_B1 = protocol_directory / "pcr_D4_to_B1.py"
        B2_to_A4 = protocol_directory / "pcr_B2_to_A4.py"
        B3_to_A4 = protocol_directory / "pcr_B3_to_A4.py"
        C1_to_A4 = protocol_directory / "pcr_C1_to_A4.py"
        D1_to_A4 = protocol_directory / "pcr_D1_to_A4.py"

        # TIP PLAN ===============================================================
        # Every Opentrons run starts with fresh tip tracking, so the first tip of each run is counted
        # here and passed into the protocol. Rack order must match the TIP slots in the protocols.
        # Only A1 (200 uL), A2 (50 uL 8-channel) and A3 (50 uL single) hold tip boxes on the Flex deck: a tall box in
        # C2/C3 blocks single-tip moves to B2/B3 (PartialTipMovementNotAllowedError). Spares wait in staging slots and
        # the gripper swaps them in, dropping the empty box down the waste chute.
        # OT-2: slot D2 stays EMPTY so the PF400 can still reach slot D1 (controls plate); of the tip
        # slots only D3 is reachable by the arm, so it is last in the rack order and is the one swapped.
        tips = {
            "ot2_20": helper_functions.TipLedger(
                "OT-2 20 uL", racks=6,                      # C2 B1 B2 B3 A2 then D3 (swappable)
                spare_slots=["rack2_row1_nest2"], swap_start=60),
            # No staging spare for the 200 uL box: D4 now parks the controls plate. The run uses
            # exactly one box (96 tips of 96), so a round with more combinations would stop here
            # with the ledger's error and need a box swapped in by hand.
            "flex_200": helper_functions.TipLedger(
                "Flex 200 uL", racks=1, tip_type="opentrons_flex_96_tiprack_200ul",
                deck_slot="A1", spare_slots=[]),
            "flex_50": helper_functions.TipLedger(
                "Flex 50 uL 8-channel", racks=1, tip_type="opentrons_flex_96_tiprack_50ul",
                deck_slot="A2", spare_slots=["B4", "C4"]),
            "flex_50_single": helper_functions.TipLedger("Flex 50 uL single", racks=1, unit="tip"),  # A3
        }

        def flex_move(script):
            """Run one Flex gripper move."""
            payload["current_flex_protocol"] = script
            self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

        def swap_ot2_tip_box():
            """PF400 swap: spent 20 uL box in OT-2 slot 3 out to rack 2, full spare back in."""
            spare = tips["ot2_20"].swap()
            print(f"OT-2 20 uL tip box swapped, spare taken from {spare}")
            self.workcell_client.submit_workflow(
                ot2_tip_swap.resolve(),
            )

        def swap_tip_box(ledger):
            """Gripper swap: empty box to the waste chute, full spare from staging onto the deck slot."""
            spare = ledger.swap()
            payload["swap_vars"] = {"tip_type": ledger.tip_type, "deck_slot": ledger.deck_slot,
                                    "spare_slot": spare}
            payload["current_flex_protocol"] = helper_functions.generate_ot2_protocol(
                flex_tips_swap, helper_functions.collect_ot2_replacement_variables(payload))
            self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )
            payload["swap_vars"] = {}

        payload = {}
        oracle_id = 1008  # design used for round 1; later rounds use the id returned by the previous upload

        # EXPERIMENT ACTIONS -------------------------------------------------------

        #cool OT-2 and Flex blocks once for the whole run
        payload["current_ot2_protocol"] = ot2_temp_on
        workflow = self.workcell_client.submit_workflow(
            run_ot2_wf.resolve(),
            file_inputs={
                "ot2_protocol": payload["current_ot2_protocol"],
            },
        )

        payload["current_flex_protocol"] = flex_temp_on
        workflow = self.workcell_client.submit_workflow(
            run_flex_wf.resolve(),
            file_inputs={
                "flex_protocol": payload["current_flex_protocol"],
            },
        )

        # The controls plate lives on the Flex cold block B1 for the whole run, so that it is not
        # standing at room temperature between rounds. It leaves only for the dilution, and steps
        # aside to staging D4 for the hour the fragments plate needs B1.
        workflow = self.workcell_client.submit_workflow(
            controls_nest_to_flex.resolve(),
        )
        flex_move(A4_to_B1)
        self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")

        for round_num in (1, 2, 3):

            ###############
            ### GOLDEN GATE
            ###############

            # combinations for this round from the design server
            combination_data = self.rest_handler.collect_combinations(oracle_id=oracle_id)
            payload["combinations"] = combination_data["combinations"]
            payload["use_combinations"] = combination_data["use_combinations"]
            payload["non_combinatorial_sources"] = combination_data["non_combinatorial_sources"]
            n_combos, n_cols, n_sources = helper_functions.combination_counts(payload)
            print(f"ROUND {round_num}: {n_combos} combinations in {n_cols} columns", payload["combinations"])
            if n_cols > 3:
                raise RuntimeError(f"Round {round_num} has {n_combos} combinations; cell-free plates hold 3 sample columns (24)")
            # PCR master mix: column 10/11/12 of the fragments plate (0-based well index of row A)
            payload["round_vars"] = {"round_num": round_num, "pcr_mm_start_well": 8 * (8 + round_num)}

            if round_num == 1:
                input("Paused, verify combinations and press Enter...")

            # sealed fragments plate: external cooling block -> peel -> OT-2 cold block C1
            workflow = self.workcell_client.submit_workflow(
                fragments_cold_block_to_ot2.resolve(),
            )

            # empty Golden Gate plate -> OT-2 cold block C3
            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"gg_plate_to_ot2_r{round_num}.yaml").resolve(),
            )

            # GG master mix (column 9) + fragments: 1 tip column per sample column, then 1 single tip per fragment
            gg_tip_columns = n_cols + (n_sources + 7) // 8
            if tips["ot2_20"].needs_swap(gg_tip_columns):
                swap_ot2_tip_box()
            payload["tip_starts"] = {"ot2_tip_start": tips["ot2_20"].take(gg_tip_columns)}
            ot2_replacement_variables = helper_functions.collect_ot2_replacement_variables(payload)
            temp_ot2_file_str = helper_functions.generate_ot2_protocol(golden_gate_protocol, ot2_replacement_variables)
            payload["current_ot2_protocol"] = temp_ot2_file_str
            workflow = self.workcell_client.submit_workflow(
                run_ot2_wf.resolve(),
                file_inputs={
                    "ot2_protocol": payload["current_ot2_protocol"],
                },
            )

            # seal Golden Gate plate, thermocycler, 1 h program
            workflow = self.workcell_client.submit_workflow(
                seal_and_thermocycle_gg.resolve(),
            )

            workflow = self.workcell_client.submit_workflow(
                run_thermo_gg.resolve(),
            )

            #########
            ### PCR
            #########

            # Golden Gate plate: thermocycler -> peel -> OT-2 cold block C3
            workflow = self.workcell_client.submit_workflow(
                thermocycler_to_ot2.resolve(),
            )

            # controls plate steps aside: B1 -> staging D4, so the fragments plate can use the block
            flex_move(B1_to_D4)

            # fragments plate: OT-2 C1 -> Flex A4 -> cold block B1 (PCR master mix source)
            workflow = self.workcell_client.submit_workflow(
                fragments_to_flex.resolve(),
            )

            payload["current_flex_protocol"] = A4_to_B1
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")

            # empty PCR plate -> Flex A4 -> cold block C1
            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"pcr_plate_to_flex_r{round_num}.yaml").resolve(),
            )

            payload["current_flex_protocol"] = A4_to_C1
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")

            # PCR master mix (column 9 + round) into the PCR plate: 1 column of 200 uL tips per sample column
            if tips["flex_200"].needs_swap(n_cols):
                swap_tip_box(tips["flex_200"])

            payload["tip_starts"] = {"flex200_tip_start": tips["flex_200"].take(n_cols)}
            ot2_replacement_variables = helper_functions.collect_ot2_replacement_variables(payload)
            temp_ot2_file_str = helper_functions.generate_ot2_protocol(pcr_flex_protocol, ot2_replacement_variables)
            payload["current_flex_protocol"] = temp_ot2_file_str
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            # PCR plate: Flex C1 -> A4 -> OT-2 cold block C1
            payload["current_flex_protocol"] = C1_to_A4
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name="otflex_sandy.deck_nest_A4",
                labware_type="pcr"
            )

            workflow = self.workcell_client.submit_workflow(
                pcr_plate_to_ot2_block.resolve(),
            )

            workflow = self.workcell_client.submit_workflow(
                pcr_plate_to_ot2_block_2.resolve(),
            )

            # water into GG wells, then GG product into the PCR plate: 2 tip columns per sample column
            if tips["ot2_20"].needs_swap(2 * n_cols):
                swap_ot2_tip_box()
            payload["tip_starts"] = {"ot2_tip_start": tips["ot2_20"].take(2 * n_cols)}
            ot2_replacement_variables = helper_functions.collect_ot2_replacement_variables(payload)
            temp_ot2_file_str = helper_functions.generate_ot2_protocol(pcr_ot2_protocol, ot2_replacement_variables)
            payload["current_ot2_protocol"] = temp_ot2_file_str
            workflow = self.workcell_client.submit_workflow(
                run_ot2_wf.resolve(),
                file_inputs={
                    "ot2_protocol": payload["current_ot2_protocol"],
                },
            )

            # seal PCR plate and load the thermocycler (program not started yet)
            workflow = self.workcell_client.submit_workflow(
                seal_and_thermocycle_pcr.resolve(),
            )

            # Nothing can run during the 3 h PCR, so store the fragments plate and clear the GG plate first.
            # fragments plate: Flex B1 -> A4 -> seal -> external cooling block
            payload["current_flex_protocol"] = B1_to_A4
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name="otflex_sandy.deck_nest_A4",
                labware_type="pcr"
            )

            workflow = self.workcell_client.submit_workflow(
                fragments_flex_seal_to_cold_block.resolve(),
            )

            # controls plate back onto the cold block for the rest of the round
            flex_move(D4_to_B1)

            # used Golden Gate plate: OT-2 C3 -> its nest
            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"gg_plate_ot2_to_rack_r{round_num}.yaml").resolve(),
            )

            # PCR program
            workflow = self.workcell_client.submit_workflow(
                run_thermo_pcr.resolve(),
            )

            ################
            #### DILUTE
            ################

            # PCR plate: thermocycler -> peel -> OT-2 cold block C1
            workflow = self.workcell_client.submit_workflow(
                pcr_thermo_to_ot2.resolve(),
            )

            # empty dilution plate -> OT-2 cold block C3
            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"diluted_plate_to_ot2_r{round_num}.yaml").resolve(),
            )

            # controls plate: Flex cold block B1 -> A4 -> OT-2 D1, just for the dilution
            flex_move(B1_to_A4)
            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name="otflex_sandy.deck_nest_A4",
                labware_type="pcr"
            )
            workflow = self.workcell_client.submit_workflow(
                controls_flex_to_ot2.resolve(),
            )

            # 98 uL water (5 x 19.6 uL, one tip column) + 2 uL PCR per well, mix at 20 uL; controls column
            if tips["ot2_20"].needs_swap(n_cols + 2):
                swap_ot2_tip_box()
            payload["tip_starts"] = {"ot2_tip_start": tips["ot2_20"].take(n_cols + 2)}
            ot2_replacement_variables = helper_functions.collect_ot2_replacement_variables(payload)
            temp_ot2_file_str = helper_functions.generate_ot2_protocol(dilution_ot2_protocol, ot2_replacement_variables)
            payload["current_ot2_protocol"] = temp_ot2_file_str
            workflow = self.workcell_client.submit_workflow(
                run_ot2_wf.resolve(),
                file_inputs={
                    "ot2_protocol": payload["current_ot2_protocol"],
                },
            )

            # PCR plate: OT-2 C1 -> re-seal -> its nest
            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"pcr_plate_ot2_seal_to_rack_r{round_num}.yaml").resolve(),
            )

            # Controls plate: OT-2 D1 -> Flex A4 -> cold block B1, as soon as the dilution is done.
            # It is not needed again until the FDGlu assay, and B1 is free from here until then, so
            # this is where it waits instead of sitting at room temperature on the OT-2 for hours.
            # controls plate: OT-2 D1 -> Flex A4 -> cold block B1
            workflow = self.workcell_client.submit_workflow(
                controls_plate_to_flex.resolve(),
            )

            payload["current_flex_protocol"] = A4_to_B1
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")


            #################
            ##### CELL FREE
            #################

            # diluted PCR plate: OT-2 C3 -> Flex A4 -> cold block C1
            workflow = self.workcell_client.submit_workflow(
                diluted_ot2_to_flex.resolve(),
            )

            payload["current_flex_protocol"] = A4_to_C1
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")

            # lyophilized cell-free plate -> Flex A4 -> B2
            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"cfps_plate_to_flex_r{round_num}.yaml").resolve(),
            )

            payload["current_flex_protocol"] = A4_to_B2
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")

            # 24 uL water into columns 1-4 (one tip column), then per column: mix diluted PCR, add 6 uL, mix 5 x 20 uL slowly
            if tips["flex_50"].needs_swap(n_cols + 2):
                swap_tip_box(tips["flex_50"])

            payload["tip_starts"] = {"flex50_tip_start": tips["flex_50"].take(n_cols + 2)}
            ot2_replacement_variables = helper_functions.collect_ot2_replacement_variables(payload)
            temp_ot2_file_str = helper_functions.generate_ot2_protocol(cfps_lyo_flex_protocol, ot2_replacement_variables)
            payload["current_flex_protocol"] = temp_ot2_file_str
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            # diluted PCR plate: Flex C1 -> A4 -> its nest
            payload["current_flex_protocol"] = C1_to_A4
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name="otflex_sandy.deck_nest_A4",
                labware_type="pcr"
            )

            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"diluted_flex_to_rack_r{round_num}.yaml").resolve(),
            )

            # cell-free plate: Flex B2 -> A4 -> seal -> A4 -> heater-shaker D1 (150 min, 37 °C)
            payload["current_flex_protocol"] = B2_to_A4
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name="otflex_sandy.deck_nest_A4",
                labware_type="pcr"
            )

            workflow = self.workcell_client.submit_workflow(
                cfps_flex_seal_to_flex.resolve(),
            )

            payload["current_flex_protocol"] = A4_to_D1
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")

            ################
            #### FD GLU ASSAY
            ################

            # empty FDGlu plate -> Flex A4 -> B3
            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"fdglu_plate_to_flex_r{round_num}.yaml").resolve(),
            )

            payload["current_flex_protocol"] = A4_to_B3
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")

            # cell-free plate: heater-shaker D1 -> A4 -> peel -> A4 -> B2
            payload["current_flex_protocol"] = D1_to_A4
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name="otflex_sandy.deck_nest_A4",
                labware_type="pcr"
            )

            workflow = self.workcell_client.submit_workflow(
                flex_a4_to_exchange.resolve(),
            )

            workflow = self.workcell_client.submit_workflow(
                exchange_peel_to_flex.resolve(),
            )

            payload["current_flex_protocol"] = A4_to_B2
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            self.pop_assay_plate_resource("otflex_sandy.deck_nest_A4")

            # FDGlu assay: 1 column of 200 uL tips, (n_cols + 1) columns of 50 uL, 6 single 50 uL tips
            if tips["flex_200"].needs_swap(1):
                swap_tip_box(tips["flex_200"])
            if tips["flex_50"].needs_swap(n_cols + 1):
                swap_tip_box(tips["flex_50"])

            payload["tip_starts"] = {
                "flex200_tip_start": tips["flex_200"].take(1),
                "flex50_tip_start": tips["flex_50"].take(n_cols + 1),
                "flex50_single_start": tips["flex_50_single"].take(6),
            }
            ot2_replacement_variables = helper_functions.collect_ot2_replacement_variables(payload)
            temp_ot2_file_str = helper_functions.generate_ot2_protocol(fdglu_flex_protocol, ot2_replacement_variables)
            payload["current_flex_protocol"] = temp_ot2_file_str
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            # FDGlu plate: Flex B3 -> A4 -> exchange -> Hidex, read
            payload["current_flex_protocol"] = B3_to_A4
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name="otflex_sandy.deck_nest_A4",
                labware_type="flat_bottom"
            )

            workflow = self.workcell_client.submit_workflow(
                flex_a4_to_exchange.resolve(),
            )

            workflow = self.workcell_client.submit_workflow(
                fdglu_to_hidex.resolve(),
            )

            workflow = self.workcell_client.submit_workflow(
                run_hidex.resolve(),
            )

            hidex_data_point = workflow.get_datapoint(label="file")
            path = hidex_data_point.path[12:]
            correct_path = "/home/rpl/workspace/" + path
            oracle_id = self.rest_handler.upload_excel_file(correct_path)
            print(f"ROUND {round_num} uploaded, oracle id", oracle_id)

            #################
            ### ROUND CLEANUP
            #################

            # FDGlu plate: Hidex -> its nest (the Hidex must be empty for the next round)
            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"fdglu_hidex_to_rack_r{round_num}.yaml").resolve(),
            )

            # used cell-free plate: Flex B2 -> A4 -> its nest
            payload["current_flex_protocol"] = B2_to_A4
            workflow = self.workcell_client.submit_workflow(
                run_flex_wf.resolve(),
                file_inputs={
                    "flex_protocol": payload["current_flex_protocol"],
                },
            )

            new_plate, old_plate = self.push_new_assay_plate_resource(
                location_name="otflex_sandy.deck_nest_A4",
                labware_type="pcr"
            )

            workflow = self.workcell_client.submit_workflow(
                (rounds_directory / f"cfps_flex_to_rack_r{round_num}.yaml").resolve(),
            )

        ###########
        ### FINISH
        ###########

        # controls plate: off the cold block and back to its nest, once the last round is done
        flex_move(B1_to_A4)
        new_plate, old_plate = self.push_new_assay_plate_resource(
            location_name="otflex_sandy.deck_nest_A4",
            labware_type="pcr"
        )
        workflow = self.workcell_client.submit_workflow(
            controls_flex_to_nest.resolve(),
        )

        print("TIPS used in the current box / spare boxes left:",
              {name: (ledger.used, ledger.spares) for name, ledger in tips.items()})

        payload["current_ot2_protocol"] = ot2_temp_off
        workflow = self.workcell_client.submit_workflow(
            run_ot2_wf.resolve(),
            file_inputs={
                "ot2_protocol": payload["current_ot2_protocol"],
            },
        )

        payload["current_flex_protocol"] = flex_temp_off
        workflow = self.workcell_client.submit_workflow(
            run_flex_wf.resolve(),
            file_inputs={
                "flex_protocol": payload["current_flex_protocol"],
            },
        )


if __name__ == "__main__":
    # exp_app = PDApp()

    # current_time = datetime.now()

    # # Start experiment run
    # with exp_app.manage_experiment(
    #     run_name = f"PD_Experiment{current_time.strftime('%Y%m%d_%H%M%S')}",
    #     run_description = "PD experiment",
    # ):
    #     exp_app.start_app()


    # Start the experiment run.
    PDApp.main(
        lab_server_url="http://146.137.240.20:8000/",
    )
