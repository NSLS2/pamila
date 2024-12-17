from pamila.device.conversion.plugin_manager import register


@register(name="ID23d_repr_convs.from_I1_I2_gap_to_x", is_factory_function=False)
def from_I1_I2_gap_to_x(I1: float, I2: float, gap: float):
    # I1, I2: [A]
    # gap: [mm]
    # x: [urad]
    x = (I1 + I2) * max([(1e2 - gap), 0.0]) / 20.0
    return [x]


@register(name="ID23d_repr_convs.from_I1_I2_gap_to_y", is_factory_function=False)
def from_I1_I2_gap_to_y(I1: float, I2: float, gap: float):
    # I1, I2: [A]
    # gap: [mm]
    # y: [urad]
    y = (I1 - I2) * max([(1e2 - gap), 0.0]) / 20.0
    return [y]


@register(name="ID23d_repr_convs.from_I1_I2_gap_to_x_y", is_factory_function=False)
def from_I1_I2_gap_to_x_y(I1: float, I2: float, gap: float):
    # I1, I2: [A]
    # gap: [mm]
    # x, y: [urad]
    x = from_I1_I2_gap_to_x(I1, I2, gap)[0]
    y = from_I1_I2_gap_to_y(I1, I2, gap)[0]
    return [x, y]


@register(name="ID23d_repr_convs.from_x_y_gap_to_I1", is_factory_function=False)
def from_x_y_gap_to_I1(x: float, y: float, gap: float):
    # x, y: [urad]
    # gap: [mm]
    # I1: [A]
    I1 = (x + y) / 2.0 * (20.0 / max([(1e2 - gap), 0.0]))
    return [I1]


@register(name="ID23d_repr_convs.from_x_y_gap_to_I2", is_factory_function=False)
def from_x_y_gap_to_I2(x: float, y: float, gap: float):
    # x, y: [urad]
    # gap: [mm]
    # I2: [A]
    I2 = (x - y) / 2.0 * (20.0 / max([(1e2 - gap), 0.0]))
    return [I2]


@register(name="ID23d_repr_convs.from_x_y_gap_to_I1_I2", is_factory_function=False)
def from_x_y_gap_to_I1_I2(x: float, y: float, gap: float):
    # x, y: [urad]
    # gap: [mm]
    # I1, I2: [A]
    I1 = from_x_y_gap_to_I1(x, y, gap)[0]
    I2 = from_x_y_gap_to_I2(x, y, gap)[0]
    return [I1, I2]


@register(
    name="ID23d_repr_convs.from_I1_x_y_gap_to_x_y_w_fixed_I2", is_factory_function=False
)
def from_I1_x_y_gap_to_x_y_w_fixed_I2(I1: float, x: float, y: float, gap: float):
    # x, y, new_x, new_y: [urad]
    # gap: [mm]
    # I1, new_I1, cur_I2: [A]

    new_I1 = I1
    cur_I2 = from_x_y_gap_to_I2(x, y, gap)[0]

    new_x = from_I1_I2_gap_to_x(new_I1, cur_I2, gap)[0]
    new_y = from_I1_I2_gap_to_y(new_I1, cur_I2, gap)[0]

    return [new_x, new_y]


@register(
    name="ID23d_repr_convs.from_I2_x_y_gap_to_x_y_w_fixed_I1", is_factory_function=False
)
def from_I2_x_y_gap_to_x_y_w_fixed_I1(I2: float, x: float, y: float, gap: float):
    # x, y, new_x, new_y: [urad]
    # gap: [mm]
    # I2, cur_I1, new_I2: [A]

    new_I2 = I2
    cur_I1 = from_x_y_gap_to_I1(x, y, gap)[0]

    new_x = from_I1_I2_gap_to_x(cur_I1, new_I2, gap)[0]
    new_y = from_I1_I2_gap_to_y(cur_I1, new_I2, gap)[0]

    return [new_x, new_y]


@register(
    name="ID23d_repr_convs.from_x_I1_I2_gap_to_I1_I2_w_fixed_y",
    is_factory_function=False,
)
def from_x_I1_I2_gap_to_I1_I2_w_fixed_y(x: float, I1: float, I2: float, gap: float):
    # x, new_x, cur_y: [urad]
    # gap: [mm]
    # I1, I2, new_I1, new_I2: [A]

    new_x = x
    cur_y = from_I1_I2_gap_to_y(I1, I2, gap)[0]

    new_I1 = from_x_y_gap_to_I1(new_x, cur_y, gap)[0]
    new_I2 = from_x_y_gap_to_I2(new_x, cur_y, gap)[0]

    return [new_I1, new_I2]


@register(
    name="ID23d_repr_convs.from_y_I1_I2_gap_to_I1_I2_w_fixed_x",
    is_factory_function=False,
)
def from_y_I1_I2_gap_to_I1_I2_w_fixed_x(y: float, I1: float, I2: float, gap: float):
    # x, new_x, cur_y: [urad]
    # gap: [mm]
    # I1, I2, new_I1, new_I2: [A]

    cur_x = from_I1_I2_gap_to_x_y(I1, I2, gap)[0]
    new_y = y

    new_I1 = from_x_y_gap_to_I1(cur_x, new_y, gap)[0]
    new_I2 = from_x_y_gap_to_I2(cur_x, new_y, gap)[0]

    return [new_I1, new_I2]


@register(
    name="ID23d_repr_convs.from_new_gap_cur_gap_cur_x_cur_y_to_new_gap_new_x_new_y",
    is_factory_function=False,
)
def from_new_gap_cur_gap_cur_x_cur_y_to_new_gap_new_x_new_y(
    new_gap: float, cur_gap: float, cur_x: float, cur_y: float
):
    # cur_x, cur_y, new_x, new_y: [urad]
    # new_gap, cur_gap: [mm]
    # cur_I1, cur_I2: [A]

    cur_I1, cur_I2 = from_x_y_gap_to_I1_I2(cur_x, cur_y, cur_gap)

    new_x, new_y = from_I1_I2_gap_to_x_y(cur_I1, cur_I2, new_gap)

    return [new_gap, new_x, new_y]
