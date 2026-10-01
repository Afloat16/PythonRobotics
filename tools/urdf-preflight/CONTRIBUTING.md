# Contributing

Start with a minimal original URDF fixture that demonstrates the missing or incorrect diagnosis. Explain whether the rule follows URDF semantics, mathematics, portability policy or a simulator-specific assumption. Include the relevant primary source in REFERENCES.md; do not infer popularity from a few issue reports.

Run `python -m unittest discover -s tests -v`. All regular tests use the standard library. Run `python scripts/verify_numerics.py` with NumPy installed when changing inertia numerics. Add regression tests for every crash or false positive, including version differences and permitted dummy links.

Keep checking read-only and offline. Do not silently expand macros, install runtime dependencies, modify physical parameters or suppress unreadable/malformed inputs. Source locations and remedies must survive all renderers. New renderers must escape untrusted input.

Changes to public report keys, fingerprints, baseline format or rule meanings need a schema/version decision and changelog entry. Keep `README.md`, `README.en.md` and `docs/rules.md` aligned. Pin reproduction inputs; never commit private robot descriptions, credentials or unreviewed assets.

No source or test assets from another project may be copied without checking its license and preserving required notices. Record exact provenance for adaptations, not merely the name of a popular repository. Code should remain easy to inspect and independent of the hosting repository.

The current host uses a dedicated feature branch and subdirectory. To work only on this project, run commands from `tools/urdf-preflight`; do not reformat unrelated host files. The standalone publishing script uses a file allowlist and does not carry the host's history or unrelated files into a new repository.
