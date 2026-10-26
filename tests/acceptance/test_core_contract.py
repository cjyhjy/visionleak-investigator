"""Real Core integration: no detector stubs or saved report replay."""
import json, subprocess
from pathlib import Path
import pytest
from visionleak_investigator.demo import make_dataset
from visionleak_investigator.core import CoreAdapter
from visionleak_investigator.common import PROJECT

@pytest.fixture
def data(tmp_path):
    root = tmp_path/'images'; make_dataset(root); return root

def audit(root, out, *flags):
    p = subprocess.run(['node',str(PROJECT/'.deps/visionleak-core/tools/cli.mjs'),'audit','--root',str(root),'--out',str(out),*flags],capture_output=True,text=True)
    return p, json.loads((out/'report.json').read_text()) if (out/'report.json').exists() else None

def test_T01_T02_real_exact_and_pixel(data, tmp_path):
    p,r=audit(data,tmp_path/'out'); assert p.returncode==0, p.stderr
    kinds={x['evidence'] for x in r['pairs']}; assert {'byte-identical','pixel-identical'} <= kinds
    checked=CoreAdapter().inspect_report(tmp_path/'out/report.json',data)
    assert checked['auditId']==r['auditId']

def test_T05_T07_T30_partial_and_fail_on(data,tmp_path):
    p,r=audit(data,tmp_path/'partial','--max-comparisons','1')
    assert p.returncode==2 and not r['complete']
    assert r['stats']['processedImages']<len(r['images'])
    p,r=audit(data,tmp_path/'gate','--fail-on','exact'); assert p.returncode==3 and r['pairs']

def test_T07_verify_invalid(data,tmp_path):
    p,r=audit(data,tmp_path/'out'); assert p.returncode==0
    (data/'test/002.png').unlink()
    p=subprocess.run(['node',str(PROJECT/'.deps/visionleak-core/tools/cli.mjs'),'verify','--report',str(tmp_path/'out/report.json'),'--root',str(data)],capture_output=True,text=True)
    assert p.returncode==4
    assert json.loads(p.stdout)['counts']['missing']>0

def test_T29_candidate_only_is_not_recomputed(tmp_path):
    from PIL import Image
    root=tmp_path/'images'; (root/'train').mkdir(parents=True); (root/'test').mkdir()
    Image.new('RGB',(48,48),(60,60,60)).save(root/'train/a.png')
    Image.new('RGB',(48,48),(90,90,90)).save(root/'test/b.png')
    p,r=audit(root,tmp_path/'out','--include-crops'); assert p.returncode==0
    assert r['pairs'] and all('candidate' in x['evidence'] for x in r['pairs'])
    p=subprocess.run(['node',str(PROJECT/'.deps/visionleak-core/tools/cli.mjs'),'verify','--report',str(tmp_path/'out/report.json'),'--root',str(root)],capture_output=True,text=True)
    v=json.loads(p.stdout); assert p.returncode==0 and v['counts']['valid']==0 and v['counts']['skippedCandidates']>0

def test_T34_unknown_schema_and_tampering(data,tmp_path):
    p,r=audit(data,tmp_path/'out'); assert p.returncode==0
    r['scope']['acceptedImages']+=1
    (tmp_path/'out/report.json').write_text(json.dumps(r))
    with pytest.raises(ValueError): CoreAdapter().inspect_report(tmp_path/'out/report.json',data)

def test_T03_T29_real_local_only_verification(tmp_path):
    import random
    from PIL import Image
    rng=random.Random(817);im=Image.new('RGB',(128,128))
    cells=[tuple(rng.randrange(256) for _ in range(3)) for _ in range(256)]
    im.putdata([cells[(y//8)*16+x//8] for y in range(128) for x in range(128)])
    root=tmp_path/'images';(root/'train').mkdir(parents=True);(root/'test').mkdir()
    im.save(root/'train/a.png');im.crop((0,0,96,128)).save(root/'test/b.png')
    p,r=audit(root,tmp_path/'out','--include-crops')
    assert p.returncode==0 and r['pairs'] and all(x['evidence']=='local-candidate' for x in r['pairs'])
    p=subprocess.run(['node',str(PROJECT/'.deps/visionleak-core/tools/cli.mjs'),'verify','--report',str(tmp_path/'out/report.json'),'--root',str(root)],capture_output=True,text=True)
    v=json.loads(p.stdout);assert p.returncode==0 and v['counts']['valid']==0 and v['counts']['skippedCandidates']>0

def test_T34_harmless_fields_tolerated_unknown_schema_rejected(data,tmp_path):
    p,r=audit(data,tmp_path/'out');assert p.returncode==0
    path=tmp_path/'out/report.json';r['harmlessNewMetadata']={'note':'forward-compatible annotation'};path.write_text(json.dumps(r))
    # Extra fields are covered by Core's content identity. A legitimate producer
    # must recompute the identity; keeping the old digest correctly fails.
    script="import {readFileSync,writeFileSync} from 'node:fs'; import {reportIdentity} from './.deps/visionleak-core/demo/report-identity.mjs'; const p=process.argv[1]; const r=JSON.parse(readFileSync(p)); r.auditId=reportIdentity(r).digest; writeFileSync(p,JSON.stringify(r));"
    subprocess.run(['node','--input-type=module','-e',script,str(path)],cwd=PROJECT,check=True)
    r=json.loads(path.read_text())
    assert CoreAdapter().inspect_report(path,data)['auditId']==r['auditId']
    r['schemaVersion']='visionleak-report-v999';path.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='schema'):CoreAdapter().inspect_report(path,data)
