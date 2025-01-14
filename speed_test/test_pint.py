import inspect
from pathlib import Path
import timeit

import click


@click.group()
def cli():
    pass


@cli.command(name="test_pint_Q_creation")
def cli_test_pint_Q_creation():
    test_pint_Q_creation()


def test_pint_Q_creation():

    func_name = inspect.currentframe().f_code.co_name
    output_filepath = Path(f"{func_name}_result.txt")

    import pint

    ureg = pint.UnitRegistry()
    Q_ = ureg.Quantity

    # N = 10_000
    N = 100_000

    lines = ["# pint.Quantity creation speed", f"# {N = :_}", ""]

    one_meter = Q_("1 meter")
    one_m = Q_("1 m")
    one_millimeter = Q_("1 millimeter")
    one_mm = Q_("1 mm")

    global_d = dict(
        ureg=ureg,
        Q_=Q_,
        one_meter=one_meter,
        one_m=one_m,
        one_millimeter=one_millimeter,
        one_mm=one_mm,
    )

    times_d = {}

    for cmd, g_keys in [
        ("42.0 * ureg('meter')", ["ureg"]),
        ("42.0 * ureg('m')", ["ureg"]),
        ("42.0 * ureg.meter", ["ureg"]),
        ("42.0 * ureg.m", ["ureg"]),
        ("42.0 * one_meter", ["one_meter"]),
        ("42.0 * one_m", ["one_m"]),
        ("Q_('42.0 meter')", ["Q_"]),
        ("Q_('42.0 m')", ["Q_"]),
        ("Q_(42.0, 'meter')", ["Q_"]),
        ("Q_(42.0, 'm')", ["Q_"]),
        ("Q_(42.0, ureg.meter)", ["Q_", "ureg"]),
        ("Q_(42.0, ureg.m)", ["Q_", "ureg"]),
        ("42.0 * Q_('1 meter')", ["Q_"]),
        ("42.0 * Q_('1 m')", ["Q_"]),
        ("spacer_1", None),
        ("42.0 * ureg('millimeter')", ["ureg"]),
        ("42.0 * ureg('mm')", ["ureg"]),
        ("42.0 * ureg.millimeter", ["ureg"]),
        ("42.0 * ureg.mm", ["ureg"]),
        ("42.0 * one_millimeter", ["one_millimeter"]),
        ("42.0 * one_mm", ["one_mm"]),
        ("Q_('42.0 millimeter')", ["Q_"]),
        ("Q_('42.0 mm')", ["Q_"]),
        ("Q_(42.0, 'millimeter')", ["Q_"]),
        ("Q_(42.0, 'mm')", ["Q_"]),
        ("Q_(42.0, ureg.millimeter)", ["Q_", "ureg"]),
        ("Q_(42.0, ureg.mm)", ["Q_", "ureg"]),
        ("42.0 * Q_('1 millimeter')", ["Q_"]),
        ("42.0 * Q_('1 mm')", ["Q_"]),
    ]:
        if g_keys is None:
            times_d[cmd] = None
            continue

        g_d = {k: global_d[k] for k in g_keys}
        times_d[cmd] = timeit.timeit(cmd, globals=g_d, number=N)

    for cmd, v in times_d.items():
        if v is None:
            lines.append("")
        else:
            lines.append(f"{cmd} :: {v:.3f} [s]")
        print(lines[-1])
    lines.append("")
    output_filepath.write_text("\n".join(lines))


@cli.command(name="test_pint_conversion")
def cli_test_pint_conversion():
    test_pint_conversion()


