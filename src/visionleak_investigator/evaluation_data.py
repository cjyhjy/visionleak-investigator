"""Evaluator-only source provenance, disjoint partitions and immutable freeze checks.

No model tools import this module. It validates declared provenance and exact
content/URL links; it cannot infer undisclosed physical identity or license rights.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import subprocess
import sys
from importlib.metadata import version
from urllib.parse import urlsplit, urlunsplit, unquote

from .common import PROJECT, read_json, write_json, file_hash, digest, safe_child, now
from .core import child_environment, CoreAdapter
from .domain import Registry, TaskSpec, input_manifest
from .workflow import code_digest

PARTITIONS = ('development','validation','test')


def normalized_uri(value: str) -> str:
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https','generator') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('Source URI must identify a public origin or generator without credentials')
    # Ignore fragments/tracking queries for conservative duplicate-origin grouping.
    scheme='https' if parsed.scheme in ('http','https') else parsed.scheme
    return urlunsplit((scheme,parsed.netloc.lower(),unquote(parsed.path),'',''))


def environment_identity() -> dict:
    return {'python':sys.version.split()[0],'libraries':{name:version(name) for name in ('jsonschema','pillow','psutil')}}


def execution_identity() -> dict:
    return {'core_lock_digest':file_hash(PROJECT/'core.lock.json'),
            'runtime_lock_digest':file_hash(PROJECT/'core.runtime.lock.json'),
            'code_digest':code_digest(),'python_lock_digest':file_hash(PROJECT/'uv.lock'),
            'policy_digest':file_hash(PROJECT/'configs/policy.json'),'environment':environment_identity()}


def core_history() -> dict:
    """Read verified pinned Core provenance; even its historical holdout is known."""
    core=PROJECT/'.deps/visionleak-core'
    lock=read_json(PROJECT/'core.lock.json')
    CoreAdapter(core).verify_artifacts()
    script="import {sourceDigest} from './tools/source-digest.mjs'; console.log(sourceDigest(process.cwd()))"
    source=subprocess.check_output(['node','--input-type=module','-e',script],cwd=core,
                                   env=child_environment(),text=True,timeout=30).strip()
    if source!=lock['source_digest']:raise ValueError('Core history source digest differs from pinned release')
    hashes,urls,records=set(),set(),[]
    for relative in ('research/photos-v1/sources.json','research/photos-v2/sources.json','research/photos-v2/source-candidates.json'):
        path=core/relative
        value=read_json(path)
        records.append({'path':relative,'sha256':file_hash(path)})
        images=value['images'] if 'images' in value else [r for rows in value.values() for r in rows]
        for row in images:
            hashes.update(row[k] for k in ('sha256','downloadSha256') if row.get(k))
            urls.update(normalized_uri(row[k]) for k in ('originUrl','originalUrl','downloadUrl','licenseEvidence') if row.get(k))
    return {'core_commit':lock['commit'],'manifests':records,'sha256':sorted(hashes),'uris':sorted(urls)}


def validate_catalog(catalog: dict, root: Path, *, history: dict | None = None) -> dict:
    if set(catalog)!={'schema_version','sources','tasks'} or catalog['schema_version']!=1:
        raise ValueError('Source catalog schema mismatch')
    if not isinstance(catalog['sources'],list) or not catalog['sources'] or not isinstance(catalog['tasks'],list) or not catalog['tasks']:
        raise ValueError('Nonempty source and task lists required')
    if len(catalog['sources'])>10000 or len(catalog['tasks'])>1000:raise ValueError('Catalog size limit')
    truth_paths=[]
    for row in catalog['tasks']:
        if set(row)!={'task_id','benchmark_partition','task_path','registry_path','truth_path','image_sources'}:raise ValueError('Evaluation task record fields mismatch')
        truth_paths.append(safe_child(root,row['truth_path']))
    truth_hashes={file_hash(path) for path in truth_paths}
    history=core_history() if history is None else history
    historical_hashes=set(history['sha256']);historical_urls=set(history['uris'])
    sources={};parents={};links={};known=set();task_ids=set();tasks=[]
    required={'source_id','source_group','entity_group','session_group','kind','path','sha256','uri',
              'license_identifier','license_evidence_url','redistribution','acquired_at','parents','known_core_data'}
    for row in catalog['sources']:
        if set(row)!=required:raise ValueError('Source record fields mismatch')
        sid=row['source_id']
        if not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}',sid) or sid in sources:raise ValueError('Invalid or duplicate source ID')
        if row['kind'] not in ('synthetic','photograph','derived_image'):raise ValueError('Unknown source kind')
        if type(row['known_core_data']) is not bool:raise ValueError('Known-Core flag must be explicit')
        for field in ('source_group','license_identifier'):
            if not isinstance(row[field],str) or not row[field].strip():raise ValueError('Missing source group/license record')
        for field in ('entity_group','session_group'):
            if row[field] is not None and (not isinstance(row[field],str) or not row[field].strip()):raise ValueError('Invalid group')
        if row['redistribution'] not in ('allowed','restricted'):raise ValueError('Redistribution restriction must be recorded')
        if datetime.fromisoformat(row['acquired_at']).tzinfo is None:raise ValueError('Acquisition time requires timezone')
        uri=normalized_uri(row['uri']);normalized_uri(row['license_evidence_url'])
        if not isinstance(row['sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',row['sha256']):raise ValueError('Invalid content hash')
        if file_hash(safe_child(root,row['path']))!=row['sha256']:raise ValueError('Source content changed')
        if not isinstance(row['parents'],list) or any(not isinstance(p,str) for p in row['parents']) or len(set(row['parents']))!=len(row['parents']):raise ValueError('Invalid source parents')
        if (row['kind']=='derived_image')!=bool(row['parents']):raise ValueError('Derived images require original-source parents')
        sources[sid]=row;parents[sid]=sid
        if row['known_core_data'] or row['sha256'] in historical_hashes or uri in historical_urls:known.add(sid)
    def find(sid):
        while parents[sid]!=sid:
            parents[sid]=parents[parents[sid]];sid=parents[sid]
        return sid
    def union(a,b):
        parents[find(a)]=find(b)
    visiting,visited=set(),set()
    def ancestry(sid):
        if sid not in sources:raise ValueError('Unknown parent source')
        if sid in visiting:raise ValueError('Source ancestry cycle')
        if len(visiting)>64:raise ValueError('Source ancestry depth limit')
        if sid in visited:return
        visiting.add(sid)
        for parent in sources[sid]['parents']:
            ancestry(parent);union(sid,parent)
        visiting.remove(sid);visited.add(sid)
    for sid,row in sources.items():
        ancestry(sid)
        for key,value in [('sha256',row['sha256']),('uri',normalized_uri(row['uri'])),
                          *[(k,row[k]) for k in ('source_group','entity_group','session_group') if row[k]]]:
            if (key,value) in links:union(sid,links[(key,value)])
            else:links[(key,value)]=sid
    for row in catalog['tasks']:
        if set(row)!={'task_id','benchmark_partition','task_path','registry_path','truth_path','image_sources'}:raise ValueError('Evaluation task record fields mismatch')
        if row['task_id'] in task_ids or row['benchmark_partition'] not in PARTITIONS:raise ValueError('Duplicate task ID or invalid partition')
        task_ids.add(row['task_id'])
        taskpath=safe_child(root,row['task_path']);regpath=safe_child(root,row['registry_path']);truthpath=safe_child(root,row['truth_path'])
        task=read_json(taskpath);TaskSpec.parse(task)
        if task['task_id']!=row['task_id']:raise ValueError('Task ID mismatch')
        registry=Registry(read_json(regpath));registry.check_confirmations(task)
        dataset=registry.dataset(task['dataset_ref'])
        if not dataset.is_relative_to(root.resolve()):raise ValueError('Suite dataset must be inside its registered root')
        for ref in registry.value['datasets']:
            other=registry.dataset(ref)
            if not other.is_relative_to(root.resolve()):raise ValueError('Registered dataset must be inside suite root')
            if any(path.is_relative_to(other) or other.is_relative_to(path) for path in truth_paths):raise ValueError('Evaluator truth overlaps a registered dataset')
            registered_input=input_manifest(other,task['limits'])
            if any(f['sha256'] in truth_hashes for f in registered_input['files']):raise ValueError('Evaluator truth copied inside dataset')
        truth_hash=file_hash(truthpath)
        documents={}
        for ref in registry.value.get('documents',{}):
            documents[ref]=file_hash(registry.document(ref))
            if documents[ref] in truth_hashes:raise ValueError('Evaluator truth registered as a model document')
        before=input_manifest(dataset,task['limits']);mapping=row['image_sources']
        images={f['path']:f for f in before['files'] if f['supported_image']}
        if not images or not isinstance(mapping,dict) or set(mapping)!=set(images):raise ValueError('Every image needs a source mapping; empty tasks are not evaluable')
        for name,sid in mapping.items():
            if sid not in sources or images[name]['sha256']!=sources[sid]['sha256']:raise ValueError('Image-source identity mismatch')
        refs=sorted(set(mapping.values()));anchor=refs[0]
        # Shared negatives and other sources within a task form one sampling unit.
        for sid in refs:union(anchor,sid)
        tasks.append({**row,'source_refs':sorted(refs),'task_sha256':file_hash(taskpath),
                      'registry_sha256':file_hash(regpath),'truth_sha256':file_hash(truthpath),
                      'input_digest':before['digest'],'limits_digest':digest(task['limits']),
                      'document_hashes':documents})
    components={};known_components={find(s) for s in known}
    for sid in sources:components.setdefault(find(sid),{'sources':[],'tasks':[],'partitions':set()})['sources'].append(sid)
    for task in tasks:
        key=find(task['source_refs'][0]);component=components[key]
        component['tasks'].append(task['task_id']);component['partitions'].add(task['benchmark_partition'])
        if key in known_components and task['benchmark_partition']!='development':raise ValueError('Known Core sources may only be development/regression data')
    for component in components.values():
        if len(component['partitions'])>1:raise ValueError('Source/entity/session/content component crosses benchmark partitions')
        component['sources'].sort();component['tasks'].sort();component['partitions']=sorted(component['partitions'])
    return {'catalog_digest':digest(catalog),'core_history_digest':digest(history),'tasks':tasks,
            'components':sorted(components.values(),key=lambda c:c['sources']),
            'partition_task_counts':{p:sum(t['benchmark_partition']==p for t in tasks) for p in PARTITIONS},
            'partition_independent_components':{p:sum(c['partitions']==[p] for c in components.values()) for p in PARTITIONS},
            'limitations':['Provenance/license/group labels are declarations; identities not inferred from appearance.',
                           'Exact hashes, origin URIs and declared ancestry/groups are checked.',
                           'Application boundary only; local administrators can read evaluator truth.']}


def freeze_catalog(catalog: dict, root: Path, protocol: dict, out: Path) -> dict:
    if set(protocol)!={'conditions','repetitions','policy_digest','model_configuration','metric_definition'}:
        raise ValueError('Protocol must freeze conditions, repetitions, policy, model and metrics')
    if protocol['conditions']!=['A','B','C','D'] or type(protocol['repetitions']) is not int or not 1<=protocol['repetitions']<=10:
        raise ValueError('Freeze the full A-D comparison and bounded repetitions')
    if protocol['policy_digest']!=file_hash(PROJECT/'configs/policy.json'):raise ValueError('Policy digest mismatch')
    model=protocol['model_configuration']
    if not isinstance(model,dict) or set(model)!={'status','provider','model_id','endpoint','prompt_digest'}:
        raise ValueError('Model freeze fields must be explicit and contain no credentials')
    if model['status'] not in ('not_configured','configured'):raise ValueError('Unknown model configuration status')
    if model['status']=='not_configured' and any(model[k] is not None for k in ('provider','model_id','endpoint','prompt_digest')):
        raise ValueError('Unconfigured model fields must be null')
    if model['status']=='configured':
        if not all(isinstance(model[k],str) and model[k] for k in ('provider','model_id','endpoint','prompt_digest')):raise ValueError('Incomplete model freeze')
        normalized_uri(model['endpoint'])
        if not re.fullmatch(r'[0-9a-f]{64}',model['prompt_digest']):raise ValueError('Prompt digest required')
    if not isinstance(protocol['metric_definition'],str) or not protocol['metric_definition'].strip():raise ValueError('Metric definition required')
    validated=validate_catalog(catalog,root)
    for row in catalog['tasks']:
        task=read_json(safe_child(root,row['task_path']));registry=Registry(read_json(safe_child(root,row['registry_path'])))
        if out.resolve().is_relative_to(registry.dataset(task['dataset_ref'])):raise ValueError('Freeze output must be outside audit inputs')
    payload={'schema_version':1,'created_at':now(),'catalog':validated,'protocol':protocol,
             **execution_identity(),
             'status':'frozen_configuration_only','model_execution':'not_run'}
    frozen={**payload,'freeze_digest':digest(payload)}
    write_json(out,frozen,exclusive=True)
    return frozen


def verify_frozen(frozen: dict, catalog: dict, root: Path, protocol: dict, *, partition: str) -> dict:
    if partition not in PARTITIONS:raise ValueError('Unknown benchmark partition')
    payload={k:v for k,v in frozen.items() if k!='freeze_digest'}
    if digest(payload)!=frozen['freeze_digest']:raise ValueError('Frozen manifest changed')
    if protocol!=frozen['protocol']:raise ValueError('Protocol changed after freeze')
    if protocol['policy_digest']!=file_hash(PROJECT/'configs/policy.json'):raise ValueError('Policy changed after freeze')
    current=validate_catalog(catalog,root)
    if current!=frozen['catalog']:raise ValueError('Catalog, truth, task, input or source history changed after freeze')
    for key,path in [('core_lock_digest','core.lock.json'),('runtime_lock_digest','core.runtime.lock.json')]:
        if frozen[key]!=file_hash(PROJECT/path):raise ValueError('Core/runtime changed after freeze')
    if frozen['code_digest']!=code_digest():raise ValueError('Implementation changed after freeze')
    if frozen['python_lock_digest']!=file_hash(PROJECT/'uv.lock') or frozen['environment']!=environment_identity():raise ValueError('Python dependencies changed after freeze')
    return {'status':'verified','partition':partition,'freeze_digest':frozen['freeze_digest'],
            'task_ids':[t['task_id'] for t in current['tasks'] if t['benchmark_partition']==partition],
            'independent_components':current['partition_independent_components'][partition],
            'model_execution':'not_run','meaning':'Input/configuration gate only; not an experiment result'}
