"""Frozen, deterministic clue routing. Text can suggest fixed checks, never grant authority."""
from __future__ import annotations
import re
from .common import PROJECT, digest, read_json
from .domain import validate

MAX_AUDITS = 3
NEGATION = re.compile(r'(?:\b(?:no|not|without|never|excluding)\s+(?:image\s+)?|(?:没有|不含|未|无|无需|不要)(?:进行|包含|发生|使用|检查|任何|的|过|了){0,3})$')


def load_policy() -> dict:
    policy = read_json(PROJECT/'configs/policy.json')
    validate(policy, 'rules-policy')
    return policy


def collect_hints(task: dict, contexts: list[dict], policy: dict) -> dict:
    """Called inside the charged context interpretation, using saved excerpts only."""
    sources = [{'source': 'request_text', 'text': task['request_text'], 'context_ref': None,
                'sha256': None, 'truncated': False}]
    skipped = []
    for context in contexts:
        if context['format'] not in ('.md', '.txt'):
            skipped.append({'context_ref': context['context_ref'], 'reason': 'not_markdown_or_txt'})
            continue
        sources.append({'source': 'registered_context', 'text': context['excerpt'],
                        'context_ref': context['context_ref'], 'sha256': context['sha256'],
                        'truncated': context['truncated']})
    inputs = []; active = set()
    for source in sources:
        text = source.pop('text')
        lower = text.lower(); positive = {}; negated = {}
        for family, terms in policy['hint_terms'].items():
            positive[family] = []; negated[family] = []
            for term in terms:
                word = term.lower(); expression = re.escape(word)
                if word.isascii(): expression = r'(?<![a-z0-9_])'+expression+r'(?![a-z0-9_])'
                matches = list(re.finditer(expression, lower))
                if any(not NEGATION.search(lower[max(0,m.start()-40):m.start()]) for m in matches):
                    positive[family].append(term); active.add(family)
                if any(NEGATION.search(lower[max(0,m.start()-40):m.start()]) for m in matches):
                    negated[family].append(term)
        inputs.append({**source, 'excerpt_digest': digest(text), 'characters': len(text),
                       'positive_terms': positive, 'negated_terms': negated})
    selected = 'all' if len(active)==2 else next(iter(active)) if active else None
    return {'selected_profile': selected, 'inputs': inputs, 'ignored_contexts': skipped,
            'method': 'Literal registered clues with limited local negation; not semantic understanding or proof of a transform.'}


def decide(task: dict, manifest: dict, info: dict, coverage: dict, ledger, policy: dict) -> dict:
    hints = info.get('routing_hints'); selected = hints['selected_profile'] if hints else None
    base = coverage['profiles'].get('base', {})
    remaining = {k: ledger.remaining(k) for k in ('tool_calls','audit_runs','comparisons','index_operations','decoded_pixels','wall_seconds')}
    reason = 'no_positive_clues'; decision = 'stop'
    if hints is None: decision, reason = 'unavailable', 'context_interpretation_incomplete'
    elif selected:
        decision, reason = 'run', 'positive_registered_clues'
        if not base.get('complete'): decision, reason = 'defer', 'base_incomplete'
        elif coverage['verification'].get(base['audit_id'], {}).get('state') != 'passed': decision, reason = 'defer', 'base_not_verified'
        elif ledger.data['spent']['audit_runs'] >= min(MAX_AUDITS,task['limits']['max_core_audit_runs']): decision, reason = 'defer', 'max_core_audit_runs'
        elif remaining['tool_calls'] <= task['limits']['finalization_reserve_tool_calls']: decision, reason = 'defer', 'finalization_tool_reserve'
        elif remaining['wall_seconds'] <= task['limits']['finalization_reserve_seconds']: decision, reason = 'defer', 'finalization_time_reserve'
        elif remaining['comparisons'] < 1: decision, reason = 'defer', 'comparison_budget'
        elif remaining['index_operations'] < 16: decision, reason = 'defer', 'index_budget'
        # A complete base measures source decoding. Hold a further full decode
        # for worst-case exact verification of the supplemental scan.
        elif remaining['decoded_pixels'] < 2*base['scope']['totalDecodedPixels']: decision, reason = 'defer', 'decode_and_verify_budget'
    return {'policy_version': policy['policy_version'], 'policy_digest': digest(policy),
            'initial_task_digest': digest(task), 'dataset_manifest_digest': manifest['digest'],
            'scope': 'Initial image-audit routing; goal-only revisions do not rerun rules or Core.',
            'decision': decision, 'reason_code': reason, 'selected_profile': selected,
            'hints': hints, 'remaining_before_decision': remaining,
            'base_complete': base.get('complete'), 'metadata_state': info['metadata']['state'],
            'requested_questions': [q['question_code'] for q in info['questions']],
            'outcome': 'not_run', 'model_calls': 0}