def test_pint_conversion():

    func_name = inspect.currentframe().f_code.co_name
    output_filepath = Path(f"{func_name}_result.txt")

    import pint

    ureg = pint.UnitRegistry()
    Q_ = ureg.Quantity

    # N = 10_000
    # N = 100_000
    N = 1_000_000

    lines = ["# pint.Quantity conversion speed", f"# {N = :_}", ""]

    forty_two_mm = Q_("42.0 mm")
    forty_two_meter = Q_("42.0 meter")

    global_d = dict(
        forty_two_mm=forty_two_mm, forty_two_meter=forty_two_meter, Q_=Q_, ureg=ureg
    )

    times_d = {}

    for cmd, g_keys in [
        ("forty_two_mm.to('meter')", ["forty_two_mm"]),
        ("forty_two_mm.to('m')", ["forty_two_mm"]),
        ("Q_(forty_two_mm, 'meter')", ["forty_two_mm", "Q_"]),
        ("Q_(forty_two_mm, 'm')", ["forty_two_mm", "Q_"]),
        ("forty_two_mm.to(ureg.meter)", ["forty_two_mm", "ureg"]),
        ("forty_two_mm.to(ureg.m)", ["forty_two_mm", "ureg"]),
        ("Q_(forty_two_mm, ureg.meter)", ["forty_two_mm", "ureg", "Q_"]),
        ("Q_(forty_two_mm, ureg.m)", ["forty_two_mm", "ureg", "Q_"]),
        ("forty_two_mm.m * 1e-3", ["forty_two_mm"]),
        ("spacer_1", None),
        ("forty_two_meter.to('millimeter')", ["forty_two_meter"]),
        ("forty_two_meter.to('mm')", ["forty_two_meter"]),
        ("Q_(forty_two_meter, 'millimeter')", ["forty_two_meter", "Q_"]),
        ("Q_(forty_two_meter, 'mm')", ["forty_two_meter", "Q_"]),
        ("forty_two_meter.to(ureg.millimeter)", ["forty_two_meter", "ureg"]),
        ("forty_two_meter.to(ureg.mm)", ["forty_two_meter", "ureg"]),
        ("Q_(forty_two_meter, ureg.millimeter)", ["forty_two_meter", "ureg", "Q_"]),
        ("Q_(forty_two_meter, ureg.mm)", ["forty_two_meter", "ureg", "Q_"]),
        ("forty_two_meter.m * 1e3", ["forty_two_meter"]),
        ("spacer_2", None),
        ("forty_two_meter.to('meter')", ["forty_two_meter"]),
        ("forty_two_mm.to('millimeter')", ["forty_two_mm"]),
    ]:
        if g_keys is None:
            times_d[cmd] = None
            continue

        g_d = {k: global_d[k] for k in g_keys}
        times_d[cmd] = timeit.timeit(cmd, globals=g_d, number=N)

    for cmd, v in times_d.items():
        if v is None:
            lines.append("")
        else:
            lines.append(f"{cmd} :: {v:.3f} [s]")
        print(lines[-1])
    lines.append("")
    output_filepath.write_text("\n".join(lines))


@cli.command(name="test_pint_conv_fac_extraction")
def cli_test_pint_conv_fac_extraction():
    test_pint_conv_fac_extraction()


