from opentrons import protocol_api
import itertools
from opentrons.protocol_api import SINGLE
import ast


metadata = {
    'protocolName': 'Protein Design PCR 8 channel',
    'author': 'LDRD team ',
    'description': 'PCR for Protein Design reagents',
    'source': 'FlexAS/pd_pcr_81.py'
}

requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


# Protocol Configuration
config = {
    # Combinatorial mixing
    'transfer_volume': 2,  # µL from each gg well
    # 'number_of_gg_samples': 6,
    # 'combinations': [[18,10],[11,19],[4,20],[21,13]],
    # 'combinations': [[1], [2, 2], [3, 3], [4, 4]],
    # 'use_combinations': True,

    'combinations': "$combinations",
    'use_combinations': "$use_combinations",
    'non_combinatorial_sources': "$non_combinatorial_sources",

    # Master mix and reagent settings
    'pcr_master_mix_well_volume': 100,
    'water_volume': 20,
    'pcr_master_mix_volume': 24,
    'water_well': 1,
    'master_mix_start_well': 48,
    'tips_used': 0,


    # Temperature settings
    'temperature': 4,  # °C

    # Labware
    'pcr_plate_type': 'opentrons_96_wellplate_200ul_pcr_full_skirt',
    'gg_plate_type': 'opentrons_96_wellplate_200ul_pcr_full_skirt',
    'reagent_plate_type': 'nest_12_reservoir_15ml',
    'tip_rack_type_20_01': 'opentrons_96_filtertiprack_20ul',
    'pipette_type_20': 'p20_single_gen2',
    'pipette_type_20_multi': 'p20_multi_gen2',

    # Deck positions
    'temp_module_01_position': 'C1',
    'temp_module_02_position': 'C3',
    'pcr_plate_position': 'C1',
    'gg_plate_position': 'C3',
    'reagent_plate_position': 'A1',
    # tip racks: see OT2_TIP_SLOTS below
}


# 3-round run: OT-2 20 uL tip racks, in the order the tip counter in full_run.py uses them (12 columns per rack).
# Slot D1 (1) holds the controls plate and D2 (2) MUST stay empty: the slots are ~6 mm apart, so anything in
# slot 2 leaves the PF400 gripper no room to reach slots 1 or 3. D3 (3) is last in the order and is the only
# rack the PF400 can swap, so it runs out last and is replaced from rack 2 mid-run. Slots other than D3 need
# position check offsets.
OT2_TIP_SLOTS = ['C2', 'B1', 'B2', 'B3', 'A2', 'D3']
OT2_TIP_OFFSETS = {'D3': (0.4, 1.2, -0.4)}
OT2_TIP_START = int("$ot2_tip_start")  # first unused tip column across OT2_TIP_SLOTS, set by full_run.py


def set_tip_offsets(racks):
    for slot, rack in zip(OT2_TIP_SLOTS, racks):
        x, y, z = OT2_TIP_OFFSETS.get(slot, (0, 0, 0))
        rack.set_offset(x=x, y=y, z=z)


