"""Deterministic machine reports and a self-contained, escaped HTML report."""
from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
from urllib.parse import quote

from . import __version__
from .core import RULES
from .model import Report


def totals(reports: list[Report]) -> dict[str, int]:
    counts = Counter(i.severity for r in reports for i in r.issues if not i.suppressed)
    return {"files": len(reports), "errors": counts["error"], "warnings": counts["warning"],
            "notes": counts["note"], "suppressed": sum(i.suppressed for r in reports for i in r.issues)}


def json_report(reports: list[Report], options: dict) -> str:
    return json.dumps({"schema_version": 1, "tool": "urdf-preflight", "version": __version__,
                       "options": options, "summary": totals(reports),
                       "reports": [r.as_dict() for r in reports]}, indent=2, ensure_ascii=True,
                      allow_nan=False) + "\n"


def terminal_safe(text: object) -> str:
    """Never pass untrusted control characters through to a terminal."""
    return "".join(c if c.isprintable() else f"\\u{ord(c):04x}" for c in str(text))


def text_report(reports: list[Report], options: dict) -> str:
    lines = [f"URDF Preflight {__version__} | profile={options.get('profile', 'default')}"]
    for report in reports:
        lines.append(f"\n{terminal_safe(report.path)}: {report.links} links, {report.joints} joints")
        for issue in report.issues:
            status = "BASELINE" if issue.suppressed else issue.severity.upper()
            lines.append(f"  {issue.line}:{issue.column} {status} {issue.code} {terminal_safe(issue.message)}")
            lines.append(f"    Fix: {terminal_safe(issue.remedy)}")
    summary = totals(reports)
    lines.append("\n" + ", ".join(f"{v} {k}" for k, v in summary.items()))
    return "\n".join(lines) + "\n"


def sarif_report(reports: list[Report], options: dict) -> str:
    codes = sorted({i.code for r in reports for i in r.issues})
    rules = [{"id": code, "shortDescription": {"text": RULES[code]},
              "help": {"text": "Consult the accompanying remedy and docs/rules.md."}} for code in codes]
    results = []
    for report in reports:
        source = Path(report.path)
        uri = source.as_uri() if source.is_absolute() else quote(source.as_posix(), safe="/")
        artifact = {"uri": uri}
        if not source.is_absolute():
            artifact["uriBaseId"] = "%SRCROOT%"
        for issue in report.issues:
            entry = {"ruleId": issue.code, "ruleIndex": codes.index(issue.code),
                     "level": issue.severity,
                     "message": {"text": issue.message + "\nRemedy: " + issue.remedy},
                     "locations": [{"physicalLocation": {"artifactLocation": artifact,
                         "region": {"startLine": issue.line, "startColumn": issue.column}}}],
                     "partialFingerprints": {"urdfPreflight/v1": issue.fingerprint}}
            if issue.suppressed:
                entry["suppressions"] = [{"kind": "external", "status": "accepted",
                                           "justification": "Explicit baseline or rule ignore."}]
            results.append(entry)
    run = {"tool": {"driver": {"name": "urdf-preflight", "version": __version__, "rules": rules}},
           "originalUriBaseIds": {"%SRCROOT%": {"uri": Path.cwd().as_uri().rstrip("/") + "/"}},
           "results": results, "properties": {"options": options}}
    return json.dumps({"$schema": "https://json.schemastore.org/sarif-2.1.0.json",
                       "version": "2.1.0", "runs": [run]}, indent=2, ensure_ascii=True) + "\n"


def html_report(reports: list[Report], options: dict) -> str:
    summary = totals(reports)
    cards = "".join(f'<div class="metric"><strong>{v}</strong><span>{k}</span></div>'
                    for k, v in summary.items())
    sections = []
    for report in reports:
        findings = []
        for issue in report.issues:
            status = "suppressed" if issue.suppressed else issue.severity
            findings.append(f'<details open class="finding {status}"><summary>'
                            f'<span class="badge">{status.upper()}</span> <code>{issue.code}</code> '
                            f'{escape(RULES[issue.code])} <small>line {issue.line}:{issue.column}</small>'
                            f'</summary><p>{escape(issue.message)}</p><p class="remedy">'
                            f'<b>Next step</b> — {escape(issue.remedy)}</p>'
                            f'<code class="location">{escape(issue.location)}</code></details>')
        content = "".join(findings) or '<p class="clean">No findings in the enabled checks.</p>'
        sections.append(f'<section><h2>{escape(report.path)}</h2><p class="meta">'
                        f'{escape(report.name)} · URDF {escape(report.version)} · '
                        f'{report.links} links · {report.joints} joints</p>{content}</section>')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>URDF Preflight — inspection report</title><style>
:root{{font-family:system-ui,-apple-system,sans-serif;color:#e7edf5;background:#0c1320;color-scheme:dark}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1100px;padding:54px 28px;margin:auto}}
.eyebrow{{color:#72e0c3;letter-spacing:.14em;font-size:12px;font-weight:700}}h1{{font-size:clamp(32px,5vw,54px);margin:12px 0}}
.subtitle,.meta,footer{{color:#a1b1c5;line-height:1.65}}.metrics{{display:flex;flex-wrap:wrap;gap:12px;margin:32px 0}}
.metric{{flex:1;min-width:120px;border:1px solid #28374c;background:#131f30;border-radius:12px;padding:20px}}
.metric strong{{display:block;font-size:32px}}.metric span{{font-size:13px;color:#a1b1c5}}
section{{margin-top:36px}}h2{{font-size:21px;overflow-wrap:anywhere}}.finding{{margin:12px 0;border:1px solid #2b3d55;border-left:3px solid #eead50;border-radius:9px;background:#131f30;padding:16px}}
.error{{border-left-color:#ff7f8f}}.note{{border-left-color:#80b7ff}}.suppressed{{border-left-color:#6c8094;opacity:.75}}
summary{{cursor:pointer;line-height:1.8}}.badge{{font-size:10px;font-weight:750;letter-spacing:.07em;margin-right:8px}}small{{color:#a1b1c5;margin-left:8px}}
p{{line-height:1.6;overflow-wrap:anywhere}}code{{font-size:12px;overflow-wrap:anywhere}}.location{{display:block;color:#94aac4}}
.remedy{{color:#9be6d0}}.clean{{border:1px solid #295f53;border-radius:9px;padding:20px;color:#9be6d0}}
footer{{margin-top:42px;padding-top:24px;border-top:1px solid #28374c;font-size:12px}}@media print{{:root{{color:#111;background:#fff;color-scheme:light}}.finding,.metric{{background:#fff;color:#111}}}}
</style></head><body><main><div class="eyebrow">ROBOT MODEL QUALITY / READ-ONLY</div>
<h1>URDF Preflight</h1><p class="subtitle">Find model problems before launching a simulator.<br>
Version {__version__} · Profile: {escape(str(options.get('profile', 'default')))} · Local inspection, no remote assets</p>
<div class="metrics">{cards}</div>{''.join(sections)}
<footer>Passing this report means only that the enabled static checks found no issues. It does not certify simulation correctness or hardware safety.
<br>Options: {escape(json.dumps(options, sort_keys=True))}</footer></main></body></html>\n'''


RENDERERS = {"text": text_report, "json": json_report, "sarif": sarif_report, "html": html_report}
