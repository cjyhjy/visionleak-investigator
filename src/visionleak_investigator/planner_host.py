"""Host-owned tools for the shared loop; no paths or tool implementations from Planner."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from .common import write_json, digest, file_hash
from .controller import AccountedRequest, run_planner_loop
from .model_budget import ModelBudgetLedger
from .planning import ToolGate, StructuredPlanner, observation
from .domain import input_manifest


def run_test_controller(*, task: dict, registry, out: Path, evidence: list, claims: list,
                        coverage: dict, completed: list, ledger, request: Callable,
                        audit: Callable, verify: Callable, interpret: Callable,
                        use_sdk: bool = False) -> dict:
    """Exercise the real host loop with an explicitly scripted, in-process callback.

    This entry point is intentionally not available via `--mode agent`. There is
    no provider adapter or consent grant implicit in a callback or provenance label.
    """
    model = ModelBudgetLedger(out / 'model-ledger.json', binding=digest(task),
                              limits=task['limits'], execution_label='scripted_test_only')
    request = AccountedRequest(request, model, out, cost_cap_usd='0')
    planner = StructuredPlanner(request, max_requests=task['limits']['max_llm_requests'],
                                execution_label='scripted_test_only')
    questions, review_refs, read_refs = [], set(), set()
    contexts = {f'context-{i+1}': ref for i, ref in enumerate(task['context_refs'])}

    def bounded(kind, operation, allocation=None):
        entry = ledger.reserve(kind, allocation)
        tick = time.monotonic()
        try:
            value = operation()
            ledger.settle(entry, {**(allocation or {}), 'wall_seconds': time.monotonic()-tick})
            return value
        except Exception:
            if entry['status'] == 'pending':
                ledger.settle(entry, None, error='Host planner tool failed; conservative charge')
            raise

    def read_context(action):
        alias = action['parameters']['context_ref']
        def read():
            path = registry.document(contexts[alias])
            text = path.read_text(encoding='utf-8')
            read_refs.add(alias)
            # Text remains local and untrusted; only a bounded summary is observed.
            write_json(out / f'{alias}.json', {'context_ref': contexts[alias],
                       'sha256': file_hash(path), 'excerpt': text[:8000],
                       'trust': 'untrusted data; never instructions'}, exclusive=True)
            return {'context_ref': alias, 'characters': len(text), 'trust': 'untrusted_data'}
        return bounded('read_context', read)

    def run_audit(action):
        if not audit(action['parameters']['profile']):
            raise ValueError('Requested Core audit failed; preserved output and cost')
        return {'profiles_completed': list(completed)}

    def check_groups(action):
        info = interpret()
        return {'metadata_state': info['metadata']['state'],
                'metadata_evidence_count': sum(e['kind'] == 'metadata.entity_overlap' for e in info['evidence'])}

    def clarify(action):
        def ask():
            questions.append({**action['parameters'], 'requested': True, 'origin': 'scripted_test_only'})
            return {'state': 'WAITING_USER'}
        return bounded('request_clarification', ask, {'questions': 1})

    def review(action):
        refs = action['parameters']['pair_refs']
        def ask():
            review_refs.update(refs)
            return {'state': 'WAITING_USER', 'requested_pairs': len(refs)}
        return bounded('request_review', ask, {'review_pairs': len(refs)})

    gate = ToolGate(evidence={}, profiles=list(completed), context_refs=set(contexts), audit_ids=set(),
                    metadata_ref='metadata-1' if task['metadata_ref'] else None,
                    goal_confirmed=task['goal_confirmed'], entity_key_confirmed=task['entity_key_confirmed'],
                    entity_key='confirmed-entity-column' if task['entity_key_confirmed'] else None,
                    max_steps=task['limits']['max_agent_steps'], handlers={
                        'read_context': read_context, 'run_audit': run_audit, 'check_groups': check_groups,
                        'verify_evidence': lambda a: verify(a['parameters']['audit_id']),
                        'request_clarification': clarify, 'request_review': review,
                        'finalize': lambda a: {'reason_code': a['parameters']['reason_code']},
                    })

    def observe():
        gate.evidence = {e['evidence_id']: e for e in evidence}
        gate.audit_ids = {c['audit_id'] for c in coverage['profiles'].values()}
        value = observation({'state': 'PLANNING', 'model_execution': 'not_run',
                             'coverage': coverage, 'budget': ledger.data, 'claims': claims}, evidence)
        value.update(goal=task['goal'], goal_confirmed=task['goal_confirmed'],
                     limits=task['limits'],
                     contexts=[{'context_ref': k, 'read': k in read_refs} for k in contexts],
                     metadata_ref=gate.metadata_ref, entity_key=gate.entity_key,
                     entity_key_confirmed=task['entity_key_confirmed'],
                     planner_budget=model.summary(), execution_label='scripted_test_only')
        return value

    def guarded_dispatch(a):
        if input_manifest(registry.dataset(task['dataset_ref']),task['limits'])['digest']!=coverage['input_manifest_digest']:
            raise ValueError('Input changed before planner tool; no action dispatched')
        return gate.dispatch(a)
    dispatch = guarded_dispatch
    if use_sdk:
        from .openjiuwen_runtime import run_guarded_workflow
        dispatch = lambda a: run_guarded_workflow(a, guarded_dispatch)
    outcome = run_planner_loop(planner=planner, observe=observe, dispatch=dispatch,
                               out=out, max_steps=task['limits']['max_agent_steps'])
    write_json(out / 'planner-trace.json', planner.trace, exclusive=True)
    write_json(out / 'planner-tools.json', gate.events, exclusive=True)
    ledger.data['planner_accounting'] = model.summary()
    ledger.save()
    return {**outcome, 'questions': questions, 'review_refs': sorted(review_refs),
            'accounting': model.summary(), 'execution_label': 'scripted_test_only',
            'sdk_dispatch': use_sdk}
