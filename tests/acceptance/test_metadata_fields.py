import csv
import io

import pytest

from visionleak_investigator.common import file_hash, read_json
from visionleak_investigator.domain import Registry, input_manifest
from visionleak_investigator.interaction_fixture import make_interaction_suite
from visionleak_investigator.workflow import run_task


@pytest.mark.parametrize('scenario',['absent_optional','sparse','required_only','custom_entity','no_rows','extra_values'])
def test_explicit_metadata_field_coverage_in_real_audit(tmp_path,scenario):
    root=tmp_path/'suite';make_interaction_suite(root)
    task=read_json(root/'tasks/t000/task.json');registry=read_json(root/'tasks/t000/registry.json')
    path=Registry(registry).document('metadata')
    rows=list(csv.DictReader(io.StringIO(path.read_text())))
    fields=['file_id','relative_path','image_split','entity_id','capture_session_id','provenance_ref']
    for row in rows:
        row.pop('category');row.update(capture_session_id='session',provenance_ref='declared-source')
    if scenario=='absent_optional':fields=['file_id','relative_path','entity_id']
    if scenario=='required_only':fields=['file_id','relative_path']
    if scenario=='no_rows':rows=[]
    if scenario=='custom_entity':
        fields[3]='subject';task['entity_key']='subject';registry['confirmations']['user.entity']['entity_key']='subject'
        for row in rows:row['subject']=row.pop('entity_id')
    with path.open('w',newline='') as output:
        writer=csv.writer(output);writer.writerow(fields)
        for n,row in enumerate(rows):
            values=[row.get(name,'') for name in fields]
            if scenario=='sparse' and n==0:values[-2]='  ';values[-1]=''
            if scenario=='sparse' and n==1:values=values[:-1]
            if scenario=='extra_values' and n==0:values.append('unmapped extra value')
            writer.writerow(values)
    registry['documents']['metadata']['sha256']=file_hash(path)
    before=input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
    out=tmp_path/'run';report=run_task(task,registry,out)
    coverage=report['coverage']['metadata'];counts=coverage['field_coverage']
    assert input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])==before
    assert file_hash(path)==registry['documents']['metadata']['sha256']
    assert counts['file_id']['nonempty_rows']==len(rows)
    html=(out/'report.html').read_text()
    assert '未提供的可选列' in html and '字段存在性不代表来源真实性已核验' in html
    if scenario=='absent_optional':
        assert coverage['state']=='complete'
        assert coverage['missing_optional_columns']==['image_split','capture_session_id','provenance_ref']
        assert counts['provenance_ref']['state']=='missing_column' and counts['provenance_ref']['missing_rows']==6
        import json
        witnesses=[e for e in map(json.loads,(out/'evidence.jsonl').read_text().splitlines()) if e['kind']=='metadata.entity_overlap']
        assert witnesses and all(m['provenance_ref'] is None for e in witnesses for m in e['facts']['members'])
    if scenario=='sparse':
        assert coverage['state']=='complete' and coverage['missing_optional_columns']==[]
        assert counts['capture_session_id']['empty_value_rows']==1
        assert counts['provenance_ref']['empty_value_rows']==counts['provenance_ref']['absent_value_rows']==1
        assert counts['provenance_ref']['nonempty_rows']==4 and counts['provenance_ref']['missing_rows']==2
    if scenario=='required_only':
        assert coverage['state']=='partial' and counts['entity_id']['state']=='missing_column'
        assert not any(c['claim_type']=='goal_conflict' for c in report['claims'])
    if scenario=='custom_entity':
        assert coverage['state']=='complete' and counts['entity_id']['state']=='missing_column'
        assert counts['subject']['state']=='complete' and counts['subject']['nonempty_rows']==6
        assert any(c['claim_type']=='goal_conflict' for c in report['claims'])
    if scenario=='no_rows':
        assert coverage['state']=='partial' and coverage['unmapped_image_count']==6
        assert all(c['state']=='no_rows' for c in counts.values())
    if scenario=='extra_values':
        assert coverage['state']=='partial' and any(i['code']=='extra_csv_values' for i in coverage['issues'])
        assert not any(c['claim_type']=='goal_conflict' for c in report['claims'])
