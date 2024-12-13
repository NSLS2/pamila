import numpy as np
from scipy.interpolate import PchipInterpolator

poly1d = np.poly1d


def identity_conversion(*inputs):
    return [v for v in inputs]
