from opentrons import protocol_api
import itertools
import ast


metadata = {
    'protocolName': 'Protein Design cell-free on lyophilized plates (Flex)',
    'author': 'LDRD team ',
    'description': '3-round run: rehydrate the lyophilized cell-free reagents (columns 1-4) with 24 uL water, then per '
                   'column mix the 1:50 diluted PCR, add 6 uL and mix 5 x 20 uL slowly (30 uL total, 250x PCR overall).',
}

requirements = {"robotType": "Flex", "apiLevel": "2.20"}


config = {
    'combinations': "$combinations",
    'use_combinations': "$use_combinations",
    'non_combinatorial_sources': "$non_combinatorial_sources",

    'water_volume': 24,            # uL water per cell-free well (X)
    'template_volume': 6,          # uL diluted PCR per well (30 - X)
    'premix': (3, 20),             # mix the diluted PCR before taking it (repetitions, uL)
    'final_mix': (5, 20),          # mix the reaction after adding the PCR (repetitions, uL)
    'final_mix_rate': 0.2,         # fraction of the default flow rate: slow, to avoid bubbles
    'rehydrate_minutes': 0,        # optional wait after the water; the per-column mixing already gives time
    'water_well': 1,               # reservoir well (1-indexed)

    # Labware
    # TODO: confirm the lyophilized plates are the same Opentrons tough plate (offsets below assume it)
    'cfps_plate_type': 'opentrons_96_wellplate_200ul_pcr_full_skirt',
    'diluted_plate_type': 'opentrons_96_wellplate_200ul_pcr_full_skirt',
    'reagent_plate_type': 'nest_12_reservoir_15ml',
    'tip_rack_type_50': 'opentrons_flex_96_tiprack_50ul',

    # Deck positions
    'temp_module_01_position': 'B1',
    'temp_module_02_position': 'C1',   # diluted PCR plate (cold)
    'cfps_plate_position': 'B2',       # lyophilized plate, room temperature
    'reagent_plate_position': 'D2',
}

# 3-round run: 50 uL 8-channel tip boxes, in the order the tip counter in full_run.py uses them (12 columns each).
FLEX50_TIP_SLOTS = ['A2', 'C2', 'C3']
FLEX50_TIP_START = int("$flex50_tip_start")


def tip_column(racks, index):
    if index >= 12 * len(racks):
        raise ValueError(f"tip column {index} is past the last 50 uL tip box")
    return racks[index // 12].columns()[index % 12][0]


def sample_columns(config):
    if config['use_combinations'] is True:
        total = len(list(itertools.product(*config['combinations'])))
    else:
        total = len(config['non_combinatorial_sources'])
    return (total + 7) // 8


def run(protocol: protocol_api.ProtocolContext):
    config['combinations'] = ast.literal_eval(config['combinations'])
    config['non_combinatorial_sources'] = ast.literal_eval(config['non_combinatorial_sources'])
    if config['use_combinations'] == "False":
        config['use_combinations'] = False
    reaction_columns = sample_columns(config) + 1   # samples + controls column (diluted plate has controls there too)

    temp_mod_1 = protocol.load_module(module_name="temperature module gen2", location=config['temp_module_01_position'])
    temp_mod_2 = protocol.load_module(module_name="temperature module gen2", location=config['temp_module_02_position'])
    temp_adapter_2 = temp_mod_2.load_adapter("opentrons_96_well_aluminum_block")
    chute = protocol.load_waste_chute()

    diluted_plate = temp_adapter_2.load_labware(config['diluted_plate_type'])
    diluted_plate.set_offset(x=0.7, y=0.30, z=0.2)
    cfps_plate = protocol.load_labware(config['cfps_plate_type'], config['cfps_plate_position'])
    cfps_plate.set_offset(x=0.4, y=0.4, z=0.0)
    reagent_plate = protocol.load_labware(config['reagent_plate_type'], config['reagent_plate_position'])

    tipracks = [protocol.load_labware(config['tip_rack_type_50'], slot) for slot in FLEX50_TIP_SLOTS]
    p50 = protocol.load_instrument('flex_8channel_50', mount='right', tip_racks=tipracks)
    p50.starting_tip = tip_column(tipracks, FLEX50_TIP_START)

    # 1) water into the dry wells with one tip column, dispensing at the top so the tips never touch the lyophilized cake
    water = reagent_plate.wells()[config['water_well'] - 1]
    p50.pick_up_tip()
    for col in range(reaction_columns):
        dest = cfps_plate.columns()[col][0]
        p50.aspirate(config['water_volume'], water)
        p50.dispense(config['water_volume'], dest.top(-1))
        p50.blow_out(dest.top(-1))
    p50.drop_tip()

    if config['rehydrate_minutes']:
        protocol.delay(minutes=config['rehydrate_minutes'])

    # 2) per column: mix diluted PCR, add 6 uL, mix the reaction slowly; fresh tips each column
    pre_reps, pre_vol = config['premix']
    reps, vol = config['final_mix']
    for col in range(reaction_columns):
        src = diluted_plate.columns()[col][0]
        dest = cfps_plate.columns()[col][0]
        protocol.comment(f"Column {col + 1}: {config['template_volume']} uL diluted PCR into rehydrated cell-free")
        p50.pick_up_tip()
        p50.mix(pre_reps, pre_vol, src.bottom(2))
        p50.aspirate(config['template_volume'], src.bottom(1))
        p50.dispense(config['template_volume'], dest.bottom(1))
        p50.mix(reps, vol, dest.bottom(1), rate=config['final_mix_rate'])
        p50.drop_tip()
    # tip columns used: 1 (water) + reaction_columns -- must match full_run.py
