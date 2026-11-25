from opentrons import protocol_api
import itertools
import ast


metadata = {
    'protocolName': 'Protein Design 1:50 PCR dilution on the OT-2',
    'author': 'LDRD team ',
    'description': '3-round run: 98 uL water (5 x 19.6 uL with 20 uL tips) into each dilution well, then 2 uL PCR '
                   'product, mixed at 20 uL. Controls column as in pd_dd_v2_ot2.py. Based on pd_dd_v2_ot2.py.',
}

requirements = {"robotType": "OT-2", "apiLevel": "2.20"}


config = {
    'combinations': "$combinations",
    'use_combinations': "$use_combinations",
    'non_combinatorial_sources': "$non_combinatorial_sources",

    # Dilution
    'water_volume': 98,          # uL per dilution well
    'water_chunks': 5,           # 98 uL = 5 x 19.6 uL with 20 uL tips
    'pcr_sample_volume': 2,      # uL PCR product per dilution well -> 1:50
    'mix_after': (5, 20),        # (repetitions, uL) after adding the PCR product
    'control_volume': 20,        # uL controls into the column after the samples (undiluted, as before)
    'water_well': 1,             # reservoir well (1-indexed)

    # Labware
    'pcr_plate_type': 'opentrons_96_wellplate_200ul_pcr_full_skirt',
    # 200 uL tough plate: 98 + 2 uL leaves room for the 20 uL mixing
    'diluted_plate_type': 'opentrons_96_wellplate_200ul_pcr_full_skirt',
    'reagent_plate_type': 'nest_12_reservoir_15ml',
    'tip_rack_type_20_01': 'opentrons_96_filtertiprack_20ul',
    'controls_plate_type': 'opentrons_96_wellplate_200ul_pcr_full_skirt',

    # Deck positions
    'temp_module_01_position': 'C1',   # PCR plate (cold)
    'temp_module_02_position': 'C3',   # dilution plate (cold)
    'reagent_plate_position': 'A1',
    'controls_plate_position': 'D1',
}


# 3-round run: OT-2 20 uL tip racks, in the order the tip counter in full_run.py uses them (12 columns per rack).
# D1 stays free for the controls plate. Slots other than D3 need labware position check offsets (TODO).
OT2_TIP_SLOTS = ['D3', 'D2', 'C2', 'B1', 'B2', 'B3', 'A2']
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


def sample_columns(config):
    if config['use_combinations'] is True:
        total = len(list(itertools.product(*config['combinations'])))
    else:
        total = len(config['non_combinatorial_sources'])
    return (total + 7) // 8


def water_to_dilution_wells(protocol, reagent_plate, diluted_plate, pipette, columns, config):
    """98 uL into each sample column with ONE tip column: dispense at the top of the empty wells, so the tips never touch liquid."""
    source = reagent_plate.wells()[config['water_well'] - 1]
    chunk = config['water_volume'] / config['water_chunks']
    pipette.pick_up_tip()
    for col_idx in range(columns):
        dest = diluted_plate.columns()[col_idx][0]
        protocol.comment(f"Water {config['water_chunks']} x {chunk:.1f} uL into column {col_idx + 1}")
        for _ in range(config['water_chunks']):
            pipette.aspirate(chunk, source)
            pipette.dispense(chunk, dest.top(-2))
            pipette.blow_out(dest.top(-2))
    pipette.drop_tip()


def pcr_to_dilution_wells(protocol, pcr_plate, diluted_plate, pipette, columns, config):
    """2 uL PCR product into the water, mix at 20 uL; fresh tips per column."""
    reps, vol = config['mix_after']
    for col_idx in range(columns):
        source = pcr_plate.columns()[col_idx][0]
        dest = diluted_plate.columns()[col_idx][0]
        protocol.comment(f"PCR column {col_idx + 1}: {config['pcr_sample_volume']} uL into 98 uL water, mix {reps} x {vol} uL")
        pipette.pick_up_tip()
        pipette.aspirate(config['pcr_sample_volume'], source)
        pipette.dispense(config['pcr_sample_volume'], dest.bottom(2))
        pipette.mix(reps, vol, dest.bottom(2))
        pipette.blow_out(dest.top(-2))
        pipette.drop_tip()


def controls_to_dilution_plate(protocol, controls_plate, diluted_plate, pipette, columns, config):
    """Controls column 1 into the column after the samples (same as pd_dd_v2_ot2.py)."""
    pipette.transfer(config['control_volume'], controls_plate.columns()[0], diluted_plate.columns()[columns],
                     new_tip='always')


def run(protocol: protocol_api.ProtocolContext):
    config['combinations'] = ast.literal_eval(config['combinations'])
    config['non_combinatorial_sources'] = ast.literal_eval(config['non_combinatorial_sources'])
    if config['use_combinations'] == "False":
        config['use_combinations'] = False
    columns = sample_columns(config)

    temp_mod_1 = protocol.load_module(module_name="temperature module gen2", location=config['temp_module_01_position'])
    temp_adapter_1 = temp_mod_1.load_adapter("opentrons_96_well_aluminum_block")
    temp_mod_2 = protocol.load_module(module_name="temperature module gen2", location=config['temp_module_02_position'])
    temp_adapter_2 = temp_mod_2.load_adapter("opentrons_96_well_aluminum_block")

    pcr_plate = temp_adapter_1.load_labware(config['pcr_plate_type'])
    pcr_plate.set_offset(x=0.4, y=0.4, z=0.0)
    diluted_plate = temp_adapter_2.load_labware(config['diluted_plate_type'])
    diluted_plate.set_offset(x=0.7, y=0.30, z=0.2)
    reagent_plate = protocol.load_labware(config['reagent_plate_type'], config['reagent_plate_position'])
    controls_plate = protocol.load_labware(config['controls_plate_type'], config['controls_plate_position'])

    tipracks = [protocol.load_labware(config['tip_rack_type_20_01'], slot) for slot in OT2_TIP_SLOTS]
    set_tip_offsets(tipracks)

    p20 = protocol.load_instrument('p20_multi_gen2', mount='right', tip_racks=tipracks)
    p20.starting_tip = ot2_tip_column(tipracks, OT2_TIP_START)

    # tip columns used: 1 (water) + columns (PCR) + 1 (controls) -- must match full_run.py
    water_to_dilution_wells(protocol, reagent_plate, diluted_plate, p20, columns, config)
    pcr_to_dilution_wells(protocol, pcr_plate, diluted_plate, p20, columns, config)
    controls_to_dilution_plate(protocol, controls_plate, diluted_plate, p20, columns, config)
