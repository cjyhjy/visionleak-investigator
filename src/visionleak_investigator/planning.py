"""Framework-independent structured planning boundary; no outbound client here."""
from __future__ import annotations
import json
from typing import Callable
from .common import digest
from .domain import AgentAction
from .workflow import ActionGuard

class ToolGate:
    """The sole SDK callback dispatcher. Handlers are registered by the host, never the planner."""
    def __init__(self,*,evidence: dict,profiles: list,context_refs: set,audit_ids: set,metadata_ref: str|None,goal_confirmed: bool,entity_key_confirmed: bool,entity_key: str|None,max_steps: int,handlers: dict[str,Callable]):
        self.evidence=evidence;self.profiles=profiles;self.context_refs=context_refs;self.audit_ids=audit_ids;self.metadata_ref=metadata_ref;self.goal_confirmed=goal_confirmed;self.entity_key_confirmed=entity_key_confirmed;self.entity_key=entity_key;self.max_steps=max_steps;self.handlers=handlers;self.steps=0;self.seen=set();self.events=[]
    def dispatch(self,value: dict) -> dict:
        self.steps+=1
        try:
            if self.steps>self.max_steps:raise ValueError('Action step budget exhausted')
            a=ActionGuard(set(self.evidence),self.profiles).check(value);kind=a['action_type'];p=a['parameters'];key=digest([kind,p])
            if key in self.seen:raise ValueError('Repeated action rejected')
            if kind not in self.handlers:raise ValueError('Tool not registered')
            if kind=='read_context' and p['context_ref'] not in self.context_refs:raise ValueError('Unregistered context')
            if kind=='verify_evidence' and p['audit_id'] not in self.audit_ids:raise ValueError('Unknown audit ID')
            if kind=='check_groups' and (not self.goal_confirmed or not self.entity_key_confirmed or p['metadata_ref']!=self.metadata_ref or p['entity_key']!=self.entity_key):raise ValueError('Unconfirmed group semantics')
            if kind=='request_review' and any(r not in self.evidence or 'candidate' not in self.evidence[r]['kind'] for r in p['pair_refs']):raise ValueError('Invalid review candidates')
            self.seen.add(key)
            result=self.handlers[kind](a)
            if kind=='run_audit':self.profiles.append(p['profile'])
            self.events.append({'action':a,'status':'executed'});return result
        except Exception as e:
            self.events.append({'action':value,'status':'rejected','reason':str(e)});raise

class StructuredPlanner:
    def __init__(self,request: Callable[[dict],str],*,max_requests: int,execution_label: str):
        if execution_label not in ('scripted_test_only','authorized_model'):raise ValueError('Execution provenance required')
        self.request=request;self.max_requests=max_requests;self.execution_label=execution_label;self.requests=0;self.trace=[]
    def next_action(self,observation: dict) -> dict:
        for attempt in range(2):
            if self.requests>=self.max_requests:raise ValueError('Planner request budget exhausted')
            self.requests+=1
            # Dispatch/accounting errors are not malformed model output.
            text=self.request({'observation':observation,'correction_requested':attempt==1})
            try:
                if not isinstance(text,str) or len(text.encode())>16384:raise ValueError('Planner output exceeds structural byte limit (not a token estimate)')
                def unique(rows):
                    d={}
                    for k,v in rows:
                        if k in d:raise ValueError('Duplicate JSON key')
                        d[k]=v
                    return d
                value=json.loads(text,object_pairs_hook=unique);AgentAction.parse(value)
                self.trace.append({'request':self.requests,'status':'accepted','action':value,'execution_label':self.execution_label});return value
            except (ValueError,TypeError) as e:
                self.trace.append({'request':self.requests,'status':'rejected','reason':str(e),'execution_label':self.execution_label})
        raise ValueError('Planner failed bounded correction; guardrail stop')

def observation(report: dict,evidence: list[dict]) -> dict:
    return {'state':report['state'],'model_execution':report['model_execution'],'evidence':[{'evidence_id':e['evidence_id'],'kind':e['kind']} for e in evidence[:128]],'evidence_total':len(evidence),'evidence_truncated':len(evidence)>128,'budget_spent':report['budget']['spent'],'profiles':{k:{'complete':v['complete'],'processed_images':v['processed_images'],'audit_id':v.get('audit_id')} for k,v in report['coverage']['profiles'].items()},'claim_counts':{s:sum(c['status']==s for c in report['claims']) for s in ('confirmed','candidate','inconclusive')}}
