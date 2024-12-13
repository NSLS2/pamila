from . import base, simple


def _get_pdev_class_from_spec(spec: base.PamilaDeviceBaseSpec):

    match type(spec):
        case simple.SimplePamilaDeviceSpec:
            return simple.SimplePamilaDevice
        case simple.SimplePamilaDeviceROSpec:
            return simple.SimplePamilaDeviceRO
        case _:
            raise NotImplementedError


def create_pamila_device_from_spec(spec: base.PamilaDeviceBaseSpec):

    sel_class = _get_pdev_class_from_spec(spec)
    ophyd_device_kwargs = {}
    return sel_class(spec, **ophyd_device_kwargs)
