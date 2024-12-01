from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ..device.simple import FixedWaitTime, SetpointReadbackDiffBase
from ..device.specs import FunctionSpec


class PvIdToReprMap(BaseModel):
    ext: Dict[str, str] = Field(default_factory=dict)
    int: Dict[str, str] = Field(default_factory=dict)


class ConversionFuncSpec(BaseModel):
    in_reprs: List[str]
    out_reprs: List[str]
    func_spec: FunctionSpec


class ExtIntStrList(BaseModel):
    ext: List[str]
    int: List[str]


class MachineModeSpecContainer(BaseModel):
    LIVE: Any | None = None
    DT: Any | None = None
    SIM: Any | None = None


class ParmilaDeviceDefinition(BaseModel):
    type: str


class StandardReadbackDeviceDefinition(ParmilaDeviceDefinition):
    type: str = "standard_RB"


class SetpointReadbackDiffDefinition(SetpointReadbackDiffBase):
    RB_channel: str


class StandardSetpointDeviceDefinition(ParmilaDeviceDefinition):
    type: str = "standard_SP"
    set_wait_method: str = "fixed_wait_time"
    fixed_wait_time: FixedWaitTime = Field(default_factory=FixedWaitTime)
    SP_RB_diff: SetpointReadbackDiffDefinition | None = None


class ChannelSpec(BaseModel):
    handle: str  # "SP" or "RB"
    reprs: List[str]
    pvs: ExtIntStrList
    pdev_def: MachineModeSpecContainer


class PamilaElementDefinition(BaseModel):
    name: str | None = None
    pvid_to_repr_map: PvIdToReprMap = Field(default_factory=PvIdToReprMap)
    repr_units: Dict[str, str] = Field(default_factory=dict)
    func_specs: List[ConversionFuncSpec] = Field(default_factory=list)
    channel_map: Dict[str, ChannelSpec] = Field(
        default_factory=dict
    )  # channel := (field, handle)
