from importlib.metadata import version

__version__ = version("pamila")
del version

__all__ = [
    "__version__",
]

import getpass

USERNAME = getpass.getuser()

# isort: off
from . import ophyd_shim

# isort: on

from . import serialization, tiled, unit, utils
from .unit import Q_, Unit

# The following import orders MUST NOT be changed in order to avoid circular imports.

# isort: off

from .machine_modes import (
    MachineMode,
    get_machine_mode,
    set_machine_mode,
    set_offline_mode,
    set_online_mode,
    go_offline,
    go_online,
    is_online,
)

from . import sim_interface
from . import middle_layer
from . import machine
from .machine import load_machine, load_cached_machine
from . import signal
from . import hla
from .hla import load_hla_defaults
from . import bluesky_wrapper

bsw = bluesky_wrapper
