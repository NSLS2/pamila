from ....hla import HlaStage
from ....machine import Machine
from ....tiled import TiledUid


class Stage(HlaStage):
    def __init__(self, machine: Machine):
        super().__init__(machine)

    def run(self):
        if isinstance(self._output_from_prev_stage, TiledUid):
            raise NotImplementedError
        else:
            return self._output_from_prev_stage
