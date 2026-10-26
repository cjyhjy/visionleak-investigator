"""Explicit setup download of the locked public Core release; never used by audits."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request
import os

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
lock = json.loads((root / 'core.lock.json').read_text())
url = lock['source_archive_download_url']
if not url.startswith('https://github.com/cjyhjy/moonbit-visionleak/releases/download/'):
    raise SystemExit('Unexpected release origin; review the source lock before downloading')
if args.out.exists():
    raise SystemExit('Destination exists; use a fresh output path')
args.out.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(dir=args.out.parent, delete=False) as stream:
    temporary = Path(stream.name)
    try:
        sha = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(url, timeout=60) as response:
            if not response.url.startswith('https://'):
                raise ValueError('Non-TLS release redirect')
            while chunk := response.read(262144):
                size += len(chunk)
                if size > 100 * 1024 * 1024:
                    raise ValueError('Release archive exceeds setup download limit')
                sha.update(chunk)
                stream.write(chunk)
        if sha.hexdigest() != lock['source_archive_sha256']:
            raise ValueError('Downloaded release archive digest mismatch')
        stream.flush()
        os.fsync(stream.fileno())
        # Hard-link creation is exclusive; never overwrite a concurrent download.
        os.link(temporary, args.out)
        print(json.dumps({'url': url, 'sha256': sha.hexdigest(), 'bytes': size, 'path': str(args.out)}))
    finally:
        temporary.unlink(missing_ok=True)
