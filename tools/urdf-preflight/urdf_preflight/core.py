"""Original diagnostic checks for expanded URDF files, not a simulator."""
from __future__ import annotations

from collections import Counter, deque
import math
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from .math3 import principal_moments
from .model import InputError, Issue, MAX_BYTES, Node, Report, parse_xml

# Stable rule IDs: severity may depend on context. See docs/rules.md.
RULES = {
    "IO001": "Input could not be read", "XML001": "Unsafe or malformed XML",
    "URDF001": "Wrong root or robot name", "URDF002": "Unsupported version",
    "URDF003": "Unexpanded macro", "URDF004": "Version-gated feature",
    "NAME001": "Missing or duplicate name", "TREE001": "Invalid joint endpoint",
    "TREE002": "Multiple parents", "TREE003": "Root count", "TREE004": "Cycle",
    "JOINT001": "Unknown joint type", "JOINT002": "Missing joint limit",
    "JOINT003": "Invalid joint range", "JOINT004": "Suspicious axis",
    "JOINT005": "Invalid mimic reference", "JOINT006": "Mimic cycle",
    "VALUE001": "Invalid numeric value", "VALUE002": "Non-positive physical value",
    "POSE001": "Conflicting orientations", "POSE002": "Non-unit quaternion",
    "INERTIA001": "Incomplete inertial block", "INERTIA002": "Non-positive tensor",
    "INERTIA003": "Unrealizable principal moments", "INERTIA004": "Ill-conditioned tensor",
    "GEOM001": "Invalid geometry", "MESH001": "Missing local asset",
    "MESH002": "Unresolved package", "MESH003": "Unchecked URI",
    "MESH004": "Unsafe package path", "MESH005": "Nonportable path",
    "SIM001": "Geometry without inertia", "SIM002": "Visual without collision",
    "STRUCT001": "Repeated singleton element", "EXT001": "Unchecked extension",
}
UNSUPPRESSIBLE = {"IO001", "XML001", "URDF001", "URDF002", "URDF003"}
FLOAT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
KINDS = {"fixed", "floating", "planar", "revolute", "continuous", "prismatic"}
MOVING_AXIS = {"planar", "revolute", "continuous", "prismatic"}


