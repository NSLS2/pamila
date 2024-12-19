from collections import defaultdict
from enum import Enum
from typing import Dict, List, Literal

from pydantic import BaseModel, Field

from ..machine_modes import MachineMode

_SIM_INTERFACES = defaultdict(dict)  # _SIM_INTERFACES[machine_name][machine_mode]
_SIM_INTERFACE_SPECS = {}  # _SIM_INTERFACE_SPECS[machine_name]


class SimulatorInterfacePath(BaseModel):
    machine_name: str
    machine_mode: MachineMode


def get_sim_interface(itf_path: SimulatorInterfacePath):
    if itf_path.machine_mode not in _SIM_INTERFACES[itf_path.machine_name]:
        initialize_sim_interface(itf_path.machine_name, itf_path.machine_mode)
    return _SIM_INTERFACES[itf_path.machine_name][itf_path.machine_mode]


def _reset_sim_interface(machine_name: str):
    if machine_name in _SIM_INTERFACES:
        del _SIM_INTERFACES[machine_name]


class SimulatorPvDefinition(BaseModel):
    pvclass: str
    args: List = Field(default_factory=list)
    kwargs: Dict = Field(default_factory=dict)


class SimulatorInterfaceSpec(BaseModel):
    package_name: str
    sim_pv_defs: Dict[str, SimulatorPvDefinition] = Field(default_factory=dict)
    conversion_plugin_folder: str = ""


class SimConfigs(BaseModel):
    facility: str
    machine: str
    control_system: Literal["epics", "tango"]
    simulator_configs: Dict[str, SimulatorInterfaceSpec | None]
    selected_config: str
    conversion_plugin_folder: str = ""

    model_config = {"extra": "forbid", "frozen": True}


class PyATLatticeModelSpec(BaseModel):
    lattice_filepath: str
    non_simulator_settings_filepath: str = ""


class PyATInterfaceSpec(SimulatorInterfaceSpec):
    closed_orbit_uint32_indexes: List[int]
    lattice_models: Dict[str, PyATLatticeModelSpec]
    default_lattice_model: str


def get_sim_pvprefix(machine_mode: MachineMode):
    match machine_mode:
        case MachineMode.SIMULATOR:
            pvprefix = "SIMPV:"
        case _:
            raise NotImplementedError

    return pvprefix


def create_interface(
    sim_itf_spec: SimulatorInterfaceSpec,
    machine_mode: MachineMode,
    model_name: str = "",
):
    match sim_itf_spec:
        case PyATInterfaceSpec():
            assert sim_itf_spec.package_name == "pyat"

            from . import pyat

            sim_itf = pyat.Interface(machine_mode, sim_itf_spec.sim_pv_defs)

            if model_name == "":
                model_name = sim_itf_spec.default_lattice_model
            sel_lat_model = sim_itf_spec.lattice_models[model_name]

            sim_itf.load_lattice(sel_lat_model.lattice_filepath)

            sim_itf.set_closed_orbit_refpts(sim_itf_spec.closed_orbit_uint32_indexes)
        case _:
            raise NotImplementedError

    return sim_itf


def set_sim_interface_spec(machine_name: str, sim_itf_spec: SimulatorInterfaceSpec):
    _SIM_INTERFACE_SPECS[machine_name] = sim_itf_spec


def initialize_sim_interface(machine_name: str, machine_mode: MachineMode):
    if machine_name not in _SIM_INTERFACE_SPECS:
        raise RuntimeError(
            f"Simulator interface has not been specified for machine `{machine_name}`"
        )

    sim_itf_spec = _SIM_INTERFACE_SPECS[machine_name]
    itf = create_interface(sim_itf_spec, machine_mode)
    _SIM_INTERFACES[machine_name][machine_mode] = itf


class StringPlane(Enum):
    x = "x"
    y = "y"

    # Aliases for 'x' plane
    X = x
    h = x
    H = x
    horiz = x
    horizontal = x

    # Aliases for 'y' plane
    Y = y
    v = y
    V = y
    vert = y
    vertical = y


class IntegerPlane(Enum):
    x = 0
    y = 1

    # Aliases for 'x' plane
    X = x
    h = x
    H = x
    horiz = x
    horizontal = x

    # Aliases for 'y' plane
    Y = y
    v = y
    V = y
    vert = y
    vertical = y


class SimCalculation(Enum):
    CLOSED_ORBIT = "closed_orbit"
    TUNE = "tune"
