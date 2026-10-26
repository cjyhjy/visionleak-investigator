"""Local provenance/partition gate tests; all assets are synthetic, never natural test data."""
import copy
from pathlib import Path

import pytest

from visionleak_investigator.common import PROJECT,write_json,file_hash,read_json
from visionleak_investigator.demo import make_task
from visionleak_investigator.evaluation_data import validate_catalog,freeze_catalog,verify_frozen,core_history


def catalog_fixture(root):
    catalog={'schema_version':1,'sources':[],'tasks':[]}
    for i,partition in enumerate(('development','validation','test')):
        base=root/partition
        task,reg=make_task(base,700+i);task['task_id']=partition
        write_json(base/'task.json',task);write_json(root/'evaluator-truth'/f'{partition}.json',{'fixture':partition,'source':'synthetic-generator'})
        mapping={}
        for j,path in enumerate(sorted((base/'images').rglob('*.png'))):
            sid=f'{partition}-{j}';mapping[path.relative_to(base/'images').as_posix()]=sid
            catalog['sources'].append({'source_id':sid,'source_group':f'procedural-{i}',
                'entity_group':None,'session_group':None,'kind':'synthetic','path':str(path.relative_to(root)),
                'sha256':file_hash(path),'uri':f'generator://fixture/{i}/{j}',
                'license_identifier':'self-generated','license_evidence_url':f'generator://fixture/{i}',
                'redistribution':'allowed','acquired_at':'2026-10-26T19:00:00+00:00','parents':[],
                'known_core_data':False})
        catalog['tasks'].append({'task_id':partition,'benchmark_partition':partition,
            'task_path':str((base/'task.json').relative_to(root)),
            'registry_path':str((base/'registry.json').relative_to(root)),
            'truth_path':f'evaluator-truth/{partition}.json','image_sources':mapping})
    protocol={'conditions':['A','B','C','D'],'repetitions':3,
              'policy_digest':file_hash(PROJECT/'configs/policy.json'),
              'model_configuration':{'status':'not_configured','provider':None,'model_id':None,'endpoint':None,'prompt_digest':None},
              'metric_definition':'exact and related-excluding-exact; N/A on empty denominator; synthetic gate test only'}
    return catalog,protocol


def test_disjoint_partitions_and_explicit_freeze_are_verified(tmp_path):
    catalog,protocol=catalog_fixture(tmp_path)
    frozen=freeze_catalog(catalog,tmp_path,protocol,tmp_path/'frozen.json')
    assert frozen['catalog']['partition_independent_components']==dict(development=1,validation=1,test=1)
    assert verify_frozen(frozen,catalog,tmp_path,protocol,partition='test')['task_ids']==['test']
    with pytest.raises(FileExistsError):freeze_catalog(catalog,tmp_path,protocol,tmp_path/'frozen.json')


@pytest.mark.parametrize('field',['source_group','entity_group','session_group','uri'])
def test_shared_origin_entity_session_and_uri_cannot_cross_partitions(tmp_path,field):
    catalog,_=catalog_fixture(tmp_path)
    rows=[catalog['sources'][0],catalog['sources'][6]]
    for row in rows:row[field]='https://example.org/same-image' if field=='uri' else 'same'
    with pytest.raises(ValueError,match='crosses benchmark'):validate_catalog(catalog,tmp_path)


def test_derivative_ancestry_and_cycles_are_rejected(tmp_path):
    catalog,_=catalog_fixture(tmp_path)
    parent,child=catalog['sources'][0],catalog['sources'][6]
    child.update(kind='derived_image',parents=[parent['source_id']])
    with pytest.raises(ValueError,match='crosses benchmark'):validate_catalog(catalog,tmp_path)
    parent.update(kind='derived_image',parents=[child['source_id']])
    with pytest.raises(ValueError,match='cycle'):validate_catalog(catalog,tmp_path)


def test_known_core_sources_and_historical_urls_only_development(tmp_path):
    catalog,_=catalog_fixture(tmp_path);row=catalog['sources'][6]
    row['known_core_data']=True
    with pytest.raises(ValueError,match='Known Core'):validate_catalog(catalog,tmp_path)
    row['known_core_data']=False;row['uri']=core_history()['uris'][0]
    with pytest.raises(ValueError,match='Known Core'):validate_catalog(catalog,tmp_path)


def test_truth_registered_or_copied_to_dataset_is_rejected(tmp_path):
    catalog,_=catalog_fixture(tmp_path)
    truth=tmp_path/catalog['tasks'][0]['truth_path'];copy=tmp_path/'development/context.json'
    copy.write_bytes(truth.read_bytes())
    (tmp_path/'development/images/truth.json').write_bytes(truth.read_bytes())
    with pytest.raises(ValueError,match='truth copied'):validate_catalog(catalog,tmp_path)
    (tmp_path/'development/images/truth.json').unlink()
    path=tmp_path/'development/context.txt';path.write_bytes(truth.read_bytes())
    regpath=tmp_path/'development/registry.json';reg=read_json(regpath)
    reg['documents']['truth-alias']={'path':str(path),'sha256':file_hash(path)};write_json(regpath,reg)
    with pytest.raises(ValueError,match='truth registered'):validate_catalog(catalog,tmp_path)


@pytest.mark.parametrize('change',['source','truth','task','protocol'])
def test_frozen_input_or_protocol_drift_is_rejected(tmp_path,change):
    catalog,protocol=catalog_fixture(tmp_path)
    frozen=freeze_catalog(catalog,tmp_path,protocol,tmp_path/'frozen.json')
    if change=='protocol':protocol['repetitions']=2
    else:
        path=tmp_path/({'source':catalog['sources'][0]['path'],
                       'truth':catalog['tasks'][0]['truth_path'],'task':catalog['tasks'][0]['task_path']}[change])
        path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError):verify_frozen(frozen,catalog,tmp_path,protocol,partition='test')


def test_unlicensed_or_unmapped_assets_are_rejected(tmp_path):
    catalog,_=catalog_fixture(tmp_path)
    catalog['sources'][0]['license_identifier']=''
    with pytest.raises(ValueError,match='license'):validate_catalog(catalog,tmp_path)
    catalog['sources'][0]['license_identifier']='self-generated'
    catalog['tasks'][0]['image_sources'].pop(next(iter(catalog['tasks'][0]['image_sources'])))
    with pytest.raises(ValueError,match='Every image'):validate_catalog(catalog,tmp_path)


@pytest.mark.parametrize('exposure',['document','selected_dataset','other_dataset'])
def test_other_task_truth_cannot_enter_any_registered_input(tmp_path,exposure):
    catalog,_=catalog_fixture(tmp_path)
    truth=tmp_path/catalog['tasks'][2]['truth_path']
    regpath=tmp_path/'development/registry.json';reg=read_json(regpath)
    if exposure=='document':
        path=tmp_path/'development/context.txt';path.write_bytes(truth.read_bytes())
        reg['documents']['leaked-answer']={'path':str(path),'sha256':file_hash(path)}
    else:
        directory=tmp_path/('development/images' if exposure=='selected_dataset' else 'extra-images')
        directory.mkdir(exist_ok=True)
        (directory/'notes.json').write_bytes(truth.read_bytes())
        if exposure=='other_dataset':
            (directory/'train').mkdir()
            (directory/'train/image.png').write_bytes((tmp_path/'development/images/train/001.png').read_bytes())
            reg['datasets']['extra']=str(directory)
    write_json(regpath,reg)
    with pytest.raises(ValueError,match='Evaluator truth'):validate_catalog(catalog,tmp_path)
