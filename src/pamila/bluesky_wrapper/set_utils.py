import time
from typing import Dict

import bluesky.plan_stubs as bps
import numpy as np
from ophyd import Signal, SignalRO


class SetMode:
    jump: bool = True

    def __init__(self):
        self.ramp_opts = {}
        self.ramp_opts["num_steps"] = (
            None  # If None, this value is calculated based on signal.max_jump_size
        )
        self.ramp_opts["interval"] = None  # If None, use signal.min_set_interval
        self.ramp_opts["current_val_signals"] = (
            None  # If None, use signal.current_val_signal
        )
        self.ramp_opts["wait_at_each_step"] = (
            True  # If True, will use "wait=True" for each step
        )


class JumpSet(SetMode):
    pass


class RampSet(SetMode):

    def __init__(
        self,
        num_steps: int | None = None,
        interval: float | None = None,
        current_val_signals: Dict[Signal | SignalRO, float] | None = None,
        wait_at_each_step: bool = True,
    ):
        super().__init__()

        self.jump = False

        self.ramp_opts["num_steps"] = num_steps
        self.ramp_opts["interval"] = interval
        self.ramp_opts["current_val_signals"] = current_val_signals
        self.ramp_opts["wait_at_each_step"] = wait_at_each_step


def wait_optional_move_per_step(step, pos_cache, wait=True):
    """
    Based on bps.move_per_step(). The only difference is the additional option
    "wait".


    Inner loop of an N-dimensional step scan without any readings

    This can be used as a building block for custom ``per_step`` stubs.

    Parameters
    ----------
    step : dict
        mapping motors to positions in this step
    pos_cache : dict
        mapping motors to their last-set positions
    """

    Msg = bps.Msg
    _short_uid = bps._short_uid

    yield Msg("checkpoint")
    grp = _short_uid("set")
    for motor, pos in step.items():
        if pos == pos_cache[motor]:
            # This step does not move this motor.
            continue
        yield Msg("set", motor, pos, group=grp)
        pos_cache[motor] = pos

    if wait:
        yield Msg("wait", None, group=grp)


def ramp_set(step, pos_cache, set_mode, initial_positions, wait=True):

    ramp_opts = set_mode.ramp_opts

    current_abs_vals = {}
    if ramp_opts["current_val_signals"] is None:
        for motor in step.keys():
            try:
                current_val_signal = motor.current_val_signal
            except AttributeError:
                current_val_signal = motor
            current_abs_vals[motor] = current_val_signal.get()
    else:
        for motor in step.keys():
            if motor in ramp_opts["current_val_signals"]:
                current_val_signal = ramp_opts["current_val_signals"][motor]
            else:
                current_val_signal = motor
            current_abs_vals[motor] = current_val_signal.get()

    abs_steps = {}
    if initial_positions is None:
        for motor, pos in step.items():
            abs_steps[motor] = pos
    else:
        if initial_positions == {}:
            for motor, v in current_abs_vals.items():
                initial_positions[motor] = v

        for motor, pos_change in step.items():
            abs_steps[motor] = initial_positions[motor] + pos_change

    if ramp_opts["num_steps"] is None:
        num_steps = 1  # minimum is 1
        for motor, abs_step in abs_steps.items():
            try:
                max_jump_size = motor.max_jump_size
            except AttributeError:
                max_jump_size = None

            if max_jump_size is not None:
                v = current_abs_vals[motor]
                new_num_steps = int(np.ceil(np.abs(abs_step - v) / max_jump_size))
                if new_num_steps > num_steps:
                    num_steps = new_num_steps
    else:
        num_steps = ramp_opts["num_steps"]

    ramp_table_d = {}
    for motor, cur_abs_v in current_abs_vals.items():
        abs_ramp_table = np.linspace(cur_abs_v, abs_steps[motor], num_steps + 1)[1:]
        assert abs_ramp_table.size == num_steps
        if initial_positions is None:
            ramp_table = abs_ramp_table
        else:
            ramp_table = abs_ramp_table - initial_positions[motor]

        ramp_table_d[motor] = ramp_table

    ramp_step_list = []
    for i in range(num_steps):
        ramp_step_list.append(
            {motor: array[i] for motor, array in ramp_table_d.items()}
        )

    min_ramp_interval = 0.0
    for motor in step.keys():
        try:
            if motor.min_set_interval > min_ramp_interval:
                min_ramp_interval = motor.min_set_interval
        except AttributeError:
            pass

    if ramp_opts["interval"] is None:
        ramp_interval = min_ramp_interval
    else:
        ramp_interval = max([ramp_opts["interval"], min_ramp_interval])

    for i, next_step in enumerate(ramp_step_list):
        t_start = time.perf_counter()

        if i + 1 != num_steps:
            _wait = ramp_opts["wait_at_each_step"]
            print(f"Ramping step {i+1}/{num_steps}")
        else:  # Always wait at the last step as expected for "scan"
            _wait = True
            print(f"Ramping final step")

        yield from wait_optional_move_per_step(next_step, pos_cache, wait=_wait)

        if i + 1 != num_steps:
            dt = time.perf_counter() - t_start
            yield from bps.sleep(max([ramp_interval - dt, 0.0]))
