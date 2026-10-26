"""Provider-neutral, serial Planner loop. No credentials or network client.

Only a deliberately labelled local-test entry point is currently wired into the
host. Real providers require a separate consent-checked adapter before exposure.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from .common import append_json, canonical, digest, now
from .model_budget import ModelBudgetLedger
from .planning import StructuredPlanner


@dataclass(frozen=True)
class PlannerReply:
    text: str
    cost_usd: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class PlannerCallFailed(RuntimeError):
    """Transport/accounting failure: never trigger structural correction retries."""


class AccountedRequest:
    def __init__(self, request: Callable[[dict], PlannerReply], ledger: ModelBudgetLedger,
                 out: Path, *, cost_cap_usd: str):
        self.request, self.ledger, self.out = request, ledger, out
        self.cost_cap_usd = cost_cap_usd

    def __call__(self, payload: dict) -> str:
        # Transport/test callbacks never receive references to mutable host state.
        payload = json.loads(canonical(payload))
        ref = self.ledger.reserve(cost_cap_usd=self.cost_cap_usd)
        payload = {**payload, 'max_output_tokens': self.ledger.data['limits']['max_output_tokens']}
        append_json(self.out / 'planner-requests.jsonl', {
            'request_id': ref, 'state': 'reserved', 'time': now(), 'payload': payload,
            'execution_label': self.ledger.data['execution_label'],
        })
        try:
            reply = self.request(payload)
            if not isinstance(reply, PlannerReply):
                raise TypeError('Provider response must be a PlannerReply')
            self.ledger.settle(ref, cost_usd=reply.cost_usd, input_tokens=reply.input_tokens,
                               output_tokens=reply.output_tokens)
            if self.ledger.data['halted']:
                raise PlannerCallFailed('Model accounting halted after reported overrun')
            if not isinstance(reply.text, str):
                raise TypeError('Planner response must be text')
            append_json(self.out / 'planner-requests.jsonl', {
                'request_id': ref, 'state': 'returned', 'time': now(),
                'response_text': reply.text if len(reply.text.encode()) <= 16384 else None,
                'response_digest': digest(reply.text), 'response_bytes': len(reply.text.encode()),
            })
            return reply.text
        except Exception as exc:
            if any(e['request_id'] == ref and e['status'] == 'pending' for e in self.ledger.data['entries']):
                self.ledger.settle(ref, failure_code=type(exc).__name__)
            append_json(self.out / 'planner-requests.jsonl', {
                'request_id': ref, 'state': 'failed', 'time': now(), 'error_type': type(exc).__name__,
            })
            raise PlannerCallFailed('Planner request failed; cost retained; no automatic retry') from exc


def run_planner_loop(*, planner: StructuredPlanner, observe: Callable[[], dict],
                     dispatch: Callable[[dict], dict], out: Path, max_steps: int) -> dict:
    """Trace decisions before execution; every stop goes through host finalization."""
    for step in range(1, max_steps + 1):
        try:
            current = observe()
            action = planner.next_action(current)
            append_json(out / 'planner-actions.jsonl', {
                'step': step, 'state': 'pending', 'time': now(), 'action': action,
                'observation_digest': digest(current), 'execution_label': planner.execution_label,
            })
            result = dispatch(action)
            append_json(out / 'planner-actions.jsonl', {
                'step': step, 'state': 'executed', 'time': now(), 'action_type': action['action_type'],
                'result': result,
            })
            if action['action_type'] == 'finalize':
                return {'reason_code': action['parameters']['reason_code'], 'steps': step}
            if result.get('state') == 'WAITING_USER':
                return {'reason_code': 'waiting_user', 'steps': step}
        except Exception as exc:
            append_json(out / 'planner-actions.jsonl', {
                'step': step, 'state': 'stopped', 'time': now(), 'error_type': type(exc).__name__,
                'reason': str(exc), 'execution_label': planner.execution_label,
            })
            return {'reason_code': 'guardrail_stop', 'steps': step, 'error': str(exc)}
    return {'reason_code': 'budget_exhausted', 'steps': max_steps}
