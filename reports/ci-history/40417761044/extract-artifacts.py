"""Extract this CI's evidence only after matching the downloaded ZIP to GitHub's digest."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

from visionleak_investigator.common import PROJECT, file_hash, read_json, write_json

base=Path(__file__).resolve().parent
commit='cee32090384c192ab171c321336876eea2c95083'
expected={}
for item in read_json(base/'github-artifacts.json')['artifacts']:
    platform=item['name'].removeprefix('real-core-').removesuffix('-'+commit)
    assert platform in ('ubuntu-24.04','macos-14') and platform not in expected
    expected[platform]=(item['id'],item['digest'].removeprefix('sha256:'))
assert len(expected)==2
names={'ci-fetch','ci-bootstrap','ci-regression','ci-fresh-audit','ci-scripted-controller',
       'ci-evaluation-gates','ci-resources','ci-report-demo','ci-catalog-execution','ci-lifecycle',
       'ci-plan-check','ci-partial-report','ci-proposal-export','ci-interaction','ci-review-lifecycle','ci-rules-routing'}
run=read_json(base/'github-run.json')
assert run['conclusion']=='success' and run['headSha']==commit
artifacts=[]
for platform,(artifact_id,sha) in expected.items():
    archive=PROJECT/'.cache/ci/40417761044'/f'{platform}.zip'
    assert file_hash(archive)==sha
    destination=base/platform;destination.mkdir(exist_ok=False)
    files=[]
    with zipfile.ZipFile(archive) as bundle:
        raw_commands=bundle.read('reports/commands.jsonl')
        commands=[c for c in map(json.loads,raw_commands.decode().splitlines()) if c['name'] in names]
        assert len(commands)==len(names) and {c['name'] for c in commands}==names
        assert all(c['exit_code']==0 for c in commands)
        logs={c['log'] for c in commands}
        selected=set()
        for item in bundle.infolist():
            name=item.filename
            if item.is_dir() or not (name.startswith(('runs/ci-','reports/ci/')) or name in logs or name=='core.runtime.lock.json'):continue
            relative=PurePosixPath(name)
            assert not relative.is_absolute() and '..' not in relative.parts and name not in selected
            assert not stat.S_ISLNK(item.external_attr >> 16)
            selected.add(name);data=bundle.read(item)
            path=destination.joinpath(*relative.parts);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(data)
            files.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
        write_json(destination/'commands.json',commands,exclusive=True)
        path=destination/'commands.json';files.append({'path':'commands.json','sha256':file_hash(path),'bytes':path.stat().st_size})
        artifacts.append({'artifact_id':artifact_id,'platform':platform,
            'artifact_name':f'real-core-{platform}-{commit}','zip_sha256':sha,
            'source_commands_sha256':hashlib.sha256(raw_commands).hexdigest(),
            'extraction_scope':'Current CI runs, runtime lock, CI reports and exact current command logs; historical paths retained unchanged.',
            'files':files})
write_json(base/'download.json',{'run_id':40417761044,'artifacts':artifacts},exclusive=True)
print(json.dumps({'status':'downloaded_and_hash_matched','files':{a['platform']:len(a['files']) for a in artifacts}}))
