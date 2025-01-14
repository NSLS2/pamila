from copy import deepcopy
from functools import partial
import inspect
from pathlib import Path
import time
from typing import Literal

import click

import pamila as pml
from pamila.middle_layer import (
    MiddleLayerVariableList,
    MiddleLayerVariableListRO,
    MiddleLayerVariableListROSpec,
    MiddleLayerVariableListSpec,
)
from pamila.timer import TimerDict


@click.group()
def cli():
    pass


def connect_online_mlvs(mlvs_dict, mlvl=None):

    import pamila as pml

    Q_ = pml.unit.Q_

    if False:  # slow (sequential) version (~20 s for production)
        for mlv in mlvs_dict.values():
            mlv.wait_for_connection()
    elif True:  # faster (parallel) version (~2 s for production)
        args = [[], [], {}]
        for mlv in mlvs_dict.values():
            _mlv_names, _sigs, _pend_funcs = mlv.get_connection_check_args()
            args[0].extend(_mlv_names)
            args[1].extend(_sigs)
            args[2].update(_pend_funcs)
        try:
            pml.middle_layer._wait_for_connection(*args, timeout=Q_("20 s"))
        except TimeoutError:
            pml.middle_layer._wait_for_connection(*args, timeout=Q_("20 s"))
    else:  # about the same as "faster"
        mlvl.wait_for_connection(all_modes=False)


def _enable_internal_conversions(mlvl):
    for mlv in mlvl.get_all_mlvs():
        mlv.get_device()._internal_conv_enabled = True


def _disable_internal_conversions(mlvl):
    for mlv in mlvl.get_all_mlvs():
        mlv.get_device()._internal_conv_enabled = False


def for_loop_mlv_get(
    timer_d,
    timer_label_prefix,
    mlv_list,
    mlvl: MiddleLayerVariableListRO,
    n=3,
    mode: Literal["normal", "auto_monitor", "parallel"] = "normal",
):

    match mode:
        case "normal" | "normal_wo_internal_conv":
            mlvl.turn_off_PV_auto_monitors()
            mlvl.disable_parallel_get()
        case "auto_monitor" | "auto_monitor_wo_internal_conv":
            mlvl.turn_on_PV_auto_monitors()
            mlvl.disable_parallel_get()
        case "parallel" | "parallel_wo_internal_conv":
            mlvl.turn_off_PV_auto_monitors()
            mlvl.enable_parallel_get()
        case _:
            raise NotImplementedError

    if mode.endswith("_wo_internal_conv"):
        _disable_internal_conversions(mlvl)
    else:
        _enable_internal_conversions(mlvl)

    time.sleep(1.0)

    data_list = []
    for i_meas in range(n):
        match mode:
            case (
                "normal"
                | "auto_monitor"
                | "normal_wo_internal_conv"
                | "auto_monitor_wo_internal_conv"
            ):
                with timer_d.timeit(f"{timer_label_prefix} #{i_meas+1}"):
                    data = [mlv.get() for mlv in mlv_list]
            case "parallel" | "parallel_wo_internal_conv":
                with timer_d.timeit(f"{timer_label_prefix} #{i_meas+1}"):
                    data = mlvl.get()
            case _:
                raise NotImplementedError

        data_list.append(data)

    ref_data = data_list[0]
    diff_list = [[v1 - v2 for v1, v2 in zip(data, ref_data)] for data in data_list[1:]]

    return data_list, diff_list


@cli.command(name="test_mlv_list_online_get")
def cli_test_mlv_list_online_get():
    func_name = inspect.currentframe().f_code.co_name
    output_filepath = Path(f"{func_name[4:]}_result.txt")
    test_mlv_list_get(True, output_filepath)


@cli.command(name="test_mlv_list_offline_get")
def cli_test_mlv_list_offline_get():
    func_name = inspect.currentframe().f_code.co_name
    output_filepath = Path(f"{func_name[4:]}_result.txt")
    test_mlv_list_get(False, output_filepath)


