from datetime import datetime
import time


class Timer:
    def __init__(self, name=""):
        self.name: str = name
        self._stopped: bool = False
        self.start_wall_clock: datetime = datetime.now()
        self.end_wall_clock: datetime | None = None
        self.t_start = time.perf_counter()

    def _lap_or_stop(self, stop: bool):
        if self._stopped:
            raise RuntimeError("This timer has been already stopped.")
        self.raw_dt = time.perf_counter() - self.t_start
        if stop:
            self.end_wall_clock = datetime.now()
            self._stopped = True
        return self.total_seconds()

    def lap(self):
        return self._lap_or_stop(False)

    def stop(self):
        return self._lap_or_stop(True)

    def total_seconds(self):
        return self.raw_dt

    def print(self, decimal: int = 1):
        dt = self.raw_dt
        print(f"Elapsed ({self.name}) = {dt:.{decimal}f} [s]")

    def get_start_time_str(self):
        return self.start_wall_clock.strftime("%Y%m%dT%H%M%S.%f")

    def get_end_time_str(self):
        if self.end_wall_clock is None:
            raise RuntimeError("You have not stopped the timer yet")
        return self.end_wall_clock.strftime("%Y%m%dT%H%M%S.%f")


class TimerDict(dict):
    def start(self, name, exist_ok: bool = True):
        if (not exist_ok) and (name in self):
            raise ValueError(
                f'Another timer with the same name "{name}" already exists'
            )
        timer = Timer(name)
        self[name] = timer
        return self

    def print(self, decimal: int = 3):
        for v in self.values():
            v.print(decimal=decimal)

    def __enter__(self):
        if "name" not in self._timeit_kwargs:
            raise RuntimeError(
                "You must use context like 'with TimerDict().timeit(label):'."
            )
        self.start(
            self._timeit_kwargs["name"], exist_ok=self._timeit_kwargs["exist_ok"]
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):

        self[self._timeit_kwargs["name"]].stop()
        self._timeit_kwargs.clear()

    def timeit(self, name, exist_ok: bool = True):
        self._timeit_kwargs = dict(name=name, exist_ok=exist_ok)
        return self
