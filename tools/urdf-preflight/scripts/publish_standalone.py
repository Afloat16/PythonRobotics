"""Preview or publish only this tool to a NEW public GitHub repository.

Requires git and an authenticated gh installation. No token is read by this
script. Existing remote repositories are never overwritten. No force push.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT_FILES = {
    'README.md', 'README.en.md', 'REFERENCES.md', 'LICENSE', 'SECURITY.md',
    'CONTRIBUTING.md', 'CHANGELOG.md', 'CITATION.cff', 'pyproject.toml',
    'MANIFEST.in', '.gitignore', '.pre-commit-hooks.yaml',
}
FOLDERS = {'urdf_preflight', 'tests', 'docs', 'examples', 'scripts'}
EXTRA = {'.github/workflows/ci.yml'}


def source_files(root: Path) -> list[Path]:
    selected = []
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in {'__pycache__', '.git', '.venv'} or part.endswith('.egg-info') for part in rel.parts):
            continue
        if str(rel.as_posix()) in ROOT_FILES | EXTRA or (
                rel.parts[0] in FOLDERS and p.suffix in {'.py', '.md', '.urdf'}):
            selected.append(p)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', help='owner/new-repository-name')
    parser.add_argument('--execute', action='store_true', help='create a NEW PUBLIC repository and push')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*', args.repository):
        parser.error('expected owner/repository without leading hyphens')
    root = Path(__file__).resolve().parents[1]
    files = source_files(root)
    print(f'New public repository: {args.repository}')
    print(f'Files: {len(files)} (allowlisted source/docs only; no host history)')
    for p in files:
        print('  ' + p.relative_to(root).as_posix())
    if not args.execute:
        print('Preview only. Review the files, authenticate gh, then add --execute.')
        return 0
    if not shutil.which('git') or not shutil.which('gh'):
        parser.error('git and GitHub CLI (gh) are required')
    subprocess.run(['gh', 'auth', 'status'], check=True)
    # gh repo create rejects an already-existing name. It creates the remote
    # before any push, so an existing repository is never a push destination.
    with tempfile.TemporaryDirectory(prefix='urdf-preflight-publish-') as directory:
        dest = Path(directory)
        for p in files:
            target = dest / p.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
        subprocess.run(['git', 'init', '-b', 'main'], cwd=dest, check=True)
        subprocess.run(['git', 'add', '.'], cwd=dest, check=True)
        # Use the user's configured identity; never fabricate an identity.
        subprocess.run(['git', 'commit', '-m', 'Release URDF Preflight 0.1.0'], cwd=dest, check=True)
        subprocess.run(['gh', 'repo', 'create', args.repository, '--public', '--source', str(dest),
                        '--remote', 'origin', '--push', '--description',
                        'Read-only, dependency-free URDF checks and CI reports'], cwd=dest, check=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'Publish stopped: {exc}') from exc
