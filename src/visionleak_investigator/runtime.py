"""Explicit platform migration of a verified Core installation, never at audit time."""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from .common import file_hash, no_symlink, read_json, write_json, now, digest


def runtime_snapshot(project: Path, core: Path) -> dict:
    lock = read_json(project / 'core.lock.json')
    previous = read_json(project / 'core.runtime.lock.json')
    if file_hash(core / 'dist/visionleak.js') != lock['compiled_artifact_sha256']:
        raise ValueError('Core compiled artifact digest mismatch')
    files = {}
    for base in ('tools', 'core', 'demo', 'dist', 'node_modules'):
        for path in sorted((core / base).rglob('*')):
            no_symlink(path)
            if path.is_file():
                files[str(path.relative_to(core))] = file_hash(path)
    for name in ('package.json', 'package-lock.json', 'LICENSE'):
        files[name] = file_hash(no_symlink(core / name))
    # Check the release's executable source before executing its digest helper.
    source_files = lambda values: {k: v for k, v in values.items() if not k.startswith('node_modules/')}
    if source_files(files) != source_files(previous['files']):
        raise ValueError('Core release files differ; platform migration cannot change Core source')
    node = subprocess.check_output(['node', '--version'], text=True, timeout=10).strip()
    if node != 'v' + (project / '.node-version').read_text().strip():
        raise ValueError('Node version differs; platform migration cannot change Node version')
    code = "import {sourceDigest} from './tools/source-digest.mjs'; console.log(sourceDigest(process.cwd()))"
    source = subprocess.check_output(['node', '--input-type=module', '-e', code], cwd=core, text=True, timeout=30).strip()
    if source != lock['source_digest']:
        raise ValueError('Core source digest mismatch')
    return {'source_digest': source, 'node': node, 'files': files}


def pin_runtime(project: Path, *, migrate: bool = False, receipt: Path | None = None) -> dict:
    lockpath = project / 'core.runtime.lock.json'
    previous = read_json(lockpath)
    current = runtime_snapshot(project, project / '.deps/visionleak-core')
    changed = previous != current
    if changed and not migrate:
        raise ValueError('Runtime differs from existing lock. Use explicit --migrate-runtime with --receipt; existing lock preserved.')
    if migrate:
        if receipt is None:
            raise ValueError('Platform migration requires a fresh receipt path')
        write_json(receipt, {'created_at': now(), 'platform': platform.platform(),
                            'machine': platform.machine(), 'changed': changed,
                            'previous_digest': digest(previous), 'proposed_digest': digest(current),
                            'previous': previous, 'proposed': current,
                            'validation': 'source verified; doctor and full regression still required'}, exclusive=True)
        if changed:
            write_json(lockpath, current)
    return {'source_digest': current['source_digest'], 'files_pinned': len(current['files']),
            'node': current['node'], 'changed': changed}
