from opentrons import protocol_api

metadata = {
    'protocolName': 'Swap a Flex tip box from staging',
    'author': 'LDRD team',
    'description': '3-round run: the Flex gripper drops the empty tip box on $deck_slot into the waste chute, then '
                   'moves the full spare from staging slot $spare_slot onto $deck_slot. No PF400 involved. '
                   'full_run.py runs this between protocol runs when its tip counter says the box is spent.',
}

requirements = {"robotType": "Flex", "apiLevel": "2.20"}

TIP_TYPE = "$tip_type"      # e.g. opentrons_flex_96_tiprack_50ul
DECK_SLOT = "$deck_slot"    # A2 (50 uL 8-channel) or A1 (200 uL)
SPARE_SLOT = "$spare_slot"  # staging slot holding the full box: B4, C4 or D4


def run(protocol: protocol_api.ProtocolContext):
    chute = protocol.load_waste_chute()
    empty_box = protocol.load_labware(TIP_TYPE, DECK_SLOT)
    spare_box = protocol.load_labware(TIP_TYPE, SPARE_SLOT)
    protocol.move_labware(labware=empty_box, new_location=chute, use_gripper=True)
    protocol.move_labware(labware=spare_box, new_location=DECK_SLOT, use_gripper=True)
