from __future__ import annotations
import json, os, platform, signal, subprocess, time, sys
from pathlib import Path
from typing import Any
from .common import PROJECT, read_json, write_json, file_hash, no_symlink, safe_child, now
from .resources import measured_wait
PROFILES={'base':[], 'transform':['--include-mirrors','--include-rotations'], 'local':['--include-crops'], 'all':['--include-mirrors','--include-rotations','--include-crops']}
KINDS={'byte-identical':'core.byte_identical','pixel-identical':'core.pixel_identical','perceptual-candidate':'core.perceptual_candidate','local-candidate':'core.local_candidate'}

def child_environment() -> dict[str,str]:
    return {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','TMPDIR','SYSTEMROOT')}

def execute(argv: list[str], cwd: Path, directory: Path, timeout: float) -> dict[str,Any]:
    """Only host constructed argv. POSIX process-group kill also cleans child workers."""
    directory.mkdir(parents=True,exist_ok=False); start=time.monotonic()
    env=child_environment()
    record={'argv':argv,'cwd':str(cwd),'started_at':now(),'timeout_seconds':timeout,'status':'pending'}
    write_json(directory/'invocation.json',record,exclusive=True)
    code=None;error=None;resources=None
    with (directory/'stdout.log').open('wb') as out,(directory/'stderr.log').open('wb') as err:
        try:
            p=subprocess.Popen(argv,cwd=cwd,env=env,shell=False,start_new_session=True,stdout=out,stderr=err)
            code,error,resources=measured_wait(p,timeout)
        except OSError as e:error=type(e).__name__
    record.update(exit_code=code,status='failed' if error else 'returned',error=error,wall_seconds=time.monotonic()-start,resources=resources)
    write_json(directory/'result.json',record,exclusive=True)
    return record

class CoreAdapter:
    def __init__(self,path: Path|None=None):
        self.path=no_symlink(path or PROJECT/'.deps/visionleak-core');self.lock=read_json(PROJECT/'core.lock.json')
        self.cli=self.path/'tools/cli.mjs'
    def verify_artifacts(self, *, timeout: float=5) -> None:
        deadline=time.monotonic()+timeout
        if file_hash(self.path/'dist/visionleak.js')!=self.lock['compiled_artifact_sha256']:raise ValueError('Core compiled artifact digest mismatch')
        pin=read_json(PROJECT/'core.runtime.lock.json')
        for name,sha in pin['files'].items():
            if file_hash(safe_child(self.path,name))!=sha:raise ValueError(f'Core source digest mismatch: {name}')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Core artifact verification time allowance exhausted')
        node=subprocess.run(['node','--version'],capture_output=True,text=True,check=True,timeout=remaining,env=child_environment()).stdout.strip()
        if node!=pin['node']:raise ValueError(f'Node version differs from runtime lock: {node}')
    def doctor(self) -> dict:
        self.verify_artifacts()
        p=subprocess.run(['node',str(self.cli),'capabilities'],capture_output=True,text=True,timeout=10,check=True,env=child_environment())
        caps=json.loads(p.stdout); expected=read_json(PROJECT/'core-capabilities.json')
        def contains(actual,subset):
            if isinstance(subset,dict):return isinstance(actual,dict) and all(k in actual and contains(actual[k],v) for k,v in subset.items())
            return actual==subset
        # Runtime values are environment-specific. Every declared semantic contract is frozen.
        for key,value in expected.items():
            if key!='runtime' and not contains(caps.get(key),value):raise ValueError(f'Incompatible Core capabilities: {key}')
        if caps['runtime']['decoder']!=expected['runtime']['decoder']:raise ValueError('Decoder version mismatch')
        return {'status':'passed','python':sys.version,'platform':platform.platform(),'core_commit':self.lock['commit'],'core_version':self.lock['version'],'cli_sha256':file_hash(self.cli),'artifact_sha256':file_hash(self.path/'dist/visionleak.js'),'capabilities':caps}
    def inspect_report(self, report_path: Path, dataset: Path, timeout: float=10) -> dict:
        r=read_json(report_path)
        if r.get('schemaVersion')!=self.lock['report_schema'] or r.get('identityVersion')!=self.lock['report_identity_version']:raise ValueError('Unknown report schema')
        if r.get('normalization')!=self.lock['normalization'] or r.get('engine',{}).get('artifactDigest')!=self.lock['compiled_artifact_sha256']:raise ValueError('Report engine/normalization mismatch')
        if r.get('localProfile') and (r['localProfile'].get('version')!=self.lock['local_profile'] or r['localProfile'].get('minimumGridContrast')!=16):raise ValueError('Unknown local profile')
        for i in r['images']:
            safe_child(dataset,i['path']);safe_child(report_path.parent,i['thumbnail'])
        if any(p['evidence'] not in KINDS for p in r['pairs']):raise ValueError('Unknown evidence type')
        p=subprocess.run(['node',str(PROJECT/'scripts/core_inspect.mjs'),str(self.path),str(report_path)],capture_output=True,text=True,timeout=timeout,env=child_environment())
        if p.returncode:raise ValueError('Core report identity/schema check failed: '+p.stderr[-500:])
        return json.loads(p.stdout)
    def audit_argv(self,dataset: Path,out: Path,profile: str,limits: dict,allocation: dict) -> list[str]:
        if profile not in PROFILES:raise ValueError('Unknown profile')
        args=['node',str(self.cli),'audit','--root',str(dataset),'--out',str(out),'--threshold','6',*PROFILES[profile]]
        values={'--max-comparisons':allocation['comparisons'],'--max-total-pixels':allocation['decoded_pixels'],'--max-images':limits['max_images'],'--max-pairs':limits['max_pairs_per_audit'],'--max-decode-pixels':limits['max_decode_pixels_per_image'],'--max-pixels':limits['max_sample_pixels_per_image'],'--max-file-bytes':limits['max_file_bytes']}
        for flag,value in values.items():args.extend([flag,str(value)])
        return args
