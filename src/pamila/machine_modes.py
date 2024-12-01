from enum import Enum


class MachineMode(Enum):
    LIVE = "LIVE"
    DIGITAL_TWIN = "DT"
    SIMULATOR = "SIM"
    SIMULATOR_1 = "SIM_1"


_SELECTED_MODE = MachineMode.SIMULATOR
_ONLINE_MODE = MachineMode.LIVE
_OFFLINE_MODE = MachineMode.SIMULATOR


def get_machine_mode():
    return _SELECTED_MODE


def set_machine_mode(new_mode: MachineMode):
    global _SELECTED_MODE
    _SELECTED_MODE = new_mode


def set_online_mode(new_mode: MachineMode):
    global _ONLINE_MODE
    assert new_mode in (MachineMode.LIVE, MachineMode.DIGITAL_TWIN)
    _ONLINE_MODE = new_mode


def set_offline_mode(new_mode: MachineMode):
    global _OFFLINE_MODE
    assert new_mode in (MachineMode.SIMULATOR, MachineMode.SIMULATOR_1)
    _OFFLINE_MODE = new_mode


def go_online():
    set_machine_mode(_ONLINE_MODE)


def go_offline():
    set_machine_mode(_OFFLINE_MODE)


def is_online():
    machine_mode = get_machine_mode()
    return machine_mode in (MachineMode.LIVE, MachineMode.DIGITAL_TWIN)
