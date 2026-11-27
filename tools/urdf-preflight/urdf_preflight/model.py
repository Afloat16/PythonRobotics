"""Public result types and the bounded, non-expanding XML reader."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from xml.parsers import expat

MAX_BYTES = 16 * 1024 * 1024
MAX_NODES = 100_000
MAX_DEPTH = 256


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    line: int = 1
    column: int = 1
    location: str = "robot"
    children: list[Node] = field(default_factory=list)

    def all(self, tag: str) -> list[Node]:
        return [n for n in self.children if n.tag == tag]

    def one(self, tag: str) -> Node | None:
        return next((n for n in self.children if n.tag == tag), None)


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    remedy: str
    path: str
    line: int
    column: int
    location: str
    suppressed: bool = False

    @property
    def fingerprint(self) -> str:
        # Line movement is harmless; changed evidence is a new finding.
        payload = [self.code, self.path, self.location, self.message]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=True).encode()).hexdigest()

    def as_dict(self) -> dict:
        return {**asdict(self), "fingerprint": self.fingerprint}


@dataclass
class Report:
    path: str
    name: str = ""
    version: str = ""
    links: int = 0
    joints: int = 0
    roots: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    operational_error: bool = False

    def as_dict(self) -> dict:
        return {**asdict(self), "issues": [i.as_dict() for i in self.issues]}


class InputError(ValueError):
    def __init__(self, message: str, line: int = 1, column: int = 1):
        super().__init__(message)
        self.line, self.column = line, column


def parse_xml(data: bytes) -> Node:
    """Reject DTDs/entities, then build a size/depth-bounded source-located tree."""
    if len(data) > MAX_BYTES:
        raise InputError(f"Input exceeds {MAX_BYTES} bytes.")
    parser = expat.ParserCreate(namespace_separator="}")
    stack: list[Node] = []
    root: Node | None = None
    count = 0

    def fail(message: str) -> None:
        raise InputError(message, parser.CurrentLineNumber, parser.CurrentColumnNumber + 1)

    def forbidden(*_args: object) -> None:
        fail("DTD and entity declarations are not allowed.")

    def start(tag: str, attrs: dict[str, str]) -> None:
        nonlocal root, count
        count += 1
        if count > MAX_NODES or len(stack) >= MAX_DEPTH:
            fail("XML element count or nesting depth exceeds the safety limit.")
        node = Node(tag, dict(attrs), parser.CurrentLineNumber, parser.CurrentColumnNumber + 1)
        if stack:
            parent = stack[-1]
            ordinal = len(parent.children)
            label = f"{tag}[{attrs.get('name', str(ordinal))}]"
            node.location = parent.location + "/" + label
            parent.children.append(node)
        else:
            root = node
        stack.append(node)

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _tag: stack.pop()
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    try:
        parser.Parse(data, True)
    except expat.ExpatError as exc:
        raise InputError(str(exc), exc.lineno, exc.offset + 1) from exc
    except (LookupError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError(str(exc), parser.CurrentLineNumber, parser.CurrentColumnNumber + 1) from exc
    if root is None:
        raise InputError("Empty XML document.")
    return root