def test_pint_conv_fac_extraction():

    func_name = inspect.currentframe().f_code.co_name
    output_filepath = Path(f"{func_name}_result.txt")

    import pint

    ureg = pint.UnitRegistry()
    Q_ = ureg.Quantity

    # N = 10_000
    N = 100_000

    lines = ["# pint.Quantity conversion factor extraction speed", f"# {N = :_}", ""]

    forty_two_meter = 42.0 * ureg.meter
    forty_two_mm = 42.0 * ureg.millimeter
    meter_str = "meter"
    m_str = "m"
    millimeter_str = "millimeter"
    mm_str = "mm"
    meter_unit = ureg.meter
    m_unit = ureg.m
    millimeter_unit = ureg.millimeter
    mm_unit = ureg.mm

    def method1(v1, v2):
        fac_Q = (1.0 * v1.to(v2).units / v1.units).to_base_units()
        assert fac_Q.dimensionless
        fac = fac_Q.m

    def method2(v1, v2):
        fac_Q = (1.0 * (v1.to(v2).units / v1.units)).to_base_units()
        assert fac_Q.dimensionless
        fac = fac_Q.m

    def method3(v1, v2):
        forty_two_q = Q_(42.0, v1)
        fac = forty_two_q.to(v2).m

    global_d = dict(
        Q_=Q_,
        method1=method1,
        method2=method2,
        method3=method3,
        forty_two_meter=forty_two_meter,
        forty_two_mm=forty_two_mm,
        meter_str=meter_str,
        m_str=m_str,
        millimeter_str=millimeter_str,
        mm_str=mm_str,
        meter_unit=meter_unit,
        m_unit=m_unit,
        millimeter_unit=millimeter_unit,
        mm_unit=mm_unit,
    )

    times_d = {}

    for cmd, g_keys in [
        (
            "method1(forty_two_meter, millimeter_str)",
            ["method1", "forty_two_meter", "millimeter_str"],
        ),
        ("method1(forty_two_meter, mm_str)", ["method1", "forty_two_meter", "mm_str"]),
        (
            "method2(forty_two_meter, millimeter_str)",
            ["method2", "forty_two_meter", "millimeter_str"],
        ),
        ("method2(forty_two_meter, mm_str)", ["method2", "forty_two_meter", "mm_str"]),
        (
            "method3(meter_str, millimeter_str)",
            ["Q_", "method3", "meter_str", "millimeter_str"],
        ),
        ("method3(meter_str, mm_str)", ["Q_", "method3", "meter_str", "mm_str"]),
        (
            "method3(meter_str, millimeter_unit)",
            ["Q_", "method3", "meter_str", "millimeter_unit"],
        ),
        ("method3(meter_str, mm_unit)", ["Q_", "method3", "meter_str", "mm_unit"]),
        (
            "method3(m_str, millimeter_str)",
            ["Q_", "method3", "m_str", "millimeter_str"],
        ),
        ("method3(m_str, mm_str)", ["Q_", "method3", "m_str", "mm_str"]),
        (
            "method3(m_str, millimeter_unit)",
            ["Q_", "method3", "m_str", "millimeter_unit"],
        ),
        ("method3(m_str, mm_unit)", ["Q_", "method3", "m_str", "mm_unit"]),
        ("spacer_1", None),
        ("method1(forty_two_mm, meter_str)", ["method1", "forty_two_mm", "meter_str"]),
        ("method1(forty_two_mm, m_str)", ["method1", "forty_two_mm", "m_str"]),
        ("method2(forty_two_mm, meter_str)", ["method2", "forty_two_mm", "meter_str"]),
        ("method2(forty_two_mm, m_str)", ["method2", "forty_two_mm", "m_str"]),
        (
            "method3(millimeter_str, meter_str)",
            ["Q_", "method3", "millimeter_str", "meter_str"],
        ),
        (
            "method3(millimeter_str, m_str)",
            ["Q_", "method3", "millimeter_str", "m_str"],
        ),
        (
            "method3(millimeter_str, meter_unit)",
            ["Q_", "method3", "millimeter_str", "meter_unit"],
        ),
        (
            "method3(millimeter_str, m_unit)",
            ["Q_", "method3", "millimeter_str", "m_unit"],
        ),
        ("method3(mm_str, meter_str)", ["Q_", "method3", "mm_str", "meter_str"]),
        ("method3(mm_str, m_str)", ["Q_", "method3", "mm_str", "m_str"]),
        ("method3(mm_str, meter_unit)", ["Q_", "method3", "mm_str", "meter_unit"]),
        ("method3(mm_str, m_unit)", ["Q_", "method3", "mm_str", "m_unit"]),
    ]:
        if g_keys is None:
            times_d[cmd] = None
            continue

        g_d = {k: global_d[k] for k in g_keys}
        times_d[cmd] = timeit.timeit(cmd, globals=g_d, number=N)

    for cmd, v in times_d.items():
        if v is None:
            lines.append("")
        else:
            lines.append(f"{cmd} :: {v:.3f} [s]")
        print(lines[-1])
    lines.append("")
    output_filepath.write_text("\n".join(lines))


if __name__ == "__main__":
    cli()
