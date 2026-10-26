"""Verified local release installation. No download of Core and no original tree writes."""
import argparse,hashlib,json,pathlib,shutil,stat,subprocess,sys,tempfile,zipfile
root=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--archive',type=pathlib.Path,required=True)
p.add_argument('--migrate-runtime',action='store_true');p.add_argument('--receipt',type=pathlib.Path);args=p.parse_args()
if args.migrate_runtime and args.receipt is None:p.error('--migrate-runtime requires --receipt')
lock=json.loads((root/'core.lock.json').read_text());target=root/'.deps/visionleak-core'
if target.exists():raise SystemExit('Dependency directory exists; use vli doctor to verify it. No files replaced.')
if hashlib.sha256(args.archive.read_bytes()).hexdigest()!=lock['source_archive_sha256']:raise SystemExit('Release archive digest mismatch')
target.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=target.parent) as directory:
 with zipfile.ZipFile(args.archive) as z:
  for member in z.infolist():
   name=pathlib.PurePosixPath(member.filename)
   if not member.filename.startswith('visionleak/') or '..' in name.parts or name.is_absolute() or stat.S_ISLNK(member.external_attr>>16):raise SystemExit('Unsafe archive member')
  z.extractall(directory)
 shutil.move(str(pathlib.Path(directory)/'visionleak'),target)
subprocess.run(['npm','ci','--prefix',str(target),'--cache',str(root/'.cache/npm'),'--ignore-scripts','--no-audit','--no-fund'],check=True)
pin_args=['--migrate-runtime','--receipt',str(args.receipt.resolve())] if args.migrate_runtime else []
subprocess.run([sys.executable,str(root/'scripts/pin_core.py'),*pin_args],cwd=root,check=True)
