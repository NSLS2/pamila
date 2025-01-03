from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from pydantic import Field

from .. import HlaStage, HlaStageParams
from ...machine import Machine
from ...tiled import TiledUid


class Params(HlaStageParams):
    show_plot: bool = Field(True)
    disp_title: str = Field("")
    chrom_title: str = Field("")
    export_to_file: Path | None = Field(None)


class Stage(HlaStage):
    def __init__(self, machine: Machine):
        super().__init__(machine)

        default_params = self.get_machine_default_params(__name__)

        self.params = Params(**default_params)

    def update_machine_default_params(self, params: Params):
        return super().update_machine_default_params(__name__, params)

    def run(self):
        params = self.params

        if isinstance(self._output_from_prev_stage, TiledUid):
            raise NotImplementedError
        else:
            prev_output = self._output_from_prev_stage

        raw = prev_output["raw_data"]

        spos = raw["orbit"]["s-pos"]
        lin_disp = dict(
            x=prev_output["disp"]["x"][-2].to("mm").m,
            y=prev_output["disp"]["y"][-2].to("mm").m,
        )

        fig = plt.figure()
        plt.subplot(211)
        plt.plot(spos["x"].to("m").m, lin_disp["x"], ".-")
        plt.ylabel(r"$\eta_x \; [\mathrm{mm}]$", size="x-large")
        plt.subplot(212)
        plt.plot(spos["y"].to("m").m, lin_disp["y"], ".-")
        plt.xlabel(r"$s\; [\mathrm{m}]$", size="x-large")
        plt.ylabel(r"$\eta_y\; [\mathrm{mm}]$", size="x-large")
        if params.disp_title:
            fig.suptitle(params.disp_title)
        plt.tight_layout()

        delta = raw["delta"].m
        nu = dict(x=raw["tune"]["x"].m, y=raw["tune"]["y"].m)
        chrom = dict(x=prev_output["chrom"]["x"].m, y=prev_output["chrom"]["y"].m)

        fit_delta = np.linspace(np.min(delta), np.max(delta), 101)
        fit_nu = dict(
            x=np.polyval(chrom["x"], fit_delta), y=np.polyval(chrom["y"], fit_delta)
        )

        fig = plt.figure()
        plt.subplot(211)
        (h,) = plt.plot(delta * 1e2, nu["x"], ".")
        plt.plot(fit_delta * 1e2, fit_nu["x"], "-", color=h.get_color())
        plt.ylabel(r"$\nu_x$", size="x-large")
        plt.subplot(212)
        (h,) = plt.plot(delta * 1e2, nu["y"], ".")
        plt.plot(fit_delta * 1e2, fit_nu["y"], "-", color=h.get_color())
        plt.xlabel(r"$\delta\; [\%]$", size="x-large")
        plt.ylabel(r"$\nu_y$", size="x-large")

        if params.chrom_title:
            fig.suptitle(params.chrom_title)

        plt.tight_layout()

        if params.export_to_file:
            match params.export_to_file.suffix:
                case ".pdf":
                    from matplotlib.backends.backend_pdf import PdfPages

                    pp = PdfPages(params.export_to_file)
                    for fignum in plt.get_fignums():
                        pp.savefig(figure=fignum)
                    pp.close()
                case _:
                    raise NotImplementedError

        if params.show_plot:
            plt.show()
