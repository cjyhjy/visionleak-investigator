"""Exercise the public provenance/freeze CLI on new synthetic fixtures, without a model."""
import argparse
import copy
import json
from pathlib import Path
import sys

from visionleak_investigator.common import PROJECT,file_hash,read_json,write_json,now
from visionleak_investigator.core import execute
from visionleak_investigator.demo import make_task


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    root=out/'suite';catalog={'schema_version':1,'sources':[],'tasks':[]}
    for i,partition in enumerate(('development','validation','test')):
        base=root/partition;task,registry=make_task(base,71000+i);task['task_id']=partition
        write_json(base/'task.json',task)
        truth=root/'evaluator-truth'/f'{partition}.json'
        write_json(truth,{'data_kind':'synthetic gate fixture','partition':partition,'seed':71000+i},exclusive=True)
        mapping={}
        for j,path in enumerate(sorted((base/'images').rglob('*.png'))):
            sid=f'{partition}-{j}';mapping[path.relative_to(base/'images').as_posix()]=sid
            catalog['sources'].append({'source_id':sid,'source_group':f'procedural-{71000+i}',
                'entity_group':None,'session_group':None,'kind':'synthetic','path':path.relative_to(root).as_posix(),
                'sha256':file_hash(path),'uri':f'generator://gate-smoke/{71000+i}/{j}',
                'license_identifier':'self-generated','license_evidence_url':f'generator://gate-smoke/{71000+i}',
                'redistribution':'allowed','acquired_at':now(),'parents':[],'known_core_data':False})
        catalog['tasks'].append({'task_id':partition,'benchmark_partition':partition,
            'task_path':(base/'task.json').relative_to(root).as_posix(),
            'registry_path':(base/'registry.json').relative_to(root).as_posix(),
            'truth_path':truth.relative_to(root).as_posix(),'image_sources':mapping})
    protocol={'conditions':['A','B','C','D'],'repetitions':3,'policy_digest':file_hash(PROJECT/'configs/policy.json'),
        'model_configuration':{'status':'not_configured','provider':None,'model_id':None,'endpoint':None,'prompt_digest':None},
        'metric_definition':'Synthetic input/configuration gate only; no evaluation scores or real Agent experiment.'}
    write_json(out/'catalog.json',catalog,exclusive=True);write_json(out/'protocol.json',protocol,exclusive=True)
    receipts=[]
    def invoke(name,command,extra,expected=0,error=None,catalog_path=None):
        argv=[sys.executable,'-m','visionleak_investigator.cli',command,
              '--catalog',str(catalog_path or out/'catalog.json'),'--root',str(root),*map(str,extra)]
        result=execute(argv,PROJECT,out/'commands'/name,30)
        if result['exit_code']!=expected or result['error']:raise RuntimeError(f'{name}: unexpected process result')
        stderr=(out/'commands'/name/'stderr.log').read_text()
        if error and error not in stderr:raise RuntimeError(f'{name}: expected rejection reason missing')
        receipts.append({'name':name,'exit_code':expected,'expected_rejection':error,'record':f'commands/{name}/result.json'})
    invoke('validate','eval-validate',['--out',out/'validated.json'])
    invoke('freeze','eval-freeze',['--protocol',out/'protocol.json','--out',out/'frozen.json'])
    for part in ('development','validation','test'):
        invoke('check-'+part,'eval-check',['--protocol',out/'protocol.json','--frozen',out/'frozen.json',
            '--partition',part,'--out',out/f'checked-{part}.json'])
    shared=copy.deepcopy(catalog);shared['sources'][6]['source_group']=shared['sources'][0]['source_group']
    write_json(out/'catalog-shared.json',shared,exclusive=True)
    invoke('reject-shared-source','eval-validate',[],1,'crosses benchmark',out/'catalog-shared.json')
    leaked=copy.deepcopy(catalog);reg=read_json(root/'development/registry.json')
    truth=root/catalog['tasks'][2]['truth_path'];exposed=root/'development/context.txt';exposed.write_bytes(truth.read_bytes())
    reg['documents']['leaked-truth']={'path':str(exposed),'sha256':file_hash(exposed)}
    write_json(root/'development/registry-exposed.json',reg,exclusive=True)
    leaked['tasks'][0]['registry_path']='development/registry-exposed.json'
    write_json(out/'catalog-exposed.json',leaked,exclusive=True)
    invoke('reject-cross-task-truth','eval-validate',[],1,'truth registered',out/'catalog-exposed.json')
    changed={**protocol,'repetitions':2};write_json(out/'protocol-changed.json',changed,exclusive=True)
    invoke('reject-protocol-drift','eval-check',['--protocol',out/'protocol-changed.json',
        '--frozen',out/'frozen.json','--partition','test'],1,'Protocol changed')
    # Negative fixtures remain outside the original input registry; its freeze still verifies.
    invoke('check-after-rejections','eval-check',['--protocol',out/'protocol.json','--frozen',out/'frozen.json',
        '--partition','test','--out',out/'checked-after-rejections.json'])
    receipt={'status':'passed','data_kind':'self-generated synthetic gate fixtures',
             'meaning':'Configuration validation only; no independent natural data or model experiment',
             'model_calls':0,'commands':receipts,'freeze_digest':read_json(out/'frozen.json')['freeze_digest']}
    write_json(out/'receipt.json',receipt,exclusive=True);print(json.dumps(receipt))


if __name__=='__main__':main()
