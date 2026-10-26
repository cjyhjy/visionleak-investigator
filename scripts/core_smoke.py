import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from visionleak_investigator.common import PROJECT,read_json,write_json
from visionleak_investigator.core import execute,CoreAdapter
from visionleak_investigator.demo import make_dataset
from PIL import Image
base=PROJECT/'reports/core-smoke';base.mkdir(exist_ok=False)
root=base/'images';make_dataset(root);adapter=CoreAdapter();rows=[]
for name,flags,expected in [('complete',[],0),('partial',['--max-comparisons','1'],2),('gate',['--fail-on','exact'],3)]:
 call=base/name
 result=execute(['node',str(adapter.cli),'audit','--root',str(root),'--out',str(call/'output'),*flags],PROJECT,call,30)
 assert result['exit_code']==expected,result
 report=read_json(call/'output/report.json')
 rows.append({'case':name,'exit_code':result['exit_code'],'audit_id':report['auditId'],'complete':report['complete'],'fingerprinted_images':len(report['images']),'processed_images':report['stats']['processedImages'],'pairs':len(report['pairs']),'log_dir':str(call.relative_to(PROJECT))})
(root/'test/002.png').unlink() # Deliberate fixture corruption for invalid-evidence test only.
r=execute(['node',str(adapter.cli),'verify','--report',str(base/'complete/output/report.json'),'--root',str(root)],PROJECT,base/'invalid-verify',30)
assert r['exit_code']==4
rows.append({'case':'invalid-verify','exit_code':r['exit_code'],'result':read_json(base/'invalid-verify/stdout.log')})
clean=base/'normal-images';(clean/'train').mkdir(parents=True)
Image.new('RGB',(16,16),'red').save(clean/'train/001.png')
r=execute(['node',str(adapter.cli),'audit','--root',str(clean),'--out',str(base/'normal/output')],PROJECT,base/'normal',30)
assert r['exit_code']==0 and not read_json(base/'normal/output/report.json')['pairs']
rows.append({'case':'normal-no-pairs','exit_code':0})
write_json(base/'receipt.json',{'status':'passed','cases':rows,'data_kind':'self-generated controlled fixtures','intentional_fixture_mutation':'test/002.png removed only for invalid verification','model_calls':0},exclusive=True)
print(json.dumps(rows,ensure_ascii=False))
