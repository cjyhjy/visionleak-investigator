from __future__ import annotations
import html, json
from .common import PROJECT,read_json,digest,write_json
from .domain import validate
RULES=read_json(PROJECT/'contracts/claim-rules.json')['rules']
LIMITATIONS=['相似候选不证明同源或实验泄漏。','图像关系不证明模型实际训练使用。','覆盖仅适用于列明的 profile、输入与阈值。','本次未调用模型；不是 Agent 性能实验。']
class ClaimValidator:
    def build(self,kind: str,records: list[dict],coverage_ref: str,goal_ref: str|None=None,*,supported: bool=True) -> dict:
        rule=RULES[kind];allowed=list(rule['evidence']);status=rule['status']
        if kind=='goal_conflict':allowed.append('metadata.entity_overlap')
        if not records or any(r['kind'] not in allowed for r in records):raise ValueError('Evidence kind does not entail claim')
        if kind in ('declared_entity_overlap','goal_conflict'):
            goals=[r for r in records if r['kind']=='user.goal_confirmation']
            groups=[r for r in records if r['kind']=='metadata.entity_overlap']
            if len(goals)!=1 or not groups or goals[0]['evidence_id']!=goal_ref:raise ValueError('Missing confirmed goal and metadata relationship')
            if kind=='goal_conflict' and goals[0]['facts']['goal']!='new_entity_generalization':raise ValueError('Goal does not prohibit entity overlap')
            for group in groups:
                f=group['facts'];members=f['members']
                if not f['entity_key_confirmed'] or not f['entity_id'] or any(m['entity_id']!=f['entity_id'] for m in members) or len({m['image_split'] for m in members})<2 or not f['metadata_sha256']:raise ValueError('Metadata facts do not support overlap')
        if kind=='same_source_review':
            for r in records:
                f=r['facts']
                if not f['reviewer'] or f['decision']!='confirmed' or f['dataset_manifest_digest']!=r['dataset_manifest_digest'] or not f['pair_ref'] or not r['core_audit_id']:raise ValueError('Review not bound to input/pair/reviewer')
        for r in records:
            if r['kind'].startswith('core.'):
                v=r['verification_state']
                if v['report_identity']!='valid':raise ValueError('Report identity invalid')
                if kind in ('byte_identity','pixel_identity'):
                    field='byteDigest' if kind=='byte_identity' else 'pixelDigest'
                    a,b=r['images'];matched=a.get(field) and a[field]==b.get(field)
                    if kind=='pixel_identity':matched=matched and all(i.get('pixelDigestBasis')=='full' for i in (a,b))
                    if not matched:raise ValueError('Digest does not support claim')
                    if v['exact_recomputed']!='valid':supported=False
        if not supported:status='inconclusive'
        statement=rule['template'] if supported else '已有关系记录尚未满足复验或确认前提，无法确认该结论。'
        c={'claim_id':digest([kind,[r['evidence_id'] for r in records],coverage_ref]),'claim_type':kind,'statement':statement,'evidence_refs':[r['evidence_id'] for r in records],'goal_ref':goal_ref,'coverage_ref':coverage_ref,'status':status,'limitations':LIMITATIONS[:],'rule_version':'vli-claims-1'}
        validate(c,'claim');return c
    def validate_claim(self,claim: dict,registry: dict,coverage: dict) -> None:
        validate(claim,'claim')
        if any(r not in registry for r in claim['evidence_refs']):raise ValueError('Unknown evidence reference')
        if claim['coverage_ref'] not in coverage:raise ValueError('Unknown coverage reference')
        expected=self.build(claim['claim_type'],[registry[r] for r in claim['evidence_refs']],claim['coverage_ref'],claim['goal_ref'],supported=claim['status']!='inconclusive')
        if claim!=expected:raise ValueError('Unsupported claim or non-template assertion')

def render_report(report: dict, evidence: list[dict] | None = None) -> str:
    from .presentation import render
    return render(report,evidence or [])
