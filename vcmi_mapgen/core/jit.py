from collections.abc import Callable
from typing import cast

import numba


def njit[F: Callable[..., object]](fn: F) -> F:
    return cast(F, numba.njit(cache=True)(fn))
