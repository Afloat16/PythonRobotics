# Security and physical safety

URDF Preflight is a static, read-only helper, not a sandbox or a safety controller.

The checker does not execute Xacro, launch subprocesses, contact robots, download assets, import model-provided code or rewrite model files. The optional standalone-publishing script is a separate, explicitly invoked Git/GitHub CLI operation, not part of checking.

XML is limited to 16 MiB, 100,000 elements and depth 256. DTDs and entity declarations are rejected through Expat callbacks, including when the input is UTF-16. Unsupported encodings are reported as findings. Keep Python and its Expat library patched; application limits do not remove every parser vulnerability. See references R3.

Package meshes must resolve within their explicitly mapped package root. Ordinary relative paths can intentionally refer to sibling directories; absolute local paths are accepted with a portability warning. The checker performs filesystem metadata checks, not mesh decoding. It is not a filesystem isolation boundary and cannot prevent concurrent path/symlink replacement. Run untrusted models in a restricted directory/container with CPU/memory limits and no sensitive mounts.

HTML escapes input, contains no scripts or remote assets, and applies a restrictive content security policy. Text output escapes non-printable control characters. JSON and SARIF are data, not commands. Reports may reveal model names, local paths and physical values; review before publishing or uploading them.

CLI output paths are explicit. Model inputs, an input baseline and hard-link aliases to them are protected from accidental output overwrite. Other explicitly named output files may be replaced. Do not point report destinations at unrelated assets. Filesystem races and external shell redirection are outside this protection.

Passing checks does not establish that a robot is safe, a model matches physical hardware, a simulator correctly imports it, or a controller obeys its limits. Do not automatically change mass, inertia, joint limits or actuator settings from a diagnostic suggestion.

For ordinary bugs, use an issue in the hosting repository with a minimal synthetic model and expected behavior. For a sensitive vulnerability, use GitHub private vulnerability reporting when enabled; otherwise contact the maintainer through an available private channel. Do not disclose secrets or a working sensitive exploit in a public issue.
