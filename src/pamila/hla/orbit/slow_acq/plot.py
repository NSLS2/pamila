import matplotlib.pyplot as plt

from ....hla import HlaStage, HlaStageParams
from ....machine import Machine


class Params(HlaStageParams):
    pass


class Stage(HlaStage):
    def __init__(self, machine: Machine):
        super().__init__(machine)

    def update_machine_default_params(self, params: Params):
        return super().update_machine_default_params(__name__, params)

    def run(self):

        orb_data = self._output_from_prev_stage
        x_mean = orb_data["x"]["mean"]
        y_mean = orb_data["y"]["mean"]

        plt.figure()
        plt.subplot(211)
        plt.plot(x_mean, ".-")
        plt.ylabel(rf"x [{x_mean.units:~P}]", size="large")
        plt.subplot(212)
        plt.plot(y_mean, ".-")
        plt.ylabel(rf"y [{y_mean.units:~P}]", size="large")
        plt.xlabel("BPM Index")
        plt.tight_layout()

        plt.show()
