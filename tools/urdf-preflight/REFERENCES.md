# References and provenance

Research date: **2026-09-30**. References describe standards, numerical constraints and the surrounding ecosystem; they are not runtime dependencies. Repository popularity is only a discovery signal, not evidence of correctness. Links to evolving branches are identified as such; the reviewed urdfdom README blob hash is recorded below.

## Normative / technical sources

**[R1] ROS urdfdom maintainers, “URDF Versioning,” README, rolling branch.**
https://github.com/ros/urdfdom/blob/rolling/README.md
Reviewed README blob: `f780413639cd5cd7faa09809a8cef63965246af9`.
Companion proposal schema: https://github.com/ros/urdfdom/blob/rolling/xsd/urdf.xsd
Used for supported versions, joint-limit defaults, the default joint axis, quaternion/capsule feature gates and origin representation constraints. The schema describes itself as a proposal; this tool does not bundle it or claim complete schema conformance. No parser source was copied.

**[R2] MuJoCo maintainers, XML Reference, compiler/body inertia documentation.**
https://mujoco.readthedocs.io/en/stable/XMLreference.html
In particular `balanceinertia` and full inertia. Used to identify principal-moment triangle inequalities as a practical preflight check. Our code does not repair tensors or reproduce MuJoCo's compiler. The numerical implementation uses independently written small-matrix Jacobi rotations; the derivation and independent numerical tests are documented in `docs/rules.md` and `docs/validation.md`.

**[R3] Python Software Foundation, `xml.parsers.expat` and XML security documentation.**
https://docs.python.org/3/library/pyexpat.html
https://docs.python.org/3/library/xml.html#xml-vulnerabilities
Used for source-location callbacks, explicit DTD/entity rejection and the need for patched parser runtimes. Python's standard library is used directly, not vendored. Application resource limits are project policy, not limits promised by Python.

**[R4] OASIS, Static Analysis Results Interchange Format (SARIF), Version 2.1.0.**
https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html
Used for the interchange envelope, driver/rules/results, locations, partial fingerprints and external suppressions. This project implements its own serializer; it does not bundle the standard or an SDK.

## Prior art and ecosystem comparisons

**[R5] Atsushi Sakai and contributors, PythonRobotics.**
https://github.com/AtsushiSakai/PythonRobotics
MIT. Readability, runnable small examples and a low-dependency entry path informed the packaging goals. No algorithm implementation, documentation passage or robot asset was reused. The hosting fork is a delivery location, not an upstream endorsement or dependency.

**[R6] Google DeepMind and contributors, MuJoCo.**
https://github.com/google-deepmind/mujoco
Apache-2.0. Compared as a full dynamics engine: a static model report should precede, not replace, engine-specific testing. No source or assets were redistributed.

**[R7] Stack-of-Tasks contributors, Pinocchio.**
https://github.com/stack-of-tasks/pinocchio
BSD-2-Clause. Compared as a mature rigid-body dynamics library with model import support. No source, numerical routine or asset was copied or linked.

**[R8] MoveIt contributors, MoveIt 2.**
https://github.com/moveit/moveit2
BSD-3-Clause. Compared as a complete manipulation framework, outside the intended lightweight offline scope. No code was reused.

**[R9] yourdfpy contributors, yourdfpy.**
https://github.com/clemense/yourdfpy
https://yourdfpy.readthedocs.io/en/latest/
MIT. Existing parsing, validation, manipulation and visualization are explicitly acknowledged. The distinction here is a small dependency-free diagnostic/CI workflow, not the invention of URDF validation. No code or test assets were copied.

**[R10] robot-descriptions contributors, robot_descriptions.py.**
https://github.com/robot-descriptions/robot_descriptions.py
Apache-2.0. Compared as a model-distribution/import convenience library. It motivates explicit portable asset handling, but no robot descriptions, meshes or loaders are bundled here. Individual robot-model licenses must be checked separately.

**[R11] gkjohnson and contributors, urdf-loaders.**
https://github.com/gkjohnson/urdf-loaders
Compared at the README/product level for Unity/Three.js loading and visualization; no implementation or visuals were copied. It remains complementary to static linting.

## Issue evidence (reports, not verified current defect status)

**[R12] MuJoCo issue #1569, “How to use urdf files in mujoco?”**
https://github.com/google-deepmind/mujoco/issues/1569
Illustrates import/mesh-path questions. A single issue is qualitative evidence, not a measured prevalence claim.

**[R13] MuJoCo issue #2405, “Importing URDF works but export to MJCF XML is missing inertial parameters.”**
https://github.com/google-deepmind/mujoco/issues/2405

**[R14] MuJoCo issue #2982, “Frame issue in mjCBody::AccumulateInertia causing issues with fusestatic.”**
https://github.com/google-deepmind/mujoco/issues/2982

The latter two highlight important limits: a valid input can still encounter importer/exporter or frame-accumulation behavior. This tool does **not** claim to detect those engine implementation defects. Their code snippets and model files are not included. Issue status, reproduction and fixes were not independently verified.

## Reuse and licensing statement

The implementation, rule arrangement, output templates and synthetic fixtures in this directory were independently written for this project. No reference repository's source implementation, documentation text, mesh, robot model or test fixture is redistributed. Shared XML field names, physical relationships and SARIF keys follow the cited specifications. MIT covers this project's material only; third-party sources retain their own licenses. Optional NumPy verification is a development-only comparison and does not vendor NumPy.

For a future contribution that actually copies or adapts third-party material, add the exact source revision, affected files, applicable license text, copyright notices and nature of the modification. A bibliography entry alone is not a substitute for license compliance.
