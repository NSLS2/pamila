import asyncio

from bluesky import RunEngine
from bluesky.utils import Msg

from ..timer import TimerDict


class ModifiedRunEngine(RunEngine):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._command_registry["parallel_read"] = self._parallel_read

    async def _parallel_read(self, msg):
        devices = msg.obj

        # read_method = self._read
        read_method = self._profiled_read

        tasks = [read_method(Msg("read", dev)) for dev in devices]
        results = await asyncio.gather(*tasks)
        return results

    async def _profiled_read(self, msg):
        """
        Exactly the same as the original `_read` except that this profiles.
        """

        from bluesky.bundlers import maybe_await
        from bluesky.protocols import Readable, check_supports
        from bluesky.utils import warn_if_msg_args_or_kwargs

        timer_d = TimerDict()

        timer_d.start("check_supports")
        obj = check_supports(msg.obj, Readable)
        timer_d["check_supports"].stop()
        # actually _read_ the object
        timer_d.start("warn_if_msg_args_or_kwargs")
        warn_if_msg_args_or_kwargs(msg, obj.read, msg.args, msg.kwargs)
        timer_d["warn_if_msg_args_or_kwargs"].stop()
        timer_d.start("maybe_await")
        ret = await maybe_await(obj.read(*msg.args, **msg.kwargs))
        timer_d["maybe_await"].stop()

        if ret is None:
            raise RuntimeError(
                f"The read of {obj.name} returned None. "
                "This is a bug in your object implementation, "
                "`read` must return a dictionary."
            )
        run_key = msg.run
        timer_d.start("_run_bundlers.get")
        current_run = self._run_bundlers.get(run_key, key_absence_sentinel := object())
        timer_d["_run_bundlers.get"].stop()
        if current_run is not key_absence_sentinel:
            timer_d.start("current_run.read")
            await current_run.read(msg, ret)
            timer_d["current_run.read"].stop()

        if False:
            for v in timer_d.values():
                v.print()

        return ret


# RE = RunEngine()
RE = ModifiedRunEngine()
