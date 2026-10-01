# URDF Preflight

**Find robot-model problems before launching a simulator.**

[中文](README.md) · [Rule reference](docs/rules.md) · [Research](docs/research.md)

A read-only URDF linter with source locations, actionable remedies and text/JSON/SARIF/offline HTML reports. Python 3.10+, no runtime dependencies, no ROS installation, no network calls.

```bash
# From this tool's directory, without installing anything:
python -m urdf_preflight examples/healthy.urdf --profile simulation
python -m urdf_preflight examples/broken.urdf --format html -o report.html
# Optional installation:
python -m pip install .
urdf-preflight models/ --strict
```

The broken example intentionally exits with status 1. Open the HTML file locally. The project is not published to PyPI; install this source tree rather than assuming a package with the same name is ours.

This version is hosted in the `tools/urdf-preflight` directory on the `feat/urdf-preflight` branch of [Afloat16/PythonRobotics](https://github.com/Afloat16/PythonRobotics/tree/feat/urdf-preflight/tools/urdf-preflight). It does not import or depend on the host repository.

## What is checked

Named-link tree structure; joint references, axes, limits and mimic dependencies; finite numeric fields; origin representations; mass and complete inertia tensors; primitive dimensions and local mesh references. Selected URDF 1.0, 1.1 and 1.2 semantics are version-aware. The optional `simulation` profile adds warnings for geometry-bearing links without inertial/collision data. Empty frame links remain valid.

The tensor test uses principal moments, including off-diagonal terms. Positive diagonal entries alone do not establish a physically realizable inertia tensor. See the rule reference for thresholds and engineering policies that are stricter than some importers.

## Package paths and reports

```bash
urdf-preflight robot.urdf --package arm=/work/arm_description
urdf-preflight models/ --format sarif -o results.sarif
urdf-preflight models/ --write-baseline baseline.json
urdf-preflight models/ --baseline baseline.json --strict
```

Relative meshes resolve against the URDF directory. Package mappings point to the package directory itself. Unmapped packages and remote URIs are reported as unchecked, not downloaded. Mesh files are not opened or decoded. `--no-mesh-check` explicitly skips resolution/existence checks.

Exit 0: no active findings at the failure threshold. Exit 1: errors, or warnings with `--strict`. Exit 2: invocation, input-I/O, baseline or report-write failure. Baseline generation does not turn a failing check into success. Suppressed findings remain visible. Fingerprints exclude line numbers but include source path, semantic location and evidence. Use consistent relative paths and working directories. Fundamental XML/input/version/macro errors cannot be suppressed.

## Library and development

```python
from urdf_preflight import check_file, check_text
report = check_file("robot.urdf", profile="simulation")
for issue in report.issues:
    print(issue.code, issue.line, issue.remedy)
```

```bash
python -m unittest discover -s tests -v
python -m urdf_preflight --list-rules
```

The regular test suite uses only the standard library. The optional `scripts/verify_numerics.py` cross-check uses NumPy during development. See [validation evidence](docs/validation.md), [contributing](CONTRIBUTING.md) and [security boundaries](SECURITY.md).

This is not full schema validation, a simulator, a collision checker, a mesh-quality checker or hardware safety certification. Xacro is never executed. Material, transmission and controller semantics are not exhaustively checked. Inspect reviewed physical values; never treat the remedies as permission to change robot limits automatically.

MIT licensed. No implementation or robot assets are copied from the comparison projects. Standards, documented constraints and prior tools are attributed in [REFERENCES.md](REFERENCES.md); this project makes no first-of-its-kind claim.