def ot2_tip_column(racks, index):
    """Top tip (row A) of tip column `index`, counted across the racks in OT2_TIP_SLOTS order."""
    if index >= 12 * len(racks):
        raise ValueError(f"tip column {index} is past the last OT-2 tip rack")
    return racks[index // 12].columns()[index % 12][0]


def calculate_total_combinations(combinations):
    """Calculate total number of combinations without generating them"""
    total = 1
    for sublist in combinations:
        total *= len(sublist)
    return total

def generate_all_combinations(combinations):
    """Generate all possible combinations from the jagged array"""
    return list(itertools.product(*combinations))

def transfer_water_to_gg(protocol, reagent_plate, gg_plate, pipette, config):
    water_volume = config['water_volume']
    # gg_wells = config['number_of_gg_samples']
    water_well = reagent_plate.wells()[config['water_well'] - 1]
    # protocol.comment(f"Total wells to add water to: {gg_wells}")
    combinations = config['combinations']

    if config['use_combinations'] is True:
        combinations = config['combinations']
        total_combinations = calculate_total_combinations(combinations)
        # Generate all possible combinations
        all_combinations = generate_all_combinations(combinations)
    else:
        all_combinations = config['non_combinatorial_sources']
        total_combinations = len(all_combinations)

    # gg_wells = calculate_total_combinations(combinations)
    gg_wells = total_combinations
    columns_needed = (gg_wells + 7) // 8

    for col_idx in range(columns_needed):
        dest_well = gg_plate.columns()[col_idx]
        protocol.comment(f"\nTransferring to destination well {dest_well}:")
        pipette.transfer(
            water_volume,
            water_well,
            dest_well,
            new_tip='always',  # Use fresh tip for each transfer
            mix_after = (3, 10)
        )

        config['tips_used']+=8

    # for well in range(1, gg_wells + 1):
    #     dest_well = gg_plate.wells()[well - 1]
    #     protocol.comment(f"\nTransferring to destination well {dest_well}:")
    #     pipette.transfer(
    #         water_volume,
    #         water_well,
    #         dest_well,
    #         new_tip='always',  # Use fresh tip for each transfer
    #         mix_after = (3, 10)
    #     )



def gg_to_pcr_plate(protocol, gg_plate, pcr_plate, pipette, config):

    if config['use_combinations'] is True:
        combinations = config['combinations']
        total_combinations = calculate_total_combinations(combinations)
        # Generate all possible combinations
        all_combinations = generate_all_combinations(combinations)
    else:
        all_combinations = config['non_combinatorial_sources']
        total_combinations = len(all_combinations)

    # combinations = config['combinations']
    # gg_wells = calculate_total_combinations(combinations)
    gg_wells = total_combinations
    transfer_volume = config['transfer_volume']
    columns_needed = (gg_wells + 7) // 8

    for col_idx in range(columns_needed):
        dest_well = pcr_plate.columns()[col_idx]
        source_well = gg_plate.columns()[col_idx]
        pipette.transfer(
            transfer_volume,
            source_well,
            dest_well,
            new_tip='always',  # Use fresh tip for each transfer
            mix_before = (3, 10),
            mix_after = (3, 10)
        )

        config['tips_used']+=8



    # for well in range(1, gg_wells + 1):
    #     dest_well = pcr_plate.wells()[well - 1]
    #     source_well = gg_plate.wells()[well - 1]

    #     pipette.transfer(
    #         transfer_volume,
    #         source_well,
    #         dest_well,
    #         new_tip='always',  # Use fresh tip for each transfer
    #         mix_before = (3, 10),
    #         mix_after = (3, 10)
    #     )








def run(protocol: protocol_api.ProtocolContext):
    combinations_string = config['combinations']
    combinations = ast.literal_eval(combinations_string)
    config['combinations'] = combinations
    non_combinations_string = config['non_combinatorial_sources']
    noncombinations = ast.literal_eval(non_combinations_string)
    config['non_combinatorial_sources'] = noncombinations
    if config['use_combinations'] == "False":
            config['use_combinations'] = False
    # Load temperature module and adapter
    temp_mod_1 = protocol.load_module(module_name="temperature module gen2", location=config['temp_module_01_position'])
    temp_adapter_1 = temp_mod_1.load_adapter("opentrons_96_well_aluminum_block")

    temp_mod_2 = protocol.load_module(module_name="temperature module gen2", location=config['temp_module_02_position'])
    temp_adapter_2 = temp_mod_2.load_adapter("opentrons_96_well_aluminum_block")

    # Set temperature
    # temp_mod_1.set_temperature(config['temperature']) #TODO: make seperate, or just set earlier, only 1 hour with plate
    # temp_mod_2.set_temperature(config['temperature']) #TODO: make seperate, or just set earlier, only 1 hour with plate



    # Load destination plate
    # pcr_plate = protocol.load_labware(config['pcr_plate_type'], config['pcr_plate_position'])
    pcr_plate = temp_adapter_1.load_labware(config['pcr_plate_type'])
    pcr_plate.set_offset(x=0.4, y=0.4, z=0.0)

    # gg_plate = protocol.load_labware(config['gg_plate_type'], config['gg_plate_position'])
    gg_plate = temp_adapter_2.load_labware(config['gg_plate_type'])
    gg_plate.set_offset(x=0.7, y=0.30, z=0.2)

    reagent_plate = protocol.load_labware(config['reagent_plate_type'], config['reagent_plate_position'])


    tipracks = [protocol.load_labware(config['tip_rack_type_20_01'], slot) for slot in OT2_TIP_SLOTS]
    set_tip_offsets(tipracks)

    # Pipettes
    p50 = protocol.load_instrument('p20_multi_gen2', mount='right', tip_racks=tipracks)
    p50s = protocol.load_instrument('p20_single_gen2', mount='left', tip_racks=tipracks)

    p50.configure_nozzle_layout(style='COLUMN', start='A1', tip_racks=tipracks)
    p50.starting_tip = ot2_tip_column(tipracks, OT2_TIP_START)



    # Perform combinatorial transfers #TODO: SWAP?  so adding small vols into large quant of master mix
    transfer_water_to_gg(
        protocol=protocol,
        reagent_plate=reagent_plate,
        gg_plate=gg_plate,
        pipette=p50,
        config=config
    )

    gg_to_pcr_plate(
        protocol=protocol,
        gg_plate=gg_plate,
        pcr_plate=pcr_plate,
        pipette=p50,
        config=config
    )

    protocol.comment(f"tips used: {config['tips_used']}")

