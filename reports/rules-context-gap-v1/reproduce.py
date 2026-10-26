"""Compare registered-description and direct-request routing with the real frozen Core."""
import copy
import json
from pathlib import Path

from visionleak_investigator.common import PROJECT, file_hash, read_json, write_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.domain import Registry, input_manifest
from visionleak_investigator.integrity import verify_run
from visionleak_investigator.workflow import code_digest, run_task

out=Path(__file__).resolve().parent
task,registry=make_task(out/'fixture',seed=79100)
hint='数据说明：采集过程中包含镜像与直角旋转视角。'
document=out/'fixture/description.md';document.write_text(hint,encoding='utf-8')
task.update(request_text='按已登记的数据说明检查内容关系。',context_refs=['description'])
registry['documents']['description']={'path':str(document),'sha256':file_hash(document)}
before=input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
write_json(out/'fixture/task.json',task);write_json(out/'fixture/registry.json',registry)
context=run_task(task,registry,out/'context-only')
direct_task=copy.deepcopy(task);direct_task['request_text']+=hint
direct=run_task(direct_task,registry,out/'direct-request')
verify_run(out/'context-only',recompute_identity=True);verify_run(out/'direct-request',recompute_identity=True)
assert list(context['coverage']['profiles'])==['base']
assert list(direct['coverage']['profiles'])==['base','transform']
assert read_json(out/'context-only/context.json')[0]['excerpt']==hint
assert input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])==before
receipt={'status':'gap_reproduced','code_digest':code_digest(),'model_calls':0,
    'scope':'Two real Core runs on controlled synthetic inputs; routing requirement check, not a C/D experiment or measured research gain.',
    'requirement':'docs/planning/03_EVALUATION.md §2 condition C: upgrade/question routing based on visible description, metadata completeness, configuration and budget.',
    'context_only_profiles':list(context['coverage']['profiles']),
    'same_hint_in_request_profiles':list(direct['coverage']['profiles']),
    'context_was_read':True,'source_unchanged':True,
    'owning_source':'src/visionleak_investigator/workflow.py','source_sha256':file_hash(PROJECT/'src/visionleak_investigator/workflow.py'),
    'policy_sha256':file_hash(PROJECT/'configs/policy.json'),
    'finding':'rules-v1 selects supplemental profiles from request_text before deterministic context interpretation. Registered descriptions do not influence routing. Complete and freeze the strong-rule policy before a C/D claim; retain prompt-injection and budget boundaries.'}
write_json(out/'receipt.json',receipt,exclusive=True);print(json.dumps(receipt,ensure_ascii=False))
