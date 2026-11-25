from opentrons import protocol_api

metadata = {
    'protocolName': 'Swap Flex 200 uL tip box',
    'author': 'LDRD team',
    'description': '3-round run: Flex gripper moves the empty 200 uL box A1 -> staging C4, then the full spare B4 -> A1. '
                   'No PF400 involved. Only run when the tip counter in full_run.py says A1 cannot cover the next step.',
}

requirements = {"robotType": "Flex", "apiLevel": "2.20"}

TIP_TYPE_200 = 'opentrons_flex_96_tiprack_200ul'


def run(protocol: protocol_api.ProtocolContext):
    empty_box = protocol.load_labware(TIP_TYPE_200, 'A1')
    spare_box = protocol.load_labware(TIP_TYPE_200, 'B4')
    protocol.move_labware(labware=empty_box, new_location='C4', use_gripper=True)
    protocol.move_labware(labware=spare_box, new_location='A1', use_gripper=True)
