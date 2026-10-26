"""Durable model accounting, independent of provider and authorization.

This module does not authorize, discover credentials, or make network requests.
Provider adapters must check consent separately and enforce the reserved token cap.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from .budget import BudgetExceeded
from .common import read_json, write_json, now


def amount(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError('Invalid model cost')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid model cost') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Invalid model cost')
    return result


def token_count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError('Invalid model token usage')
    return value


class ModelBudgetLedger:
    """One serial request at a time, persisted before dispatch, no automatic retry.

    Costs are decimal strings. Unknown usage consumes the full reservation and is
    explicitly labelled unmeasured. A reported overrun is retained and halts work.
    A host-provided task binding prevents resetting or increasing budgets on resume.
    """

    def __init__(self, path: Path, *, binding: str, limits: dict, execution_label: str):
        if execution_label not in ('scripted_test_only', 'authorized_model'):
            raise ValueError('Execution provenance required; label alone is not consent')
        if not binding:
            raise ValueError('Task binding required')
        self.path = path
        fixed = {
            'max_requests': token_count(limits['max_llm_requests']),
            'max_output_tokens': token_count(limits['max_llm_output_tokens']),
            'budget_usd': str(amount(limits['remote_budget_usd'])),
        }
        if fixed['max_output_tokens'] == 0:
            raise ValueError('Positive output token cap required')
        if path.exists():
            self.data = read_json(path)
            if (self.data['binding'], self.data['limits'], self.data['execution_label']) != (binding, fixed, execution_label):
                raise ValueError('Model ledger binding, limits or provenance changed')
        else:
            self.data = {'schema_version': 1, 'binding': binding, 'limits': fixed,
                         'execution_label': execution_label, 'entries': [], 'halted': False}
            write_json(path, self.data, exclusive=True)

    def summary(self) -> dict:
        entries = self.data['entries']
        return {
            'execution_label': self.data['execution_label'],
            'requests_reserved': len(entries),
            'charged_cost_usd': str(sum((amount(e.get('charged_cost_usd', '0')) for e in entries), Decimal(0))),
            'unknown_requests': sum(e['status'] == 'unknown' for e in entries),
            'pending_requests': sum(e['status'] == 'pending' for e in entries),
            'halted': self.data['halted'],
        }

    def reserve(self, *, cost_cap_usd: str) -> str:
        if self.data['halted']:
            raise BudgetExceeded('Model usage overrun; further requests blocked')
        if any(e['status'] == 'pending' for e in self.data['entries']):
            raise BudgetExceeded('Pending model request; explicit recovery required')
        if len(self.data['entries']) >= self.data['limits']['max_requests']:
            raise BudgetExceeded('Model request budget exhausted')
        cap = amount(cost_cap_usd)
        if cap + amount(self.summary()['charged_cost_usd']) > amount(self.data['limits']['budget_usd']):
            raise BudgetExceeded('Model cost reservation exceeds remaining budget')
        ref = f'model-{len(self.data["entries"]) + 1:04d}'
        self.data['entries'].append({'request_id': ref, 'status': 'pending', 'reserved_at': now(),
                                     'cost_cap_usd': str(cap),
                                     'output_token_cap': self.data['limits']['max_output_tokens']})
        write_json(self.path, self.data)
        return ref

    def settle(self, ref: str, *, cost_usd: str | None = None, input_tokens: int | None = None,
               output_tokens: int | None = None, failure_code: str | None = None) -> None:
        entry = next((e for e in self.data['entries'] if e['request_id'] == ref), None)
        if entry is None or entry['status'] != 'pending':
            raise ValueError('Unknown or already settled model reservation')
        invalid = None
        known = cost_usd is not None and input_tokens is not None and output_tokens is not None
        cost = None
        try:
            cost = amount(cost_usd) if cost_usd is not None else None
            if input_tokens is not None:
                token_count(input_tokens)
            if output_tokens is not None:
                token_count(output_tokens)
        except ValueError as exc:
            invalid = exc
            known = False
        cap = amount(entry['cost_cap_usd'])
        # Missing token usage must not undercharge even when a cost was supplied.
        charge = cost if known else max(cap, cost or Decimal(0))
        overrun = charge > cap or (invalid is None and output_tokens is not None and output_tokens > entry['output_token_cap'])
        entry.update(status='settled' if known else 'unknown', settled_at=now(),
                     charged_cost_usd=str(charge),
                     measured_cost_usd=str(cost) if cost is not None else None,
                     input_tokens=input_tokens if invalid is None else None,
                     output_tokens=output_tokens if invalid is None else None,
                     accounting_basis='reported_usage' if known else 'conservative_reservation',
                     failure_code='invalid_usage' if invalid else failure_code, overrun=overrun)
        self.data['halted'] = self.data['halted'] or overrun or invalid is not None
        write_json(self.path, self.data)
        if invalid:
            raise invalid

    def recover_pending(self) -> None:
        for entry in self.data['entries']:
            if entry['status'] == 'pending':
                self.settle(entry['request_id'], failure_code='interrupted_no_automatic_replay')
