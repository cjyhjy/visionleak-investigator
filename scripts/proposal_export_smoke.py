"""Real audit and actual JSON/CSV export CLI acceptance; no data modifications."""
import argparse
import csv
import json
from pathlib import Path
import sys

from visionleak_investigator.common import PROJECT,file_hash,read_json,write_json
from visionleak_investigator.core import execute
from visionleak_investigator.demo import make_task
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.workflow import run_task,code_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=False)
    task,registry=make_task(out/'fixture',79000);run=out/'run';report=run_task(task,registry,run)
    before={str(p):file_hash(p) for b in (run,out/'fixture') for p in b.rglob('*') if p.is_file()}
    receipts=[]
    for format in ('json','csv'):
        destination=out/f'exports/suggestion.{format}'
        result=execute([sys.executable,'-m','visionleak_investigator.cli','proposal-export','--run',str(run),
                        '--format',format,'--out',str(destination)],PROJECT,out/'commands'/format,60)
        assert result['exit_code']==0 and result['error'] is None
        receipt=read_json(out/'commands'/format/'stdout.log')
        assert receipt['sha256']==file_hash(destination) and receipt['requires_approval'] and receipt['image_reaudit']=='not_run'
        receipts.append(receipt)
    value=read_json(out/'exports/suggestion.json')
    with (out/'exports/suggestion.csv').open(newline='') as source:rows=list(csv.DictReader(source))
    decode=lambda s:json.loads(s[5:])
    assert all(row['path'].startswith('text:') and row['image_split'].startswith('text:') for row in rows)
    assert [{'path':decode(r['path']),'image_split':decode(r['image_split']),'included':r['proposed_included']=='true'} for r in rows]==value['new_manifest']
    assert len(rows)==6 and all(r['proposed_included']=='true' for r in rows if decode(r['image_split'])=='test')
    assert any(json.loads(decode(r['evidence_refs_json'])) for r in rows)
    assert all(file_hash(Path(p))==sha for p,sha in before.items()) and verify_run(run)==report
    receipt={'status':'passed','code_digest':code_digest(),'rows':len(rows),'exports':receipts,
        'source_and_audit_unchanged':True,'model_calls':0,'real_agent_experiment':'not_run',
        'data_kind':'self-generated controlled synthetic audit','encoding':'text-json-v1',
        'spreadsheet_gui_execution':'not_run; CSV serializer/parser and literal-prefix invariants tested'}
    write_json(out/'receipt.json',receipt,exclusive=True);print(json.dumps({'status':'passed','rows':len(rows),'model_calls':0}))


if __name__=='__main__':main()
