"""Use an actual Core copy; no replacement detector or fabricated runtime."""
import json
import shutil

import pytest

from visionleak_investigator.common import PROJECT, file_hash, read_json
from visionleak_investigator.runtime import pin_runtime


@pytest.fixture
def project(tmp_path):
    for name in ('core.lock.json', 'core.runtime.lock.json', '.node-version'):
        shutil.copy2(PROJECT / name, tmp_path / name)
    shutil.copytree(PROJECT / '.deps/visionleak-core', tmp_path / '.deps/visionleak-core')
    return tmp_path


def test_runtime_drift_requires_explicit_migration_and_preserves_old_lock(project):
    lock = project / 'core.runtime.lock.json'
    previous = read_json(lock)
    previous['files']['node_modules/foreign-platform.node'] = '0' * 64
    lock.write_text(json.dumps(previous))
    before = file_hash(lock)
    with pytest.raises(ValueError, match='explicit'):
        pin_runtime(project)
    assert file_hash(lock) == before
    receipt = project / 'migration.json'
    result = pin_runtime(project, migrate=True, receipt=receipt)
    assert result['changed']
    assert read_json(receipt)['previous'] == previous
    assert read_json(receipt)['proposed'] == read_json(lock)
    assert pin_runtime(project)['changed'] is False
    with pytest.raises(FileExistsError):
        pin_runtime(project, migrate=True, receipt=receipt)


@pytest.mark.parametrize('name', ['tools/cli.mjs', 'package-lock.json', 'dist/visionleak.js'])
def test_platform_migration_cannot_bless_modified_core(project, name):
    lock_digest = file_hash(project / 'core.runtime.lock.json')
    path = project / '.deps/visionleak-core' / name
    path.write_bytes(path.read_bytes() + b'\n// changed\n')
    with pytest.raises(ValueError, match='Core'):
        pin_runtime(project, migrate=True, receipt=project / 'migration.json')
    assert file_hash(project / 'core.runtime.lock.json') == lock_digest
    assert not (project / 'migration.json').exists()


def test_platform_migration_cannot_bless_changed_node_version(project):
    (project / '.node-version').write_text('0.0.0\n')
    with pytest.raises(ValueError, match='Node version'):
        pin_runtime(project, migrate=True, receipt=project / 'migration.json')
