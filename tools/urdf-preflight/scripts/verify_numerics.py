"""Optional independent numerical cross-check. Development-only NumPy dependency."""
from pathlib import Path
import json
import platform
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from urdf_preflight.math3 import principal_moments

rng = np.random.default_rng(20260930)
max_error = 0.0
for _ in range(10000):
    a = rng.normal(size=(3, 3))
    a = (a + a.T) * 0.5 * 10.0 ** rng.uniform(-250, 250)
    values = [a[0, 0], a[1, 1], a[2, 2], a[0, 1], a[0, 2], a[1, 2]]
    actual, scale = principal_moments(values)
    expected = np.linalg.eigvalsh(a / scale)
    error = float(np.max(np.abs(np.asarray(actual) - expected)))
    max_error = max(max_error, error)
    if error > 1e-12:
        raise AssertionError(f"Eigenvalue mismatch: {actual}, {expected}")
print(json.dumps({"matrices": 10000, "seed": 20260930,
                  "scale_exponent_range": [-250, 250], "max_normalized_absolute_error": max_error,
                  "tolerance": 1e-12, "python": platform.python_version(), "numpy": np.__version__}, indent=2))
