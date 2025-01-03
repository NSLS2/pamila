from typing import Literal

import matplotlib.pyplot as plt

from ....hla import HlaStage, HlaStageParams
from ....machine import Machine


class Params(HlaStageParams):
    show_plot: bool = True
    x_axis: Literal["index", "s-pos"] = "index"


class Stage(HlaStage):
    def __init__(self, machine: Machine):
        super().__init__(machine)

        default_params = self.get_machine_default_params(__name__)

        self.params = Params(**default_params)

    def update_machine_default_params(self, params: Params):
        return super().update_machine_default_params(__name__, params)

    def run(self):

        p = self.params

        orb_data = self._output_from_prev_stage
        x_mean = orb_data["x"]["mean"]
        y_mean = orb_data["y"]["mean"]

        plt.figure()
        plt.subplot(211)
        if p.x_axis == "index":
            plt.plot(x_mean, ".-")
        elif p.x_axis == "s-pos":
            plt.plot(orb_data["s-pos"]["x"].to("m"), x_mean, ".-")
            plt.xlabel("")
        plt.ylabel(rf"x [{x_mean.units:~P}]", size="large")
        plt.subplot(212)
        if p.x_axis == "index":
            plt.plot(y_mean, ".-")
        elif p.x_axis == "s-pos":
            plt.plot(orb_data["s-pos"]["y"].to("m"), y_mean, ".-")
        plt.ylabel(rf"y [{y_mean.units:~P}]", size="large")
        if p.x_axis == "index":
            plt.xlabel("BPM Index")
        elif p.x_axis == "s-pos":
            plt.xlabel("s [m]")
        plt.tight_layout()

        if p.show_plot:
            plt.show()
