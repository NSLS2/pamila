from collections.abc import Sequence
import time

from pydantic import Field, field_serializer, field_validator

from .... import bluesky_wrapper as bsw
from ....hla import (
    HlaInitialStage,
    RepeatMeasHlaStageParams,
    is_machine_default_allowed,
)
from ....machine import Machine
from ....middle_layer import (
    MiddleLayerVariableListRO,
    MiddleLayerVariableTree,
    MloName,
    MlvlName,
    MlvtName,
    json_deserialize_mlo_name,
)
from ....tiled import TiledWriter, get_client
from ....tiled.write import write_to_tiled
from ....unit import Q_
from ....utils import MACHINE_DEFAULT, MachineDefault, StatisticsType


class Params(RepeatMeasHlaStageParams):
    n_meas: int = Field(5, ge=1, description="Number of orbit measurements to acquire")
    wait_btw_meas: Q_ = Field(
        Q_("0.2 s"), ge=Q_("0 s"), description="Wait time between each measurement"
    )
    stats: StatisticsType | Sequence[StatisticsType] = Field(
        (
            StatisticsType.MEAN,
            StatisticsType.STD,
            StatisticsType.MIN,
            StatisticsType.MAX,
        )
    )
    bpm_mlo: MiddleLayerVariableListRO | MiddleLayerVariableTree | MloName | str = (
        Field(MACHINE_DEFAULT)
    )
    use_bluesky: bool = Field(False)
    save_to_tiled: bool = Field(False)

    @field_serializer("bpm_mlo")
    def serialize_mlo(self, value):
        if isinstance(value, MiddleLayerVariableListRO):
            return MlvlName(value.name).json_serialize()
        elif isinstance(value, MiddleLayerVariableTree):
            return MlvtName(value.name).json_serialize()
        elif isinstance(value, MloName):
            return value.json_serialize()
        elif isinstance(value, str | MachineDefault):
            return value
        else:
            return TypeError

    @field_validator("bpm_mlo", mode="before")
    def deserialize_mlo(cls, value):
        if isinstance(value, dict):
            return json_deserialize_mlo_name(value)
        else:
            return value


class Stage(HlaInitialStage):
    def __init__(self, machine: Machine):
        super().__init__(machine)

        default_params = self.get_machine_default_params(__name__)

        self.params = Params(**default_params)

        if not is_machine_default_allowed():
            self.params.bpm_mlo = self.ensure_valid_mlo(
                self.params.bpm_mlo, MiddleLayerVariableListRO | MiddleLayerVariableTree
            )

    def update_machine_default_params(self, params: Params):
        return super().update_machine_default_params(__name__, params)

    def run(self):
        params = self.params

        # t0 = time.perf_counter()
        params.bpm_mlo.wait_for_connection()
        # print(f"Connection took {time.perf_counter()-t0:.3f} [s]")

        if params.save_to_tiled:

            client = get_client()
            tw = TiledWriter(client)

        if params.use_bluesky:

            # subs = {"all": [tw, LiveTable(sel_odevs)]}
            subs = {"all": []}
            if params.save_to_tiled:
                subs["all"].append(tw)

            if False:
                output = bsw.rel_put_then_get(
                    obj_list_to_get=[params.bpm_mlo],
                    obj_list_to_put=None,
                    vals_to_put=None,
                    n_repeat=params.n_meas,
                    wait_time_btw_read=params.wait_btw_meas.to("s").m,
                    subs=subs,
                    ret_raw=True,
                    stats_types=params.stats,
                )
            else:
                output = bsw.get(
                    [params.bpm_mlo],
                    n_repeat=params.n_meas,
                    wait_time_btw_read=params.wait_btw_meas.to("s").m,
                    subs=subs,
                    ret_raw=True,
                    stats_types=params.stats,
                )

            raise NotImplementedError
        else:
            bpm_mlo = params.bpm_mlo

            results = []
            for i in range(params.n_meas):
                t0 = time.perf_counter()
                results.append(bpm_mlo.get())
                if i != params.n_meas - 1:
                    time.sleep(max([0.0, time.perf_counter() - t0]))

            if isinstance(bpm_mlo, MiddleLayerVariableTree):
                output = bpm_mlo.compute_stats(results)
            elif isinstance(bpm_mlo, MiddleLayerVariableListRO):
                raise NotImplementedError
            else:
                raise TypeError

            # metadata_kw = {"hla_stage": "orbit.acquire"}
            # write_to_tiled(tw, output, **metadata_kw)

        return output
