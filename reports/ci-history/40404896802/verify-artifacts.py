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
assert run['conclusion']=='success' and run['headSha']=='aff5ea6abaf08d138e168954e87d684bb60947bc'
download=read_json(base/'download.json');results=[]
adapter=CoreAdapter();adapter.verify_artifacts()
for artifact in download['artifacts']:
    directory=base/artifact['platform']
    for entry in artifact['files']:assert file_hash(directory/entry['path'])==entry['sha256']
    suite=ET.parse(directory/'reports/ci/junit.xml').find('testsuite')
    assert {k:suite.attrib[k] for k in ('tests','failures','errors','skipped')}==dict(tests='134',failures='0',errors='0',skipped='0')
    commands=read_json(directory/'commands.json')
    assert len(commands)==12 and all(c['exit_code']==0 for c in commands)
    original=Path(commands[0]['cwd'])
    def relocate(value):return directory/Path(value).relative_to(original)
    checked=[]
    for path in sorted((directory/'runs').rglob('report.json')):
        audit=path.parent
        if not (audit/'validation.json').exists():continue
        report=read_json(path);validation=read_json(audit/'validation.json');manifest=read_json(audit/'manifest.json')
        checkpoint=read_json(audit/'checkpoint.json')
        assert checkpoint['report_digest']==digest(report) and checkpoint['manifest_digest']==digest(manifest)
        assert read_json(audit/'ledger.json')==report['budget']
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
        dataset=relocate(registry['datasets'][report['task']['dataset_ref']])
        assert input_manifest(dataset,report['task']['limits'])['digest']==manifest['dataset_manifest_digest']
        if 'model_ledger_sha256' in validation:assert validation['model_ledger_sha256']==file_hash(audit/'model-ledger.json')
        assert report['model_execution']=='not_run' and report['coverage']['source_unchanged']
        evidence={r['evidence_id']:r for r in map(json.loads,(audit/'evidence.jsonl').read_text().splitlines())}
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
    assert len(checked)==33 and sum(r['mode']=='scripted_test_only' for r in checked)==2
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
    results.append({'platform':artifact['platform'],'tests':134,'skipped':0,'reports_reverified':checked,
                    'gate_cli_commands':9,'expected_rejections':3,'resource_measured_runs':18,'catalog_cli_commands':5,'catalog_scores_reverified':9,'lifecycle_reports':5,'controlled_negative_candidates':4,'static_report_links_and_thumbnails':'passed','plan_check_cases':4,'half_written_core_report':'passed',
                    'runtime_lock_sha256':file_hash(directory/'core.runtime.lock.json')})
write_json(base/'verification.json',{'verified_at':now(),'status':'passed','tested_commit':run['headSha'],
    'ci_url':run['url'],'results':results,'model_calls':0,'method':__doc__},exclusive=True)
print(json.dumps({'status':'passed','platforms':2,'tests_per_platform':134,'reports_reverified':66,
                  'resource_measured_runs':36,'catalog_scores_reverified':18,'lifecycle_reports':10,'plan_check_cases':8,'half_written_core_reports':2,'real_agent_experiment':'not_run'}))
