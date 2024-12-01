from typing import Dict

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from ophyd import Device

from . import TiledWriter
from .. import USERNAME
from ..bluesky_wrapper.run_engine import (  # This `RE` is a modified version of RunEngine
    RE,
)
from ..machine_modes import get_machine_mode
from ..serialization import json_serialize_pint_quantity
from ..signal import UserPamilaSignal


def write_to_tiled(tw: TiledWriter, dict_to_write: Dict, **metadata_kw):

    raise NotImplementedError

    assert isinstance(tw, TiledWriter)

    class TempDevice(Device):
        pass

    temp_dev = TempDevice(name="temp", prefix=USERNAME)
    for k, v in dict_to_write.items():
        name = f"{temp_dev.prefix}_{k}"
        # setattr(temp_dev, k, Signal(name=name, value=v))
        setattr(
            temp_dev, k, UserPamilaSignal(mode=get_machine_mode(), name=name, value=v)
        )

        if False:
            import json

            tw.client.write_array(
                json.dumps(json_serialize_pint_quantity(v["raw"])),
                metadata={"color": "red"},
            )

            tw.client.write_awkward(v["raw"].m, metadata={"color": "red"})
            tw.client.write_awkward(dict(x=1, y=[3, 5]), metadata={"color": "red"})

            from tiled.queries import Key

            data = list(tw.client.search(Key("color") == "red").values())[-1]
            out = data[:]
            for v in tw.client.search(Key("color") == "red").values():
                print(v[:])

    @bpp.set_run_key_decorator("insert_data")
    @bpp.run_decorator(md={})
    def insert_data():
        yield from bps.create("primary")

        for k, v in dict_to_write.items():
            sig = getattr(temp_dev, k)
            yield from bps.read(sig)

        yield from bps.save()

    subs = {"all": tw}
    (uid,) = RE(insert_data(), subs, **metadata_kw)

    if True:
        print(tw.client[uid]["primary"]["internal"]["events"].read())

    return uid
