"""Small symmetric-matrix routines; no numerical runtime dependency."""
from __future__ import annotations

import math


def principal_moments(values: list[float]) -> tuple[list[float], float]:
    """Return sorted eigenvalues divided by max-abs entry, and that scale.

    Input order: ixx, iyy, izz, ixy, ixz, iyz. Jacobi rotations operate
    on normalized entries so uniformly tiny/huge tensors do not overflow.
    Values are NOT automatically corrected. Callers must check finiteness.
    """
    if len(values) != 6 or not all(math.isfinite(x) for x in values):
        raise ValueError("Expected six finite inertia components.")
    scale = max(map(abs, values))
    if scale == 0:
        return [0.0, 0.0, 0.0], 0.0
    xx, yy, zz, xy, xz, yz = (v / scale for v in values)
    a = [[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]]
    for _ in range(32):
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) < 1e-15:
            break
        angle = 0.5 * math.atan2(2.0 * a[p][q], a[q][q] - a[p][p])
        c, s = math.cos(angle), math.sin(angle)
        pp, qq, pq = a[p][p], a[q][q], a[p][q]
        a[p][p] = c*c*pp - 2*c*s*pq + s*s*qq
        a[q][q] = s*s*pp + 2*c*s*pq + c*c*qq
        a[p][q] = a[q][p] = 0.0
        for k in range(3):
            if k not in (p, q):
                kp, kq = a[k][p], a[k][q]
                a[k][p] = a[p][k] = c*kp - s*kq
                a[k][q] = a[q][k] = s*kp + c*kq
    return sorted(a[i][i] for i in range(3)), scale