class Checker:
    def __init__(self, path: str, base_dir: Path, packages: dict[str, Path], profile: str,
                 check_meshes: bool):
        if profile not in ("default", "simulation"):
            raise ValueError("profile must be 'default' or 'simulation'")
        self.report = Report(path)
        self.base = base_dir
        self.packages = packages
        self.profile = profile
        self.check_meshes = check_meshes
        self.version = (1, 0)

    def issue(self, code: str, node: Node, message: str, remedy: str,
              severity: str = "error") -> None:
        self.report.issues.append(Issue(code, severity, message, remedy, self.report.path,
                                        node.line, node.column, node.location))

    def numbers(self, node: Node, attr: str, count: int = 1,
                infinity: bool = False) -> list[float] | None:
        raw = node.attrs.get(attr, "")
        parts = raw.split()
        allowed_inf = {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
        valid = len(parts) == count and all(
            FLOAT.fullmatch(s) or (infinity and s.lower() in allowed_inf) for s in parts)
        if valid:
            try:
                values = [float(s) for s in parts]
                valid = all(math.isfinite(v) or (infinity and s.lower() in allowed_inf)
                            for v, s in zip(values, parts))
            except ValueError:
                valid = False
        if not valid:
            self.issue("VALUE001", node, f"{attr}={raw!r}: expected {count} valid number(s).",
                       "Use decimal/scientific notation; reject NaN and overflow. Check units and expansion.")
            return None
        return values

    def positive(self, node: Node, attr: str, count: int = 1, zero: bool = False) -> None:
        values = self.numbers(node, attr, count)
        if values is not None and any(v < 0 if zero else v <= 0 for v in values):
            self.issue("VALUE002", node, f"{attr}={node.attrs.get(attr)!r} must be {'non-negative' if zero else 'positive'}.",
                       "Check SI units and physical meaning; do not replace values with arbitrary constants.")

    def singleton(self, node: Node, tags: tuple[str, ...]) -> None:
        for tag in tags:
            items = node.all(tag)
            for item in items[1:]:
                self.issue("STRUCT001", item, f"Repeated <{tag}> in {node.location}.",
                           "Keep a single definition; a loader may silently choose only one.")

    def pose(self, parent: Node) -> None:
        self.singleton(parent, ("origin",))
        for node in parent.all("origin"):
            if "xyz" in node.attrs:
                self.numbers(node, "xyz", 3)
            if "rpy" in node.attrs:
                self.numbers(node, "rpy", 3)
            if "quat_xyzw" in node.attrs:
                if self.version < (1, 1):
                    self.issue("URDF004", node, "quat_xyzw requires URDF 1.1+.",
                               "Use rpy for older consumers, or declare a supported newer version.", "warning")
                if "rpy" in node.attrs:
                    self.issue("POSE001", node, "Both rpy and quat_xyzw are specified.",
                               "Keep exactly one orientation representation.")
                q = self.numbers(node, "quat_xyzw", 4)
                if q is not None:
                    length = math.hypot(*q)
                    if length == 0 or not math.isfinite(length):
                        self.issue("POSE002", node, "Quaternion has zero or overflowing norm.",
                                   "Provide a finite unit quaternion in x y z w order.")
                    elif abs(length - 1) > 1e-6:
                        self.issue("POSE002", node, f"Quaternion norm is {length:.8g}, not 1.",
                                   "Verify x y z w ordering, then explicitly normalize the intended rotation.", "warning")

    def asset(self, node: Node) -> None:
        raw = node.attrs.get("filename", "")
        if not raw:
            self.issue("MESH001", node, "Mesh filename is missing.", "Provide a local or package:// mesh reference.")
            return
        if not self.check_meshes:
            return
        try:
            uri = urlsplit(raw)
            if uri.scheme == "package":
                name = uri.netloc
                root = self.packages.get(name)
                decoded = unquote(uri.path).lstrip("/")
                if not name or not decoded or "\\" in decoded or uri.query or uri.fragment:
                    raise ValueError("invalid package URI")
                if root is None:
                    self.issue("MESH002", node, f"Package {name!r} is not mapped; asset was not checked.",
                               f"Pass --package {name}=/path/to/package (the package directory itself).", "warning")
                    return
                root = Path(root).resolve()
                path = (root / decoded).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("package URI escapes its mapped directory")
            elif uri.scheme == "file":
                if uri.netloc not in ("", "localhost") or uri.query or uri.fragment:
                    raise ValueError("file URI must be local, without a query or fragment")
                path = Path(url2pathname(uri.path))
                if not path.is_absolute():
                    raise ValueError("file URI must have an absolute path")
                self.issue("MESH005", node, f"Absolute file URI {raw!r} is machine-specific.",
                           "Prefer a model-relative path or explicit package mapping.", "warning")
            elif uri.scheme and not Path(raw).is_absolute():
                self.issue("MESH003", node, f"URI scheme {uri.scheme!r} was not resolved.",
                           "Download trusted assets separately and use local paths; no network access is performed.", "warning")
                return
            else:
                path = Path(raw)
                if path.is_absolute():
                    self.issue("MESH005", node, f"Absolute path {raw!r} is machine-specific.",
                               "Prefer a model-relative path or explicit package mapping.", "warning")
                else:
                    path = self.base / path
            if not path.is_file():
                self.issue("MESH001", node, f"Mesh {raw!r} is not a regular local file.",
                           "Check spelling, capitalization and the directory relative to the URDF.")
        except (ValueError, OSError, RuntimeError) as exc:
            self.issue("MESH004", node, f"Cannot safely resolve mesh {raw!r}: {exc}.",
                       "Keep package assets inside their mapped directory; remove traversal and invalid URI parts.")

    def geometry(self, parent: Node) -> None:
        self.pose(parent)
        self.singleton(parent, ("geometry", "material"))
        geometries = parent.all("geometry")
        if not geometries:
            self.issue("GEOM001", parent, "Visual/collision has no geometry.", "Add exactly one supported geometry.")
        for geometry in geometries:
            if len(geometry.children) != 1:
                self.issue("GEOM001", geometry, "Geometry must contain exactly one shape.", "Split multiple shapes into separate visual/collision elements.")
            for shape in geometry.children:
                if shape.tag == "box":
                    self.positive(shape, "size", 3)
                elif shape.tag == "sphere":
                    self.positive(shape, "radius")
                elif shape.tag in ("cylinder", "capsule"):
                    capsule = shape.tag == "capsule"
                    if capsule and self.version < (1, 1):
                        self.issue("URDF004", shape, "Capsule geometry requires URDF 1.1+.",
                                   "Use supported primitives for older consumers or declare version 1.1+.", "warning")
                    self.positive(shape, "radius", zero=capsule)
                    self.positive(shape, "length", zero=capsule)
                elif shape.tag == "mesh":
                    self.asset(shape)
                    if "scale" in shape.attrs:
                        self.positive(shape, "scale", 3)
                else:
                    self.issue("GEOM001", shape, f"Unsupported geometry <{shape.tag}>.",
                               "Use box, cylinder, sphere, mesh, or version-appropriate capsule.")

    def inertia(self, link: Node) -> None:
        for block in link.all("inertial"):
            self.pose(block)
            self.singleton(block, ("mass", "inertia"))
            mass, tensor = block.one("mass"), block.one("inertia")
            if mass is None or tensor is None:
                self.issue("INERTIA001", block, "Inertial block needs mass and inertia elements.",
                           "Supply measured/computed properties, or omit the entire inertial block for a dummy frame.")
            if mass is not None:
                self.positive(mass, "value")
            if tensor is None:
                continue
            components = [self.numbers(tensor, key) for key in ("ixx", "iyy", "izz", "ixy", "ixz", "iyz")]
            if any(v is None for v in components):
                continue
            values = [v[0] for v in components if v is not None]
            eigen, scale = principal_moments(values)
            evidence = f"components={values!r}, normalized principal moments={eigen!r}, scale={scale:g}"
            if eigen[0] <= 0:
                self.issue("INERTIA002", tensor, "Tensor is not positive definite; " + evidence,
                           "Recompute the COM inertia in its declared frame. Positive diagonal entries alone are insufficient.")
            elif eigen[0] / eigen[-1] < 1e-10:
                self.issue("INERTIA004", tensor, "Tensor is nearly singular; " + evidence,
                           "Check thin-body approximations, units and simulator precision; do not silently inflate inertia.", "warning")
            if eigen[-1] > eigen[0] + eigen[1] + 1e-10 * max(1.0, abs(eigen[-1])):
                self.issue("INERTIA003", tensor, "Principal moments violate the triangle inequality; " + evidence,
                           "Recompute the full inertia tensor about the center of mass; do not test only ixx, iyy, izz.")

    def names(self, nodes: list[Node]) -> dict[str, Node]:
        result: dict[str, Node] = {}
        for n in nodes:
            name = n.attrs.get("name", "")
            if not name.strip() or name in result:
                self.issue("NAME001", n, f"Missing or duplicate {n.tag} name {name!r}.",
                           "Use a unique, non-empty name within this element type.")
            else:
                result[name] = n
        return result

    def joint(self, node: Node) -> None:
        kind = node.attrs.get("type", "")
        if kind not in KINDS:
            self.issue("JOINT001", node, f"Unknown joint type {kind!r}.", "Choose fixed, floating, planar, revolute, continuous or prismatic.")
        self.singleton(node, ("parent", "child", "axis", "limit", "mimic", "dynamics"))
        self.pose(node)
        axis = node.one("axis")
        if kind in MOVING_AXIS and axis is not None:
            xyz = self.numbers(axis, "xyz", 3) if "xyz" in axis.attrs else [1.0, 0.0, 0.0]
            if xyz is not None:
                norm = math.hypot(*xyz)
                if norm == 0 or not math.isfinite(norm):
                    self.issue("JOINT004", axis, f"Axis has zero/overflowing norm: {xyz!r}.", "Supply a finite nonzero direction in the joint frame.")
                elif abs(norm - 1) > 1e-6:
                    self.issue("JOINT004", axis, f"Axis norm is {norm:g}: {xyz!r}.", "Verify the intended axis; normalize explicitly for portability.", "warning")
        limit = node.one("limit")
        if kind in ("revolute", "prismatic") and limit is None:
            self.issue("JOINT002", node, "Bounded joint has no limit element.", "Set reviewed travel, effort and velocity limits.")
        if limit is not None:
            required = ("lower", "upper") if self.version >= (1, 2) and kind in ("revolute", "prismatic") else ()
            if self.version < (1, 2):
                required = ("effort", "velocity")
            for attr in required:
                if attr not in limit.attrs:
                    self.issue("JOINT002", limit, f"Required limit {attr!r} is missing for URDF {self.report.version}.", "Provide an explicit reviewed value for this URDF version.")
            parsed: dict[str, float] = {}
            for attr in ("lower", "upper", "effort", "velocity", "acceleration", "deceleration", "jerk"):
                if attr not in limit.attrs:
                    continue
                if attr in ("acceleration", "deceleration", "jerk") and self.version < (1, 2):
                    self.issue("URDF004", limit, f"Limit {attr!r} is ignored before URDF 1.2.", "Do not rely on this limit in older consumers; select a compatible version.", "warning")
                values = self.numbers(limit, attr, infinity=self.version >= (1, 2))
                if values is not None:
                    parsed[attr] = values[0]
                    if attr not in ("lower", "upper") and values[0] < 0:
                        self.issue("VALUE002", limit, f"{attr}={values[0]} is negative.", "Use a non-negative physical limit; check signs and units.")
            if kind in ("revolute", "prismatic") and self.version < (1, 2):
                for attr in ("lower", "upper"):
                    if attr not in limit.attrs:
                        self.issue("JOINT003", limit, f"Missing {attr!r} defaults to zero in legacy URDF.", "Make travel limits explicit to avoid accidentally locking or truncating motion.", "warning")
                        parsed[attr] = 0.0
            if "lower" in parsed and "upper" in parsed:
                if parsed["lower"] > parsed["upper"]:
                    self.issue("JOINT003", limit, f"lower={parsed['lower']} exceeds upper={parsed['upper']}.", "Review the intended travel range and axis direction.")
                elif parsed["lower"] == parsed["upper"] and kind in ("revolute", "prismatic"):
                    self.issue("JOINT003", limit, f"Joint travel is zero at {parsed['lower']}.", "Verify that a locked joint is intentional, or use a fixed joint.", "warning")
        dynamics = node.one("dynamics")
        if dynamics is not None:
            for attr in ("damping", "friction"):
                if attr in dynamics.attrs:
                    self.positive(dynamics, attr, zero=True)
        mimic = node.one("mimic")
        if mimic is not None:
            for attr in ("multiplier", "offset"):
                if attr in mimic.attrs:
                    self.numbers(mimic, attr)

    def cycles(self, nodes: dict[str, Node], edges: list[tuple[str, str]], code: str) -> None:
        adjacency: dict[str, list[str]] = {n: [] for n in nodes}
        degree = dict.fromkeys(nodes, 0)
        for parent, child in edges:
            adjacency[parent].append(child)
            degree[child] += 1
        queue = deque(n for n in nodes if degree[n] == 0)
        visited = 0
        while queue:
            visited += 1
            for child in adjacency[queue.popleft()]:
                degree[child] -= 1
                if degree[child] == 0:
                    queue.append(child)
        if visited != len(nodes):
            remaining = sorted(n for n in nodes if degree[n] > 0)
            self.issue(code, nodes[remaining[0]], f"Cycle detected; involved or downstream nodes: {remaining!r}.",
                       "Remove the cycle; URDF link and mimic dependency graphs must be acyclic.")

    def run(self, root: Node) -> Report:
        if root.tag != "robot" or not root.attrs.get("name", "").strip():
            self.issue("URDF001", root, "Expected an unnamespaced <robot> with a non-empty name.", "Use an expanded URDF robot document, not MJCF/SDF.")
            return self.report
        self.report.name = root.attrs["name"]
        self.report.version = root.attrs.get("version", "1.0")
        if self.report.version not in ("1.0", "1.1", "1.2"):
            self.issue("URDF002", root, f"Unsupported URDF version {self.report.version!r}.", "Supported versions are 1.0, 1.1 and 1.2. Omitted means 1.0.")
            return self.report
        self.version = tuple(map(int, self.report.version.split(".")))
        stack = [root]
        while stack:
            node = stack.pop()
            if (node.tag.startswith("http://www.ros.org/wiki/xacro}") or node.tag.startswith("https://www.ros.org/wiki/xacro}")) or any("${" in v or "$(" in v for v in node.attrs.values()):
                self.issue("URDF003", node, "Unexpanded macro or substitution found.", "Expand trusted Xacro separately, then check the resulting URDF; this tool never executes macros.")
                return self.report
            stack.extend(node.children)
        links = self.names(root.all("link"))
        joints = self.names(root.all("joint"))
        self.report.links, self.report.joints = len(links), len(joints)
        for node in root.children:
            if node.tag not in ("link", "joint", "material"):
                self.issue("EXT001", node, f"Extension <{node.tag}> was not validated.", "Validate simulator/control-specific extensions with their own tools.", "note")
        for link in links.values():
            self.singleton(link, ("inertial",))
            self.inertia(link)
            for n in link.children:
                if n.tag in ("visual", "collision"):
                    self.geometry(n)
            if self.profile == "simulation":
                if (link.all("visual") or link.all("collision")) and not link.all("inertial"):
                    self.issue("SIM001", link, "Geometry-bearing link has no inertial block.", "Review simulator inference/fixed-link fusion; supply physical properties where needed.", "warning")
                if link.all("visual") and not link.all("collision"):
                    self.issue("SIM002", link, "Visual geometry has no collision counterpart.", "Add suitable collision geometry if this link should contact the environment.", "warning")
        edges: list[tuple[str, str]] = []
        mimic_edges: list[tuple[str, str]] = []
        parents: Counter[str] = Counter()
        for name, joint in joints.items():
            self.joint(joint)
            parent, child = joint.one("parent"), joint.one("child")
            p = parent.attrs.get("link", "") if parent else ""
            c = child.attrs.get("link", "") if child else ""
            if p not in links or c not in links or p == c:
                self.issue("TREE001", joint, f"Invalid endpoints parent={p!r}, child={c!r}.", "Reference two existing, distinct link names.")
            else:
                parents[c] += 1
                edges.append((p, c))
                if parents[c] > 1:
                    self.issue("TREE002", joint, f"Link {c!r} has multiple parent joints.", "A URDF tree gives each non-root link exactly one parent.")
            mimic = joint.one("mimic")
            if mimic is not None:
                target = mimic.attrs.get("joint", "")
                if target not in joints or target == name:
                    self.issue("JOINT005", mimic, f"Invalid mimic target {target!r}.", "Reference another existing scalar joint.")
                else:
                    if joint.attrs.get("type") not in ("revolute", "continuous", "prismatic") or joints[target].attrs.get("type") not in ("revolute", "continuous", "prismatic"):
                        self.issue("JOINT005", mimic, "Mimic source/target must be scalar joints.", "Do not mimic fixed, floating or planar joints.")
                    mimic_edges.append((target, name))
        self.report.roots = sorted(n for n in links if parents[n] == 0)
        if len(self.report.roots) != 1:
            self.issue("TREE003", root, f"Expected one root link; found {self.report.roots!r}.", "Connect disconnected subtrees and remove graph cycles.")
        self.cycles(links, edges, "TREE004")
        self.cycles(joints, mimic_edges, "JOINT006")
        return self.report


def check_text(text: str | bytes, *, path: str = "<memory>", base_dir: str | Path = ".",
               packages: dict[str, str | Path] | None = None, profile: str = "default",
               check_meshes: bool = True) -> Report:
    """Check expanded URDF. No execution, network calls or input modifications."""
    checker = Checker(path, Path(base_dir), {k: Path(v) for k, v in (packages or {}).items()}, profile, check_meshes)
    try:
        data = text.encode("utf-8") if isinstance(text, str) else text
        checker.run(parse_xml(data))
    except (InputError, UnicodeError) as exc:
        checker.issue("XML001", Node("input", {}, getattr(exc, "line", 1), getattr(exc, "column", 1)),
                      str(exc), "Provide bounded, well-formed XML without DTDs/entities; expand trusted macros separately.")
    checker.report.issues.sort(key=lambda i: (i.line, i.column, i.code, i.message))
    return checker.report


def check_file(path: str | Path, **options: object) -> Report:
    """Read at most MAX_BYTES+1 bytes; report I/O problems instead of crashing."""
    source = Path(path)
    try:
        if not source.is_file():
            raise OSError("not a regular file")
        with source.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        report = Report(str(source), operational_error=True)
        report.issues.append(Issue("IO001", "error", str(exc), "Check the file path and read permission.", str(source), 1, 1, "input"))
        return report
    return check_text(data, path=str(source), base_dir=source.parent, **options)
