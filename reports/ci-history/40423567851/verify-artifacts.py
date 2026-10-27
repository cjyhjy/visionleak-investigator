"""Reverify downloaded CI artifacts without modifying historical absolute-path registries."""
import json
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

from visionleak_investigator.common import read_json,file_hash,digest,write_json,now
from visionleak_investigator.core import CoreAdapter
from visionleak_investigator.domain import input_manifest
from visionleak_investigator.evaluation import comparable,resource_totals
from visionleak_investigator.reporting import ClaimValidator
from visionleak_investigator.workflow import code_digest
from visionleak_investigator.evaluation_scoring import validate_truth,score_labels,AXES
from visionleak_investigator.evaluation_runner import summarize_quality

class Page(HTMLParser):
    def __init__(self,text):
        super().__init__();self.ids=[];self.links=[];self.images=[];self.tags=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        self.tags.append(tag);attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='a':self.links.append(attrs['href'])
        if tag=='img':self.images.append(attrs['src'])

base=Path(__file__).resolve().parent;run=read_json(base/'github-run.json')
assert run['conclusion']=='success' and run['headSha']=='3146889f60274866955845dfcdbaef183628a139'
download=read_json(base/'download.json');results=[]
adapter=CoreAdapter();adapter.verify_artifacts()
for artifact in download['artifacts']:
    directory=base/artifact['platform']
    for entry in artifact['files']:assert file_hash(directory/entry['path'])==entry['sha256']
    suite=ET.parse(directory/'reports/ci/junit.xml').find('testsuite')
    assert {k:suite.attrib[k] for k in ('tests','failures','errors','skipped')}==dict(tests='204',failures='0',errors='0',skipped='0')
    commands=read_json(directory/'commands.json')
    assert len(commands)==18 and all(c['exit_code']==0 for c in commands)
    original=Path(commands[0]['cwd'])
    def relocate(value):return directory/Path(value).relative_to(original)
    checked=[];metadata_field_reports=0;rules_reports=0
    for path in sorted((directory/'runs').rglob('report.json')):
        audit=path.parent
        if not all((audit/name).exists() for name in ('validation.json','manifest.json','checkpoint.json')):continue
        if not read_json(audit/'checkpoint.json').get('report_digest'):continue
        report=read_json(path);validation=read_json(audit/'validation.json');manifest=read_json(audit/'manifest.json')
        checkpoint=read_json(audit/'checkpoint.json')
        assert checkpoint['report_digest']==digest(report) and checkpoint['manifest_digest']==digest(manifest)
        assert read_json(audit/'ledger.json')==report['budget']
        pub=report['publication'];assert pub['full_render_calls']==1
        assert pub['html_sha256']==file_hash(audit/'report.html')
        entry=next(e for e in report['budget']['entries'] if e['call_id']==pub['finalization_call_id'])
        assert entry['status']=='settled' and entry['actual']['wall_seconds']==pub['measured_wall_seconds']
        assert checkpoint['state']==report['state']
        if 'rules' in report:
            rules=read_json(audit/'rules-decision.json');policy=read_json(audit/'rules-policy.json')
            assert file_hash(audit/'rules-decision.json')==validation['rules_decision_sha256']
            assert file_hash(audit/'rules-policy.json')==validation['rules_policy_sha256']
            assert report['rules']==rules and digest(policy)==rules['policy_digest']==manifest['policy']['config_digest']
            assert rules['initial_task_digest']==manifest['policy']['initial_task_digest']
            assert rules['dataset_manifest_digest']==manifest['dataset_manifest_digest']
            assert rules['policy_version']==policy['policy_version']=='rules-v2' and rules['model_calls']==0
            assert policy['max_audits']==manifest['policy']['max_audits']==3
            assert report['budget']['spent']['audit_runs']<=3
            assert report.get('publication',{}).get('html_kind')=='overrun_status_receipt' or '初始规则选择' in (audit/'report.html').read_text()
            rules_reports+=1
        if report.get('recovery'):
            recovery=read_json(audit/'recovery-receipt.json')
            assert recovery==report['recovery'] and digest(recovery)==checkpoint['recovery_receipt_digest']
            for item in recovery['preserved_files']:assert file_hash(audit/item['path'])==item['sha256']
        if report.get('revision') and 'processor_code_digest' in report['revision']:
            assert report['revision']['processor_code_digest']==manifest['code_digest']==code_digest()
            assert report['revision']['image_evidence_code_digest']==manifest['image_evidence_origin']['investigator_code_digest']
            parent=relocate(manifest['evidence_reused_from'])
            assert digest(read_json(parent/'manifest.json'))==manifest['parent_manifest_digest']
            assert digest(read_json(parent/'report.json'))==manifest['parent_report_digest']
        assert validation['evidence_sha256']==file_hash(audit/'evidence.jsonl')
        assert digest(read_json(audit/'task.json'))==manifest['task_digest']
        registry=read_json(audit/'registry.private.json');assert digest(registry)==manifest['registry_digest']
        for document in registry.get('documents',{}).values():assert file_hash(relocate(document['path']))==document['sha256']
        metadata=report['coverage']['metadata']
        if 'field_coverage' in metadata:
            import csv
            document=relocate(registry['documents'][report['task']['metadata_ref']]['path'])
            with document.open(encoding='utf-8-sig',newline='') as stream:
                reader=csv.DictReader(stream);headers=reader.fieldnames;source_rows=list(reader)
            assert metadata['columns']==headers
            optional=['image_split','entity_id','capture_session_id','provenance_ref']
            assert metadata['missing_optional_columns']==[name for name in optional if name not in headers]
            assert set(metadata['field_coverage'])==set(['file_id','relative_path',*optional,*([report['task']['entity_key']] if report['task']['entity_key'] else [])])
            for field,counts in metadata['field_coverage'].items():
                absent=sum(row.get(field) is None for row in source_rows)
                empty=sum(isinstance(row.get(field),str) and not row[field].strip() for row in source_rows)
                state='missing_column' if field not in headers else 'no_rows' if not source_rows else 'partial' if absent+empty else 'complete'
                assert counts==dict(column_present=field in headers,nonempty_rows=len(source_rows)-absent-empty,absent_value_rows=absent,empty_value_rows=empty,missing_rows=absent+empty,state=state)
            assert report.get('publication',{}).get('html_kind')=='overrun_status_receipt' or '未提供的可选列' in (audit/'report.html').read_text()
            metadata_field_reports+=1
        dataset=relocate(registry['datasets'][report['task']['dataset_ref']])
        assert input_manifest(dataset,report['task']['limits'])['digest']==manifest['dataset_manifest_digest']
        if 'model_ledger_sha256' in validation:assert validation['model_ledger_sha256']==file_hash(audit/'model-ledger.json')
        assert report['model_execution']=='not_run' and report['coverage']['source_unchanged']
        evidence={r['evidence_id']:r for r in map(json.loads,(audit/'evidence.jsonl').read_text().splitlines())}
        from visionleak_investigator.review_state import review_coverage
        if 'human_review_coverage_digest' in validation:
            assert report['coverage']['human_review']==review_coverage(report['reviews'])
            assert digest(report['coverage']['human_review'])==validation['human_review_coverage_digest']
            refs={p for ev in evidence.values() if ev['kind'].startswith('human.') for p in ev['source_positions']}
            assert refs==set(validation['review_inputs'])
            for ev in evidence.values():
                if not ev['kind'].startswith('human.'):continue
                assert digest(ev['facts'])==ev['params_digest']
                for ref in ev['source_positions']:
                    assert not Path(ref).is_absolute() and '..' not in Path(ref).parts
                    assert read_json(audit/ref)==ev['facts'] and file_hash(audit/ref)==validation['review_inputs'][ref]
            for review in report['reviews']:
                if review['status']=='pending':continue
                assert evidence[review['pair_ref']]['verification_state']['human_review']==review['status']
                assert any(ev['kind'].startswith('human.') and ev['facts']['pair_ref']==review['pair_ref'] and ev['facts']['decision']==review['status'] for ev in evidence.values())
        coverage={**report['coverage']['profiles'],'metadata':report['coverage']['metadata'],'human_review':report['coverage']['human_review']}
        for claim in report['claims']:ClaimValidator().validate_claim(claim,evidence,coverage)
        for profile,cov in report['coverage']['profiles'].items():
            raw=audit/cov['report_ref'];assert file_hash(raw)==cov['report_sha256']==validation['core_reports'][profile]
            adapter.inspect_report(raw,dataset)
        page=Page((audit/'report.html').read_text())
        assert len(page.ids)==len(set(page.ids)) and 'script' not in page.tags
        for href in page.links:
            if href.startswith('#'):assert href[1:] in page.ids
            else:assert not Path(href).is_absolute() and '..' not in Path(href).parts and (audit/href).is_file()
        for image in page.images:
            assert not Path(image).is_absolute() and '..' not in Path(image).parts and (audit/image).is_file()
        for ev in evidence.values():
            if ev.get('images'):
                prefix=ev['source_positions'][0].split('#')[0].rsplit('/',1)[0]
                for image in ev['images']:assert file_hash(audit/prefix/image['thumbnail'])==image['thumbnailDigest']
        checked.append({'report':str(path.relative_to(directory)),'mode':report['mode'],'state':report['state']})
    assert len(checked)==84 and sum(r['mode']=='scripted_test_only' for r in checked)==2
    gate=directory/'runs/ci-evaluation-gates';receipt=read_json(gate/'receipt.json')
    assert receipt['status']=='passed' and receipt['model_calls']==0 and len(receipt['commands'])==9
    frozen=read_json(gate/'frozen.json');assert digest({k:v for k,v in frozen.items() if k!='freeze_digest'})==frozen['freeze_digest']==receipt['freeze_digest']
    assert frozen['code_digest']==code_digest()
    for c in receipt['commands']:
        result=read_json(gate/c['record']);assert result['exit_code']==c['exit_code'] and result['error'] is None
    assert sum(c['exit_code']==1 for c in receipt['commands'])==3
    for part in ('development','validation','test'):
        check=read_json(gate/f'checked-{part}.json')
        assert check['freeze_digest']==frozen['freeze_digest'] and check['independent_components']==1
    resources=directory/'runs/ci-resources';frozen=read_json(resources/'frozen_config.json')
    assert frozen['runtime_lock_digest']==file_hash(directory/'core.runtime.lock.json')
    assert frozen['code_digest']==code_digest()
    rows=list(map(json.loads,(resources/'per_run.jsonl').read_text().splitlines()))
    assert len(rows)==12
    assert resource_totals(rows)==read_json(resources/'metrics.json')['resources_by_condition']
    manifests={}
    for row in rows:
        if row['condition']=='D':assert row['state']=='blocked';continue
        assert row['state'] in ('COMPLETED','PARTIAL')
        record=read_json(resources/row['process_record']/'result.json')
        assert record['resources']==row['full_task_resources']
        assert record['resources']['cpu_seconds']>0 and record['resources']['tree_rss_status']=='sampled'
        assert record['resources']['tree_rss_peak_bytes']>0
        m=read_json(resources/row['run']/'manifest.json');t=read_json(resources/row['run']/'task.json')
        assert all(m[k]==frozen[k] for k in ('core_lock_digest','runtime_lock_digest','code_digest'))
        manifests.setdefault(row['task_id'],[]).append((m,t))
    for entries in manifests.values():comparable(entries)
    catalog_base=directory/'runs/ci-catalog-execution'
    cr=read_json(catalog_base/'receipt.json');cf=read_json(catalog_base/'frozen.json')
    catalog=read_json(catalog_base/'suite/catalog.json')
    assert cr['status']=='passed' and cr['tasks']==3 and cr['real_task_runs']==9 and cr['models_called']==0
    assert digest({k:v for k,v in cf.items() if k!='freeze_digest'})==cf['freeze_digest']==cr['freeze_digest']
    assert cf['code_digest']==code_digest() and cf['catalog']['catalog_digest']==digest(catalog)
    assert cf['runtime_lock_digest']==file_hash(directory/'core.runtime.lock.json')
    for source in catalog['sources']:assert file_hash(catalog_base/'suite'/source['path'])==source['sha256']
    for c in cr['commands']:
        result=read_json(catalog_base/c['record'])
        assert result['exit_code']==c['expected_exit']==c['exit_code'] and result['error'] is None
    assert len(cr['commands'])==5 and cr['commands'][-1]['exit_code']==1
    assert not (catalog_base/'duplicate-test').exists()
    cat_measured=0
    for taskrow in cf['catalog']['tasks']:
        source_root=catalog_base/'suite'
        taskpath=source_root/taskrow['task_path'];regpath=source_root/taskrow['registry_path'];truthpath=source_root/taskrow['truth_path']
        assert file_hash(taskpath)==taskrow['task_sha256'] and file_hash(regpath)==taskrow['registry_sha256'] and file_hash(truthpath)==taskrow['truth_sha256']
        task=read_json(taskpath);reg=read_json(regpath);truth=read_json(truthpath)
        im=input_manifest(relocate(reg['datasets'][task['dataset_ref']]),task['limits'])
        assert im['digest']==taskrow['input_digest']
        ti=validate_truth(truth,task,im)
        result_root=catalog_base/'results'/taskrow['benchmark_partition']
        metrics=read_json(result_root/'metrics.json')
        erows=list(map(json.loads,(result_root/'per_run.jsonl').read_text().splitlines()))
        assert len(erows)==4 and metrics['quality']==summarize_quality(erows)
        assert metrics['resources_by_condition']==resource_totals(erows)
        assert metrics['declared_independent_components']==1 and metrics['model_calls']==0
        assert all(g['status']=='passed' for g in map(json.loads,(result_root/'gate_checks.jsonl').read_text().splitlines()))
        cm=[]
        for row in erows:
            assert row['expected_truth_denominators']==ti['truth_denominators']
            if row['condition']=='D':assert row['state']=='blocked' and 'score' not in row;continue
            audit=result_root/row['run'];report=read_json(audit/'report.json')
            score=read_json(result_root/'scores'/task['task_id']/'r01'/row['condition']/'score.json')
            assert score==row['score'] and score['truth_sha256']==file_hash(truthpath)
            assert score['truth_digest']==digest(truth) and score['dataset_manifest_digest']==im['digest']
            es={e['evidence_id']:e for e in map(json.loads,(audit/'evidence.jsonl').read_text().splitlines())}
            exact=set();candidates=set()
            for claim in report['claims']:
                refs=[es[ref] for ref in claim['evidence_refs']]
                if claim['status']=='confirmed' and claim['claim_type'] in ('byte_identity','pixel_identity'):
                    exact.update(tuple(sorted(e['files'])) for e in refs)
                if claim['status']=='candidate' and claim['claim_type']=='perceptual_relation':
                    candidates.update(tuple(sorted(e['files'])) for e in refs)
            true_exact={tuple(sorted(p)) for p in truth['exact']['positive_pairs']}
            predictions={'exact':exact,'related_excluding_exact':candidates-true_exact,'entity_goal_conflict':set()}
            for axis in AXES:
                expected=score_labels(predictions[axis],truth[axis],ti['eligible_approximate_pairs' if axis=='related_excluding_exact' else 'eligible_cross_split_pairs'])
                assert score[axis]==expected
            assert score['candidate_burden']==len(candidates) and score['exact']['truth_denominator']==3
            worker=read_json(result_root/row['process_record']/'result.json')
            scorer=read_json(result_root/row['scorer_record']/'result.json')
            assert '--truth' not in worker['argv'] and '--truth' in scorer['argv']
            assert scorer['exit_code']==0 and scorer['error'] is None
            assert worker['resources']==row['full_task_resources'] and scorer['resources']==row['scoring_resources']
            assert worker['resources']['cpu_seconds']>0 and worker['resources']['tree_rss_status']=='sampled'
            assert worker['resources']['tree_rss_peak_bytes']>0
            if row['condition']=='B':assert report['budget']['spent']['audit_runs']==1 and list(report['coverage']['profiles'])==['all']
            m=read_json(audit/'manifest.json');assert all(m[k]==cf[k] for k in ('core_lock_digest','runtime_lock_digest','code_digest'))
            cm.append((m,task));cat_measured+=1
        comparable(cm)
    assert cat_measured==9
    lifecycle=directory/'runs/ci-lifecycle';lr=read_json(lifecycle/'receipt.json')
    assert lr['status']=='passed' and lr['code_digest']==code_digest() and lr['model_calls']==0
    assert len(lr['reports'])==5
    for item in lr['reports']:
        host=lifecycle/item['run']
        assert file_hash(host/'report.json')==item['report_sha256'] and file_hash(host/'manifest.json')==item['manifest_sha256']
    recovered=read_json(lifecycle/'recovery/run/report.json')
    assert recovered['state']=='PARTIAL' and not recovered['claims']
    assert (lifecycle/'recovery/run/evidence.jsonl').read_bytes()==b''
    assert not read_json(lifecycle/'recovery/run/proposal.json')['proposed_exclusions']
    after=next(item for item in lr['reports'] if item['case']=='revision_after_recovery')
    after_report=read_json(lifecycle/after['run']/'report.json')
    assert not after_report['revision']['image_evidence_reused'] and after_report['revision']['reused_core_evidence_count']==0
    assert not after_report['claims'] and not after_report['reviews']
    negative=read_json(lifecycle/'negative/score.json')
    assert negative['exact']['predicted_pairs']==0 and negative['related_excluding_exact']['fp']==4
    assert negative['related_excluding_exact']['precision']==0 and negative['related_excluding_exact']['recall'] is None
    assert negative['candidate_burden']==negative['pending_review_pairs']==4
    from visionleak_investigator.plan_check import check_manifest
    planbase=directory/'runs/ci-plan-check';pr=read_json(planbase/'receipt.json')
    assert pr['status']=='passed' and pr['code_digest']==code_digest() and pr['model_calls']==0
    assert pr['source_unchanged'] and pr['original_audit_files_unchanged'] and len(pr['cases'])==4
    planrun=planbase/'run';pm=read_json(planrun/'manifest.json');pt=read_json(planrun/'task.json')
    source=read_json(planrun/'input-manifest.json')
    pe=list(map(json.loads,(planrun/'evidence.jsonl').read_text().splitlines()))
    assert digest(pm)==pr['audit_manifest_digest']
    for item in pr['cases']:
        cmd=read_json(planbase/item['command']);assert cmd['exit_code']==item['exit_code'] and cmd['error'] is None
        plan=read_json(planbase/item['candidate_manifest'])
        if item['exit_code']==1:
            assert item['result'] is None
            try:check_manifest(pt,pe,source,plan)
            except ValueError:pass
            else:raise AssertionError('Invalid plan unexpectedly accepted')
        else:
            actual=read_json(planbase/item['result']);expected=check_manifest(pt,pe,source,plan)
            assert all(actual[k]==v for k,v in expected.items())
            assert actual['candidate_manifest_digest']==digest(plan) and actual['audit_manifest_digest']==digest(pm)
            assert actual['audit_report_digest']==digest(read_json(planrun/'report.json'))
            assert actual['evidence_sha256']==file_hash(planrun/'evidence.jsonl')
            assert actual['image_reaudit']=='not_run' and actual['execution']['core_audit_runs']==0
    partial=directory/'runs/ci-partial-report';fr=read_json(partial/'receipt.json')
    assert fr['status']=='passed' and fr['code_digest']==code_digest() and fr['model_calls']==0
    assert fr['accepted_core_evidence']==fr['accepted_claims']==0 and fr['host_state']=='PARTIAL'
    host=read_json(partial/'run/report.json');assert not host['claims'] and not host['coverage']['profiles']
    fault=fr['faults'][0];whole=partial/fault['original_report'];broken=partial/fault['truncated_report']
    assert file_hash(whole)==fault['original_sha256'] and file_hash(broken)==fault['truncated_sha256']
    assert broken.read_bytes()==whole.read_bytes()[:fault['original_bytes']//2]
    try:read_json(broken)
    except ValueError:pass
    else:raise AssertionError('Injected half report is still valid JSON')
    original_report=read_json(whole);assert original_report['complete'] and original_report['auditId']==fault['original_audit_id']
    adapter.inspect_report(whole,partial/'fixture/images')
    tooldir=broken.parents[1]
    assert all(file_hash(tooldir/name)==sha for name,sha in fault['preserved_tool_logs'].items())
    assert read_json(tooldir/'result.json')['exit_code']==fault['original_exit_code']==0
    assert fr['audit_charge']['status']=='unknown' and fr['audit_charge']['actual']==fr['audit_charge']['reservation']
    assert fr['audit_charge'] in host['budget']['entries']
    assert not any(e['status']=='pending' for e in host['budget']['entries'])
    assert any(e['kind']=='finalize' and e['status']=='settled' for e in host['budget']['entries'])
    import csv,itertools
    from visionleak_investigator.evaluation import score_pairs
    from visionleak_investigator.interaction_evaluation import summarize_interaction
    from visionleak_investigator.interaction_scoring import validate_interaction_truth
    exportbase=directory/'runs/ci-proposal-export';export=read_json(exportbase/'receipt.json')
    assert export['status']=='passed' and export['code_digest']==code_digest() and export['model_calls']==0
    suggestion=read_json(exportbase/'exports/suggestion.json')
    with (exportbase/'exports/suggestion.csv').open(newline='') as source:csvrows=list(csv.DictReader(source))
    decode=lambda text:json.loads(text[5:])
    assert len(csvrows)==6 and [{'path':decode(r['path']),'image_split':decode(r['image_split']),'included':r['proposed_included']=='true'} for r in csvrows]==suggestion['new_manifest']
    for record in export['exports']:
        assert record['sha256']==file_hash(relocate(record['output'])) and record['requires_approval'] and record['image_reaudit']=='not_run'
    interaction=directory/'runs/ci-interaction';ir=read_json(interaction/'receipt.json');ic=read_json(interaction/'suite/catalog.json');iff=read_json(interaction/'frozen.json')
    assert ir['status']=='passed' and ir['code_digest']==code_digest() and ir['real_C_runs']==ir['D_blocked']==12
    assert iff['code_digest']==code_digest() and iff['protocol']['conditions']==['C','D'] and iff['protocol']['metric_definition']=='interaction-v1'
    assert digest({k:v for k,v in iff.items() if k!='freeze_digest'})==iff['freeze_digest']
    assert iff['catalog']['catalog_digest']==digest(ic)
    for source in ic['sources']:assert file_hash(interaction/'suite'/source['path'])==source['sha256']
    interaction_scores=[];blocked=0
    by_id={row['task_id']:row for row in iff['catalog']['tasks']}
    for command in ir['commands']:
        result=read_json(interaction/command['record']);assert result['exit_code']==command['exit_code'] and result['error'] is None
    assert not (interaction/'duplicate-test').exists()
    for partition in ('development','validation','test'):
        resultsroot=interaction/'results'/partition;metrics=read_json(resultsroot/'metrics.json')
        rows=list(map(json.loads,(resultsroot/'per_run.jsonl').read_text().splitlines()))
        assert metrics['status']=='completed' and metrics['quality']==summarize_interaction(rows)
        assert metrics['human_participants']==0 and metrics['human_time_saved_seconds'] is None and metrics['model_calls']==0
        assert all(g['status']=='passed' for g in map(json.loads,(resultsroot/'gate_checks.jsonl').read_text().splitlines()))
        for row in rows:
            if row['condition']=='D':
                assert row['state']=='blocked' and 'score' not in row;blocked+=1;continue
            taskrow=by_id[row['task_id']];taskpath=interaction/'suite'/taskrow['task_path'];regpath=interaction/'suite'/taskrow['registry_path'];truthpath=interaction/'suite'/taskrow['truth_path']
            assert file_hash(taskpath)==taskrow['task_sha256'] and file_hash(regpath)==taskrow['registry_sha256'] and file_hash(truthpath)==taskrow['truth_sha256']
            task=read_json(taskpath);registry=read_json(regpath);truth=read_json(truthpath)
            original_input=input_manifest(relocate(registry['datasets'][task['dataset_ref']]),task['limits'])
            info=validate_interaction_truth(truth,task,original_input)
            host=resultsroot/row['run'];report=read_json(host/'report.json');score=row['score']
            transcriptpath=resultsroot/row['transcript'];transcript=list(map(json.loads,transcriptpath.read_text().splitlines()))
            initial=transcriptpath.parent/transcript[0]['run']
            assert read_json(initial/'task.json')==task and read_json(initial/'registry.private.json')==registry
            assert host==transcriptpath.parent/transcript[-1]['run'] and not transcript[-1]['answered_questions']
            assert score['initial_task_digest']==digest(task) and score['initial_registry_digest']==digest(registry)
            assert score['question_history_usable'] is True
            assert score['accepted_output']==dict(report_digest=digest(report),run_manifest_digest=digest(read_json(host/'manifest.json')),initial_report_digest=digest(read_json(initial/'report.json')),verified_revision_count=len(transcript)-1)
            mutable={'goal','goal_confirmed','goal_evidence_refs','entity_key','entity_key_confirmed','entity_key_evidence_refs'}
            for i,observation in enumerate(transcript):
                stage=transcriptpath.parent/observation['run'];stage_report=read_json(stage/'report.json');stage_registry=read_json(stage/'registry.private.json')
                assert {k:v for k,v in stage_report['task'].items() if k not in mutable}=={k:v for k,v in task.items() if k not in mutable}
                assert {k:v for k,v in stage_registry.items() if k!='confirmations'}=={k:v for k,v in registry.items() if k!='confirmations'}
                assert all(stage_registry['confirmations'].get(k)==v for k,v in registry['confirmations'].items())
                assert read_json(stage/'manifest.json')['dataset_manifest_digest']==original_input['digest']
                if i:
                    parent=transcriptpath.parent/transcript[i-1]['run'];record=read_json(stage/'manifest.json')
                    assert relocate(record['evidence_reused_from'])==parent
                    assert record['parent_report_digest']==digest(read_json(parent/'report.json'))
                    assert record['parent_manifest_digest']==digest(read_json(parent/'manifest.json'))
                    assert read_json(stage/'answers.input.json')==read_json(transcriptpath.parent/transcript[i-1]['answer_path'])
            asked=[];answered=[]
            for observation in transcript:
                observed=read_json(transcriptpath.parent/observation['run']/'report.json')
                assert digest(observed)==observation['report_digest'] and observation['questions']==observed['questions']
                asked.extend(q['question_code'] for q in observation['questions']);answered+=observation['answered_questions']
                if observation['answered_questions']:
                    payload=read_json(transcriptpath.parent/observation['answer_path']);expected={'actor':'fixed scripted answer broker; no human participant'}
                    for question in observation['answered_questions']:
                        assert question in {q['question_code'] for q in observation['questions']}
                        expected.update(truth['answerable_questions'][question])
                    assert payload==expected
                    result=read_json(transcriptpath.parent/observation['answer_result']);assert result['exit_code'] in (0,2,3) and result['error'] is None
            needed=set(truth['necessary_questions'])
            assert score['necessary_questions']==len(needed) and score['necessary_questions_asked']==len(needed&set(asked))
            assert score['necessary_questions_missed']==sorted(needed-set(asked)) and score['questions_asked']==len(asked)
            assert score['excessive_questions']==len(asked)-len(needed&set(asked)) and score['answers_delivered']==len(answered)
            assert score['unanswerable_questions']==sum(q not in truth['answerable_questions'] for q in asked)
            assert score['goal_correct']==bool(report['task']['goal_confirmed'] and report['task']['goal']==truth['goal'])
            field=bool(report['task']['entity_key_confirmed'] and report['task']['entity_key']==truth['entity_key']) if info['field_interpretation_required'] else None
            assert score['field_correct']==field
            records={e['evidence_id']:e for e in map(json.loads,(host/'evidence.jsonl').read_text().splitlines())};predicted=set();splits={f['path']:f['image_split'] for f in original_input['files'] if f['supported_image']}
            for claim in report['claims']:
                if claim['claim_type']=='goal_conflict' and claim['status']=='confirmed':
                    for ref in claim['evidence_refs']:
                        witness=records[ref]
                        if witness['kind']=='metadata.entity_overlap':predicted.update(tuple(sorted((a,b))) for a,b in itertools.combinations(witness['files'],2) if splits[a]!=splits[b])
            assert score['risk']==score_pairs(predicted,{tuple(sorted(p)) for p in truth['risk_positive_pairs']})
            assert score['truth_digest']==digest(truth) and score['truth_sha256']==file_hash(truthpath) and score['unsupported_confirmed_claims']==0
            assert score['question_budget_spent']==report['budget']['spent']['questions']==len(asked)
            assert score['review_budget_spent']==0 and score['human_time_saved_seconds'] is None and score['budget_respected']
            assert row['costs_complete'] and row['costs']==report['budget']['spent'] and row['costs']['audit_runs']==1
            measured=[]
            for record in row['processes']:
                actual=read_json(resultsroot/record['record']/'result.json');assert actual==record['result'] and '--truth' not in actual['argv']
                assert actual['resources']['cpu_seconds']>0 and actual['resources']['tree_rss_peak_bytes']>0
                measured.append(actual['resources'])
            assert row['worker_resources']['cpu_seconds']==sum(r['cpu_seconds'] for r in measured)
            assert row['worker_resources']['max_sampled_tree_rss_bytes']==max(r['tree_rss_peak_bytes'] for r in measured)
            scorer=read_json(resultsroot/row['scorer_record']/'result.json');assert scorer['exit_code']==0 and '--truth' in scorer['argv']
            assert scorer['resources']==row['scoring_resources']
            interaction_scores.append(score)
    assert len(interaction_scores)==blocked==12
    negative=read_json(interaction/'binding-negative-cases.json')
    assert len(negative)==ir['binding_negative_cases']==6 and ir['metadata_missing_columns_recorded']
    for item in negative:
        supplied=interaction/item['supplied_run'];report=read_json(supplied/'report.json');record=read_json(supplied/'manifest.json');score=item['score']
        assert not score['usable_output'] and score['accepted_output'] is None and score['unsupported_confirmed_claims'] is None
        assert score['risk']['fn']==score['risk']['truth_denominator']==len(item['truth']['risk_positive_pairs'])==8
        assert score['risk']['tp']==score['risk']['fp']==0 and not score['question_history_usable']
        assert score['questions_asked']==score['answers_delivered']==0 and score['question_budget_spent'] is None
        assert score['initial_task_digest']==digest(item['task']) and score['initial_registry_digest']==digest(item['registry'])
        if item['case']=='task_id':assert report['task']['task_id']!=item['task']['task_id']
        elif item['case']=='limits':assert report['task']['limits']!=item['task']['limits']
        elif item['case']=='registry':assert read_json(supplied/'registry.private.json')!=item['registry']
        elif item['case']=='input':assert record['dataset_manifest_digest']!=item['truth']['dataset_manifest_digest']
        elif item['case']=='initial_goal':assert report['task']!=item['task']
        elif item['case']=='foreign_transcript':
            foreign=list(map(json.loads,(interaction/item['supplied_transcript']).read_text().splitlines()))
            assert foreign[0]['report_digest']!=digest(report)
        else:raise AssertionError('Unexpected negative case')
    assert sum(s['goal_correct'] for s in interaction_scores)==10 and sum(s['risk']['fn'] for s in interaction_scores)==27
    reviews=directory/'runs/ci-review-lifecycle';rr=read_json(reviews/'receipt.json')
    assert rr['status']=='passed' and rr['code_digest']==code_digest() and rr['model_calls']==0 and len(rr['reports'])==4
    reviewed={}
    for item in rr['reports']:
        host=reviews/item['run'];assert file_hash(host/'report.json')==item['report_sha256'] and file_hash(host/'manifest.json')==item['manifest_sha256']
        reviewed[item['case']]=read_json(host/'report.json')
    assert any(c['claim_type']=='same_source_review' for c in reviewed['confirmed']['claims'])
    assert all(c['claim_type']!='same_source_review' for c in reviewed['rejected']['claims'])
    assert all(c['claim_type']!='same_source_review' for c in reviewed['goal_revision']['claims'])
    assert reviewed['rejected']['revision']['superseded_review_evidence_refs']
    assert reviewed['goal_revision']['budget']['spent']['audit_runs']==reviewed['original']['budget']['spent']['audit_runs']
    rb=directory/'runs/ci-rules-routing';routing=read_json(rb/'receipt.json')
    assert routing['status']=='passed' and routing['code_digest']==code_digest()
    assert routing['model_calls']==routing['human_participants']==0 and len(routing['cases'])==13 and len(routing['reports'])==14
    from visionleak_investigator.common import PROJECT
    assert routing['policy_sha256']==file_hash(PROJECT/'configs/policy.json')
    expectation={'context_transform':'transform','direct_transform':'transform','context_local':'local','combined_sources':'all','no_clues':None,'negated':None,'truncated':None,'csv_context':None,'audit_limit':'transform','decode_limit':'transform','partial_base':'transform','injection':'all','clarification':'transform'}
    deferred={'audit_limit':'max_core_audit_runs','decode_limit':'decode_and_verify_budget','partial_base':'base_incomplete'}
    routed={}
    for row in routing['cases']:
        host=rb/row['run'];report=read_json(host/'report.json');decision=report['rules'];case=row['case'];routed[case]=report
        selected=expectation[case];profiles=['base']+([selected] if selected and case not in deferred else [])
        assert row['selected_profile']==decision['selected_profile']==selected
        assert row['profiles']==list(report['coverage']['profiles'])==profiles
        assert row['source_unchanged'] and report['coverage']['source_unchanged']
        assert report['state']==('WAITING_USER' if case=='clarification' else 'PARTIAL' if case in deferred else 'COMPLETED')
        if case in deferred:assert decision['decision']=='defer' and decision['reason_code']==deferred[case]
        elif selected:assert decision['decision']=='run' and decision['outcome']=='accepted'
        else:assert decision['decision']=='stop' and decision['reason_code']=='no_positive_clues'
        process=read_json(rb/row['process']);assert process['error'] is None and process['exit_code'] in (0,2,3)
        assert process['resources']['cpu_seconds']>0 and process['resources']['tree_rss_status']=='sampled'
        task=read_json(host/'task.json');reg=read_json(host/'registry.private.json')
        for source in decision['hints']['inputs']:
            if source['source']=='request_text':text=task['request_text']
            else:
                doc=reg['documents'][source['context_ref']];path=relocate(doc['path'])
                assert file_hash(path)==source['sha256']==doc['sha256']
                text=path.read_text()[:8000]
            assert source['excerpt_digest']==digest(text) and source['characters']==len(text)
        entries=report['budget']['entries'];assert sum(e['kind']=='interpret_context' for e in entries)==1
        kinds=[e['kind'] for e in entries]
        assert kinds.index('audit')<kinds.index('interpret_context')
        if len(profiles)==2:assert kinds.index('interpret_context')<max(i for i,k in enumerate(kinds) if k=='audit')
    assert routed['context_transform']['coverage']['input_manifest_digest']==routed['direct_transform']['coverage']['input_manifest_digest']
    for row in routing['reports']:
        host=rb/row['run'];assert file_hash(host/'report.json')==row['report_sha256'] and file_hash(host/'manifest.json')==row['manifest_sha256']
        if row['case']=='clarification_revision':
            revised=read_json(host/'report.json');initial=routed['clarification']
            assert revised['rules']==initial['rules'] and revised['budget']['spent']['audit_runs']==initial['budget']['spent']['audit_runs']
    rb=directory/'runs/ci-revision-budget';revision=read_json(rb/'receipt.json')
    assert revision['status']=='passed' and revision['code_digest']==code_digest()
    assert revision['model_calls']==revision['human_participants']==0 and len(revision['cases'])==4 and len(revision['reports'])==7
    for row in revision['reports']:
        host=rb/row['run'];assert file_hash(host/'report.json')==row['report_sha256'] and file_hash(host/'manifest.json')==row['manifest_sha256']
    for row in revision['cases']:
        assert row['source_unchanged'] and row['original_ledger_unchanged']
        anchor=rb/row['initial_run'];initial=read_json(anchor/'report.json')
        assert not (anchor/'pending-revision.json').exists()
        for item in row['processes']:
            record=read_json(rb/item['record']);assert record['exit_code']==item['expected_exit'] and record['error'] is None
            assert record['resources']['cpu_seconds']>0 and record['resources']['tree_rss_status']=='sampled'
        if row['case']=='denied':
            assert row['revision_run'] is None and not (anchor/'revisions').exists()
            assert initial['budget']['spent']['tool_calls']==5 and initial['task']['limits']['max_tool_calls']==6
            continue
        target=rb/row['revision_run'];final=read_json(target/'report.json')
        assert final['state']=='PARTIAL' and final['budget']['spent']['audit_runs']==initial['budget']['spent']['audit_runs']==1
        assert relocate(read_json(anchor/'latest-revision.json')['path'])==target
        if row['case'] in ('failed','interrupted'):
            assert final['revision']['recovered_interruption'] and not final['claims'] and not final['coverage']['profiles']
            before=read_json(anchor.parent/'ledger-before-recovery.json');faults=read_json(anchor.parent/'controlled-fault.json')
            assert len(faults)==row['controlled_real_inspections']==1 and faults[0]['real_core'] and not faults[0]['production_incident']
            assert faults[0]['pending_entry']['status']=='pending' and faults[0]['pending_entry']['kind']=='resume_identity_check'
            assert before['entries'][-1]['status']==('pending' if row['case']=='interrupted' else 'unknown')
            entry=next(e for e in final['budget']['entries'] if e['kind']=='resume_identity_check')
            assert entry['status']=='unknown' and entry['actual']==entry['reservation']
            assert sum(e['kind']=='recovery_finalize' for e in final['budget']['entries'])==1
    final=directory/'runs/ci-finalization';fr=read_json(final/'receipt.json')
    assert fr['status']=='passed' and fr['code_digest']==code_digest()
    assert fr['model_calls']==fr['human_participants']==0 and len(fr['cases'])==len(fr['reports'])==6
    for item in fr['reports']:
        host=final/item['run'];assert file_hash(host/'report.json')==item['report_sha256'] and file_hash(host/'manifest.json')==item['manifest_sha256']
    for item in fr['cases']:
        case=read_json(final/item['receipt']);proc=read_json(final/item['process'])
        assert proc['exit_code']==0 and proc['error'] is None
        assert proc['resources']['cpu_seconds']>0 and proc['resources']['tree_rss_status']=='sampled'
    results.append({'platform':artifact['platform'],'tests':204,'skipped':0,'reports_reverified':checked,
                    'gate_cli_commands':9,'expected_rejections':3,'resource_measured_runs':18,'catalog_cli_commands':5,'catalog_scores_reverified':9,'lifecycle_reports':5,'controlled_negative_candidates':4,'static_report_links_and_thumbnails':'passed','plan_check_cases':4,'half_written_core_report':'passed','csv_export_rows':6,'interaction_scores':12,'interaction_D_blocked':12,'review_lifecycle_reports':4,'interaction_binding_rejections':6,'metadata_field_reports':metadata_field_reports,'rules_reports':rules_reports,'rules_cases':13,'rules_smoke_reports':14,'revision_budget_cases':4,'revision_budget_reports':7,'finalization_cases':6,'finalization_reports':6,
                    'runtime_lock_sha256':file_hash(directory/'core.runtime.lock.json')})
write_json(base/'verification.json',{'verified_at':now(),'status':'passed','tested_commit':run['headSha'],
    'ci_url':run['url'],'results':results,'model_calls':0,'method':__doc__},exclusive=True)
summary={'status':'passed','platforms':len(results),'tests_per_platform':results[0]['tests'],
         'reports_reverified':sum(len(r['reports_reverified']) for r in results),
         'real_agent_experiment':'not_run'}
for field in ('resource_measured_runs','catalog_scores_reverified','lifecycle_reports','plan_check_cases',
              'csv_export_rows','interaction_scores','review_lifecycle_reports','interaction_binding_rejections','metadata_field_reports','rules_reports','rules_cases','rules_smoke_reports','revision_budget_cases','revision_budget_reports','finalization_cases','finalization_reports'):
    summary[field]=sum(r[field] for r in results)
summary['half_written_core_reports']=sum(r['half_written_core_report']=='passed' for r in results)
print(json.dumps(summary))
