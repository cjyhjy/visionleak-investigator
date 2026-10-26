"""Read installed dependency metadata and hash bundled notices. No license inference."""
import argparse
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import platform
import sys

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--environment', choices=['base-dev', 'optional-sdk'], required=True)
args = parser.parse_args()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def notice(path):
    name = path.name.lower()
    return name.startswith(('license', 'licence', 'copying', 'notice', 'copyright'))


packages = []
for dist in sorted(distributions(), key=lambda d: d.metadata['Name'].lower()):
    meta = dist.metadata
    files = []
    for relative in dist.files or []:
        path = Path(dist.locate_file(relative))
        if notice(path) and path.is_file():
            files.append({'path': str(relative), 'sha256': sha(path)})
    declared = meta.get('License-Expression') or meta.get('License')
    packages.append({'name': meta['Name'], 'version': dist.version,
                     'declared_license': declared, 'classifiers': [c for c in meta.get_all('Classifier', []) if c.startswith('License ::')],
                     'project_urls': meta.get_all('Project-URL', []), 'notice_files': files})

node = []
core = root/'.deps/visionleak-core'
package_files = [core/'package.json', *sorted((core/'node_modules').glob('*/package.json')),
                 *sorted((core/'node_modules').glob('@*/*/package.json'))]
for package in package_files:
    meta = json.loads(package.read_text())
    paths = [p for p in package.parent.rglob('*') if p.is_file() and notice(p)] if package.parent != core else [core/'LICENSE']
    node.append({'name': meta['name'], 'version': meta['version'], 'declared_license': meta.get('license'),
                 'package_path': str(package.relative_to(core)),
                 'notice_files': [{'path': str(p.relative_to(core)), 'sha256': sha(p)} for p in sorted(paths)]})

value = {'environment': args.environment, 'python': sys.version, 'platform': platform.platform(),
         'uv_lock_sha256': sha(root/'uv.lock'), 'core_package_lock_sha256': sha(core/'package-lock.json'),
         'collector_sha256': sha(Path(__file__)), 'python_packages': packages, 'installed_node_packages': node,
         'scope': 'Installed packages on this platform; embedded notices are enumerated, not legally reclassified. Does not assign an Investigator license or claim a complete SBOM of all bundled native libraries.'}
args.out.parent.mkdir(parents=True, exist_ok=True)
with args.out.open('x') as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'environment': args.environment, 'python_packages': len(packages), 'node_packages': len(node),
                  'without_license_metadata': [p['name'] for p in packages if not p['declared_license'] and not p['classifiers']],
                  'out': str(args.out)}))
