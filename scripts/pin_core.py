"""Run only during explicit dependency setup, after verifying the release archive."""
import json,subprocess,hashlib,pathlib
root=pathlib.Path(__file__).resolve().parents[1]; core=root/'.deps/visionleak-core'
lock=json.loads((root/'core.lock.json').read_text())
assert hashlib.sha256((core/'dist/visionleak.js').read_bytes()).hexdigest()==lock['compiled_artifact_sha256']
code="import {sourceDigest} from './tools/source-digest.mjs'; console.log(sourceDigest(process.cwd()))"
source=subprocess.check_output(['node','--input-type=module','-e',code],cwd=core,text=True).strip()
assert source==lock['source_digest'],source
files={}
for base in ['tools','core','demo','dist','node_modules']:
 for p in sorted((core/base).rglob('*')):
  if p.is_file() and not p.is_symlink():files[str(p.relative_to(core))]=hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['package.json','package-lock.json','LICENSE']:
 p=core/name;files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
out={'source_digest':source,'node':subprocess.check_output(['node','--version'],text=True).strip(),'files':files}
lockpath=root/'core.runtime.lock.json'
if lockpath.exists() and json.loads(lockpath.read_text())!=out:
 raise SystemExit('Runtime differs from existing lock. An explicit version/platform migration is required; existing lock preserved.')
if not lockpath.exists():lockpath.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'source_digest':source,'files_pinned':len(files),'node':out['node']}))
