"""Twelve controlled interaction tasks; labels/answer contracts are evaluator-only."""
import csv
import itertools
from pathlib import Path

from .common import file_hash, read_json, write_json
from .domain import Registry, input_manifest
from .evaluation_fixture import make_catalog_suite
from .interaction_scoring import METRIC_VERSION


def make_interaction_suite(root: Path) -> tuple[dict, dict]:
    catalog, protocol = make_catalog_suite(root, count=12, seed_start=78000)
    scenario_records=[]
    for i, row in enumerate(catalog['tasks']):
        base=root/Path(row['task_path']).parent
        task=read_json(base/'task.json');registry=read_json(base/'registry.json')
        goal='content_audit' if i==4 else 'same_entity_new_view' if i in (5,10) else 'new_entity_generalization'
        missing_goal=i in (1,3,4,5,6,7,8,11);missing_field=i in (2,3,4,6,11)
        task.update(request_text='检查登记数据，并在必要时确认实验目标或字段含义。',goal='unspecified' if missing_goal else goal,
            goal_confirmed=not missing_goal,goal_evidence_refs=[] if missing_goal else ['user.local-task'],
            metadata_ref='metadata',entity_key=None if missing_field else 'entity_id',entity_key_confirmed=not missing_field,
            entity_key_evidence_refs=[] if missing_field else ['user.entity'])
        registry['confirmations']={}
        if not missing_goal:registry['confirmations']['user.local-task']={'kind':'user.goal_confirmation','goal':goal,'actor':'synthetic initial task contract'}
        if not missing_field:registry['confirmations']['user.entity']={'kind':'user.entity_key_confirmation','entity_key':'entity_id','actor':'synthetic initial field contract'}
        if i==6:task['limits']['max_questions']=1
        if i==7:task['limits']['max_questions']=0
        task['limits']['max_review_pairs']=0 if i==7 else 2
        manifest=input_manifest(Registry(registry).dataset(task['dataset_ref']),task['limits'])
        files=[f for f in manifest['files'] if f['supported_image']]
        origin={'train/001.png','test/002.png','validation/003.png','test/004.png','validation/005.png'}
        metadata=base/'samples.csv'
        with metadata.open('w',newline='',encoding='utf-8') as output:
            writer=csv.writer(output);writer.writerow(['file_id','relative_path','image_split','entity_id','category'])
            for n,f in enumerate(files):
                if i==9 and f['path']=='test/004.png':continue
                writer.writerow([str(n),f['path'],f['image_split'],'object-a' if f['path'] in origin else 'object-'+str(n),'texture'])
        registry['documents']['metadata']={'path':str(metadata.resolve()),'sha256':file_hash(metadata)}
        needed=[]
        if missing_goal:needed.append('clarify_goal')
        if missing_field and goal!='content_audit':needed.append('clarify_entity_key')
        answers={'clarify_goal':{'goal':goal},'clarify_entity_key':{'entity_key':'entity_id'}} if i!=8 else {}
        risk=[sorted([a['path'],b['path']]) for a,b in itertools.combinations(files,2)
              if a['image_split']!=b['image_split'] and {a['path'],b['path']}<=origin and goal=='new_entity_generalization']
        truth={'schema_version':1,'task_id':task['task_id'],'dataset_manifest_digest':manifest['digest'],
               'goal':goal,'entity_key':'entity_id','basis':{'kind':'synthetic_generation',
               'description':'Controlled source lineage defines object-a across views; target-goal risk labels and scripted answers fixed before execution. No natural source or human participant.'},
               'necessary_questions':needed,'answerable_questions':answers,'risk_positive_pairs':risk}
        write_json(base/'task.json',task);write_json(base/'registry.json',registry)
        write_json(root/row['truth_path'],truth)
        scenario_records.append({'task_id':task['task_id'],'goal':goal,'initial_missing_goal':missing_goal,
            'initial_missing_field':missing_field,'question_limit':task['limits']['max_questions'],
            'answers_available':i!=8,'metadata_missing_row':i==9,'controlled_image_error':i==9,
            'comparison_limited':i==11})
    protocol.update(conditions=['C','D'],metric_definition=METRIC_VERSION)
    write_json(root/'protocol.json',protocol)
    write_json(root/'interaction-source.json',{'kind':'self-generated synthetic interaction engineering cases',
        'seed_start':78000,'human_participants':0,'natural_independent_test':False,
        'scenarios':scenario_records,'answer_permission':'same fixed contract for C and future D; D is blocked'},exclusive=True)
    return catalog,protocol
