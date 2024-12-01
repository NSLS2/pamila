import time

import numpy as np
from pydantic import Field, field_serializer, field_validator, model_validator
from pydantic_core import PydanticCustomError

from .. import (
    HlaFlow,
    HlaInitialStage,
    HlaStageParams,
    is_machine_default_allowed,
    json_deserialize_HlaFlow,
    json_serialize_HlaFlow,
)
from ... import bluesky_wrapper as bsw
from ...machine import Machine
from ...middle_layer import (
    MiddleLayerVariable,
    MiddleLayerVariableRO,
    MlvName,
    json_deserialize_mlo_name,
)
from ...serialization import (
    json_deserialize_pint_quantity,
    json_serialize_pint_quantity,
)
from ...tiled import TiledWriter, get_client
from ...tiled.write import write_to_tiled
from ...unit import Q_
from ...utils import MACHINE_DEFAULT, MachineDefault


class Params(HlaStageParams):
    rf_freq_mlv_SP: MiddleLayerVariable | MlvName | str = Field(MACHINE_DEFAULT)
    rf_freq_mlv_RB: MiddleLayerVariableRO | MlvName | str | None = Field(None)
    orbit_meas: HlaFlow | None = Field(MACHINE_DEFAULT)
    tune_meas: HlaFlow | None = Field(MACHINE_DEFAULT)
    n_freq_pts: int = Field(5, ge=2)
    max_delta_freq: Q_ = Field(Q_("200 Hz"))
    min_delta_freq: Q_ = Field(Q_("-200 Hz"))
    extra_settle_time: Q_ = Field(Q_("0 s"), ge=Q_("0 s"))
    use_bluesky: bool = Field(False)
    save_to_tiled: bool = Field(False)

    def _assert_freq_range(params):
        min_delta_freq = params.min_delta_freq
        max_delta_freq = params.max_delta_freq
        if max_delta_freq <= min_delta_freq:
            raise PydanticCustomError(
                "freq_range_error", "max_delta_freq must be larger than min_delta_freq"
            )

    def _assert_measurements(params):
        orbit_meas = params.orbit_meas
        tune_meas = params.tune_meas
        if orbit_meas is None and tune_meas is None:
            raise PydanticCustomError(
                "measurement_error",
                "At least one of 'orbit_meas' or 'tune_meas' must not be None",
            )

    @model_validator(mode="after")
    def assert_model(cls, values):
        cls._assert_freq_range(values)
        cls._assert_measurements(values)

        return values

    @field_serializer("max_delta_freq", "min_delta_freq", "extra_settle_time")
    def serialize_pint_quantity(self, value):
        return json_serialize_pint_quantity(value)

    @field_validator(
        "max_delta_freq", "min_delta_freq", "extra_settle_time", mode="before"
    )
    def deserialize_pint_quantity(cls, value):
        return json_deserialize_pint_quantity(value)

    @field_serializer("orbit_meas", "tune_meas")
    def serialize_HlaFlow(self, value):
        if isinstance(value, HlaFlow):
            return json_serialize_HlaFlow(value)
        else:
            return value

    @field_validator("orbit_meas", "tune_meas", mode="before")
    def deserialize_HlaFlow(cls, value):
        return json_deserialize_HlaFlow(value)

    @field_serializer("rf_freq_mlv_SP", "rf_freq_mlv_RB")
    def serialize_mlo(self, value):
        if isinstance(value, MiddleLayerVariable | MiddleLayerVariableRO):
            return MlvName(value.name).json_serialize()
        elif isinstance(value, MlvName):
            return value.json_serialize()
        elif isinstance(value, str | MachineDefault | None):
            return value
        else:
            return TypeError

    @field_validator("rf_freq_mlv_SP", "rf_freq_mlv_RB", mode="before")
    def deserialize_mlo(cls, value):
        if isinstance(value, dict):
            return json_deserialize_mlo_name(value)
        elif value is None:
            return value
        else:
            return value


class Stage(HlaInitialStage):
    def __init__(self, machine: Machine):
        super().__init__(machine)

        default_params = self.get_machine_default_params(__name__)

        params = self.params = Params(**default_params)

        if not is_machine_default_allowed():
            params.rf_freq_mlv_SP = self.ensure_valid_mlo(
                params.rf_freq_mlv_SP, MiddleLayerVariable
            )
            if params.rf_freq_mlv_RB is not None:
                params.rf_freq_mlv_RB = self.ensure_valid_mlo(
                    params.rf_freq_mlv_RB, MiddleLayerVariableRO
                )

    def update_machine_default_params(self, params: Params):
        return super().update_machine_default_params(__name__, params)

    def run(self):
        params = self.params

        # t0 = time.perf_counter()
        params.rf_freq_mlv_SP.wait_for_connection()
        if params.rf_freq_mlv_RB is not None:
            params.rf_freq_mlv_RB.wait_for_connection()
        # print(f"Connection took {time.perf_counter()-t0:.3f} [s]")

        if params.save_to_tiled:
            client = get_client()
            tw = TiledWriter(client)

        if params.use_bluesky:

            subs = {"all": []}
            if params.save_to_tiled:
                subs["all"].append(tw)

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

            raise NotImplementedError
        else:

            if params.rf_freq_mlv_RB is None:
                init_freq = params.rf_freq_mlv_SP.get()
            else:
                init_freq = params.rf_freq_mlv_RB.get()
            freq_array = init_freq + np.linspace(
                params.min_delta_freq, params.max_delta_freq, params.n_freq_pts
            )

            extra_settle_time = params.extra_settle_time.to("s").m

            output = dict(init_freq=init_freq, tune=[], orbit=[], freq_SP=[])
            if params.rf_freq_mlv_RB is not None:
                output["freq_RB"] = []

            for freq in freq_array:
                params.rf_freq_mlv_SP.set_and_wait(freq)
                time.sleep(extra_settle_time)

                output["freq_SP"].append(freq)
                if params.rf_freq_mlv_RB is not None:
                    output["freq_RB"].append(params.rf_freq_mlv_RB.get())
                output["tune"].append(params.tune_meas.run())
                output["orbit"].append(params.orbit_meas.run())

            params.rf_freq_mlv_SP.set_and_wait(init_freq)

            # metadata_kw = {"hla_stage": "orbit.acquire"}
            # write_to_tiled(tw, output, **metadata_kw)

        return output
