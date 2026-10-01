# Validation record — 0.1.0

Local validation date: 2026-09-30. Environment: Linux, CPython 3.13.5. These are executed local results, not a claim that all configured CI platforms have passed.

| Check | Observed result | Reproduce |
|---|---|---|
| Standard-library automated suite | 121 tests passed, no skips in this environment | `python -m unittest discover -s tests -v` |
| Healthy original example | 0 errors, 0 warnings in strict simulation profile | `python -m urdf_preflight examples/healthy.urdf --profile simulation --strict` |
| Broken original example | 5 errors and 1 warning in simulation profile | `python -m urdf_preflight examples/broken.urdf --profile simulation` |
| Numerical comparison | 10,000 random symmetric matrices; max normalized absolute eigenvalue difference 2.886579864025407e-15 against NumPy 2.3.5 | `python scripts/verify_numerics.py` |
| Mutation robustness | 10,000 mutated XML inputs; 0 uncaught exceptions; not a security proof | `python scripts/verify_inputs.py` |
| Large structure | 2,000-link chain checked without recursive graph traversal | Included in unit suite |
| Packaging | Wheel built locally, installed with no index/dependencies into a fresh venv; CLI strict healthy check passed outside the source directory | Commands below |
| HTML | Local Chromium rendering inspected; 6 findings on the broken example, no external assets or script required | Generate HTML, open locally |

Numerical comparisons use seed `20260930`, matrix scales across 10^(-250) to 10^250, and tolerance 1e-12 on normalized eigenvalues. This tests the small-matrix solver independently of model fixtures. It does not certify physical measurements or simulator behavior.

Input tests include DTD/entities, UTF-16, excessive XML size/depth/count, unknown and unsupported encodings, NaN, overflow, invalid URDF graphs, mimic cycles, version-specific limits, package traversal/symlink escape, JSON/baseline behavior, HTML/terminal escaping and report-output overwrite protection. A regression discovered during development was that unsupported XML encodings could escape the diagnostic boundary; the suite now covers that case explicitly.

```bash
python -m pip wheel . --no-deps --no-build-isolation -w dist
python -m venv /tmp/preflight-check
/tmp/preflight-check/bin/python -m pip install --no-index --no-deps dist/urdf_preflight-0.1.0-py3-none-any.whl
# From a directory outside the source tree:
/tmp/preflight-check/bin/urdf-preflight /absolute/path/to/examples/healthy.urdf --profile simulation --strict
```

The first command requires a suitable preinstalled setuptools build backend. Windows uses the virtual environment's `Scripts` directory rather than `bin`.

## Not validated by these results

There is no physical robot test, simulator integration certification, third-party model corpus benchmark, measured real-world false-positive rate or exhaustive SARIF-schema certification. JSON/SARIF serialization and core fields are unit-tested. The provided GitHub Actions matrix targets Ubuntu/Windows/macOS and Python 3.10/3.13/3.14; configured jobs are not the same as observed passes. Consult the actual run attached to a commit for cloud CI status.