def test_mlv_list_get(online: bool, output_filepath: Path):

    timer_d = TimerDict()

    lines = ["# Online MLV get speed", ""]

    machine_name = "SR"
    cache_filepath = Path("test_SR_obj_production.pgz")

    with timer_d.timeit("Cached loading"):
        SR = pml.load_cached_machine(machine_name, cache_filepath)

    bpm_mlvs = SR.get_mlvs_via_value_tag("BPM")

    scors_I_RB = SR.get_mlvs_via_name(r"C\d\d_C\d_[xy]_I_RB", search_type="regex")
    scors_angle_RB = SR.get_mlvs_via_name(
        r"C\d\d_C\d_[xy]_angle_RB", search_type="regex"
    )
    scors_I_SP = SR.get_mlvs_via_name(r"C\d\d_C\d_[xy]_I_SP", search_type="regex")
    scors_angle_SP = SR.get_mlvs_via_name(
        r"C\d\d_C\d_[xy]_angle_SP", search_type="regex"
    )
    assert (
        len(scors_I_RB) == len(scors_I_SP) == len(scors_angle_RB) == len(scors_angle_SP)
    )

    all_mlvs = deepcopy(bpm_mlvs)
    all_mlvs.update(scors_I_RB)
    all_mlvs.update(scors_angle_RB)
    all_RB_mlvs = deepcopy(all_mlvs)
    all_mlvs.update(scors_I_SP)
    all_mlvs.update(scors_angle_SP)

    use_all_combined_connection = True
    if not use_all_combined_connection:
        all_mlvs_list = [
            bpm_mlvs,
            scors_I_RB,
            scors_I_SP,
            scors_angle_RB,
            scors_angle_SP,
        ]

    bpm_mlv_list = list(bpm_mlvs.values())
    spec = MiddleLayerVariableListROSpec(
        name="bpms_xy", exist_ok=False, mlvs=bpm_mlv_list
    )
    bpm_mlvl = MiddleLayerVariableListRO(spec)

    scor_I_RB_mlv_list = list(scors_I_RB.values())
    spec = MiddleLayerVariableListROSpec(
        name="scors_xy_I_RB", exist_ok=False, mlvs=scor_I_RB_mlv_list
    )
    scors_I_RB_mlvl = MiddleLayerVariableListRO(spec)

    scor_angle_RB_mlv_list = list(scors_angle_RB.values())
    spec = MiddleLayerVariableListROSpec(
        name="scors_xy_angle_RB", exist_ok=False, mlvs=scor_angle_RB_mlv_list
    )
    scors_angle_RB_mlvl = MiddleLayerVariableListRO(spec)

    scor_I_SP_mlv_list = list(scors_I_SP.values())
    spec = MiddleLayerVariableListSpec(
        name="scors_xy_I_SP", exist_ok=False, mlvs=scor_I_SP_mlv_list
    )
    scors_I_SP_mlvl = MiddleLayerVariableList(spec)

    scor_angle_SP_mlv_list = list(scors_angle_SP.values())
    spec = MiddleLayerVariableListSpec(
        name="scors_xy_angle_SP", exist_ok=False, mlvs=scor_angle_SP_mlv_list
    )
    scors_angle_SP_mlvl = MiddleLayerVariableList(spec)

    spec = MiddleLayerVariableListROSpec(
        name="all_RB_mlvs", exist_ok=False, mlvs=list(all_RB_mlvs.values())
    )
    all_RB_mlvl = MiddleLayerVariableListRO(spec)

    if False:
        spec = MiddleLayerVariableListROSpec(
            name="all_mlvs", exist_ok=False, mlvs=list(all_mlvs.values())
        )
        all_mlvl = MiddleLayerVariableListRO(spec)

    if online:
        pml.go_online()
    else:
        pml.go_offline()

    with timer_d.timeit("Connection"):
        if use_all_combined_connection:
            connect_online_mlvs(all_mlvs)
        else:
            for _mlvs in all_mlvs_list:
                connect_online_mlvs(_mlvs)

    spacer_counter = 0
    for dev_type, mlvl in [
        ("BPM", bpm_mlvl),
        ("SCOR-I-RB", scors_I_RB_mlvl),
        ("SCOR-I-SP", scors_I_SP_mlvl),
        ("SCOR-angle-RB", scors_angle_RB_mlvl),
        ("SCOR-angle-SP", scors_angle_SP_mlvl),
        ("All_RB", all_RB_mlvl),
        # ("All", all_mlvl),
    ]:
        mlv_list = mlvl.get_all_mlvs()

        data_list, diff_list = for_loop_mlv_get(
            timer_d,
            f"{dev_type} for_loop (auto_monitor=False, internal_conv=True)",
            mlv_list,
            mlvl,
            n=3,
            mode="normal",
        )

        data_list, diff_list = for_loop_mlv_get(
            timer_d,
            f"{dev_type} for_loop (auto_monitor=False, internal_conv=False)",
            mlv_list,
            mlvl,
            n=3,
            mode="normal_wo_internal_conv",
        )

        data_list, diff_list = for_loop_mlv_get(
            timer_d,
            f"{dev_type} for_loop (auto_monitor=True, internal_conv=True)",
            mlv_list,
            mlvl,
            n=3,
            mode="auto_monitor",
        )

        data_list, diff_list = for_loop_mlv_get(
            timer_d,
            f"{dev_type} for_loop (auto_monitor=True, internal_conv=False)",
            mlv_list,
            mlvl,
            n=3,
            mode="auto_monitor_wo_internal_conv",
        )

        data_list, diff_list = for_loop_mlv_get(
            timer_d,
            f"{dev_type} parallel, internal_conv=True",
            mlv_list,
            mlvl,
            n=3,
            mode="parallel",
        )

        data_list, diff_list = for_loop_mlv_get(
            timer_d,
            f"{dev_type} parallel, internal_conv=False",
            mlv_list,
            mlvl,
            n=3,
            mode="parallel_wo_internal_conv",
        )

        spacer_counter += 1
        timer_d[f"spacer_{spacer_counter}"] = None

    timer_d.print(decimal=3)

    lines.extend(timer_d.get_print_lines(decimal=3))
    lines.append("")
    output_filepath.write_text("\n".join(lines))

    print("Finished")


if __name__ == "__main__":
    cli()
