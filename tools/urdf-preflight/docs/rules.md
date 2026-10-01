# Rule reference

Rule IDs are stable within the 0.1 series. Severity is contextual. `error` means the selected preflight policy failed, not necessarily that every existing importer rejects the file. `warning` needs review. `note` means coverage information. References map to [REFERENCES.md](../REFERENCES.md).

| IDs | Checks / behavior | Basis |
|---|---|---|
| IO001, XML001 | Read failure; malformed XML, DTD/entities, excessive input, unsupported encoding. Never suppressible. | R3, resource policy |
| URDF001–003 | Robot root/name, supported version, unexpanded macros. Never suppressible. | R1, execution policy |
| URDF004 | New-version fields in an older declared version; warning, since importers may ignore them. | R1 |
| NAME001 | Missing or duplicate link/joint names. | R1 |
| TREE001–004 | Invalid parent/child references, multiple parents, wrong root count, cycles. Kahn-style non-recursive graph traversal. | R1, graph invariants |
| JOINT001–003 | Joint kind, required limits, inverted/implicit/zero travel. | R1, review policy |
| JOINT004 | Zero/overflowing axis is error; non-unit axis is warning. Absent axis defaults to x. | R1, portability policy |
| JOINT005–006 | Invalid/non-scalar mimic target or dependency cycle. | R1, graph invariants |
| VALUE001 | Numeric arity, invalid spelling, NaN or finite-field overflow. | R1, numeric policy |
| VALUE002 | Non-positive mass/dimensions/scale or negative non-negative fields. | Engineering policy |
| POSE001–002 | Both rpy and quaternion; zero/overflowing or non-unit quaternion. | R1, numeric policy |
| INERTIA001–004 | Incomplete block, non-positive-definite tensor, triangle inequality, conditioning. | R2, derivation below |
| GEOM001 | Missing/multiple/unsupported geometry. | R1 |
| MESH001–005 | Missing asset, unmapped package, unchecked scheme, unsafe package path, absolute path portability. | File-resolution policy |
| SIM001–002 | Geometry without inertia; visual without collision, only in simulation profile. Warnings, not universal validity rules. | Review policy |
| STRUCT001 | Duplicate elements expected to be singletons. | R1 |
| EXT001 | Top-level extension not checked. A note does not validate nested extension semantics. | Coverage policy |

Run `python -m urdf_preflight --list-rules` for individual titles. Each emitted finding contains its own remedy.

## Version-aware policy

Default is 1.0. Supported declarations are exactly `1.0`, `1.1`, `1.2`; other spellings/versions fail closed. For legacy limit blocks, effort and velocity must be supplied; missing lower/upper default to zero and trigger an engineering warning for bounded joints. Version 1.2 requires explicit lower/upper on revolute/prismatic joints, while effort/velocity may be omitted. Explicit infinity is accepted only for 1.2 limit fields, never mass, inertia, axes or dimensions. Newer quaternion/capsule features and extended limits are checked against their declared version [R1]. This is selected semantic checking, not a replacement for urdfdom's parser.

## Inertia: what is tested

URDF components form the symmetric matrix

```text
I = [ ixx ixy ixz ]
    [ ixy iyy iyz ]
    [ ixz iyz izz ]
```

For position r relative to the center of mass, rigid-body inertia is the integral of `(|r|² identity - r rᵀ) dm`. In principal coordinates, `Ixx + Iyy - Izz = 2 integral(z² dm) >= 0`, with analogous permutations. Thus sorted principal moments must satisfy `lambda_max <= lambda_min + lambda_mid`. Positive diagonal entries and diagonal-only triangle checks are insufficient after a coordinate rotation.

The original `math3.py` implementation divides components by their largest absolute value, applies up to 32 Jacobi rotations, and tests the normalized eigenvalues. Off-diagonal iteration stops below `1e-15`. A triangle violation uses relative tolerance `1e-10 * max(1, |lambda_max_normalized|)`. Non-positive minimum principal moment is an error for the intended non-degenerate physical-body policy. Positive tensors with `lambda_min/lambda_max < 1e-10` trigger a conditioning warning. Uniformly small valid tensors are not rejected simply for being small.

A valid rotation of the inertial frame preserves eigenvalues, so frame rotation is not required for these particular invariant tests. However, the tool does **not** verify the tensor's declared COM or whether the provided physical measurements match the real robot. It never applies a parallel-axis correction or changes the input.

The reported component values, normalized moments and scale make findings reproducible. Near a threshold, compare with an independent numerical implementation and the intended physical approximation. A singular ideal line/point body can be mathematically meaningful, but falls outside this tool's positive-definite dynamic-body policy; omit dummy-frame inertials rather than adding arbitrary epsilon values.

## Geometry / files

Box, cylinder and sphere dimensions must be positive. Capsule dimensions follow the newer non-negative rule; zero cylindrical length is valid. Mesh scales must be positive in the default engineering policy, even where an importer accepts a negative mirrored scale. The tool does not infer millimeter/meter mistakes from arbitrary size thresholds.

Relative paths may use `..` because common packages keep URDF and mesh directories as siblings. Explicit `package://` mappings are restricted to their mapped root after percent decoding and symlink resolution. Remote assets are not downloaded. Only regular-file existence is checked; a file with invalid STL content will still pass the existence check.

## Coverage and suppressions

Known omissions include complete material/transmission/controller validation, simulator extension internals, mesh topology, collision intersections, transformations between every frame and actual hardware limits. `EXT001` notes unknown top-level blocks; it is not a complete coverage inventory of every attribute. A clean report certifies neither full schema compliance nor safe operation.

Suppressed findings stay in reports; their severity is retained. Baselines are line-independent but evidence-sensitive, and depend on stable path spelling and semantic locations. They are a review mechanism, not a safety bypass. Fundamental input/XML/version/macro failures cannot be suppressed.
