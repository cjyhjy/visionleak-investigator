"""Accounting tests only; no provider calls or real Agent trajectories."""
import pytest

from visionleak_investigator.budget import BudgetExceeded
from visionleak_investigator.common import read_json
from visionleak_investigator.model_budget import ModelBudgetLedger


def ledger(tmp_path, **changes):
    limits = {'max_llm_requests': 3, 'max_llm_output_tokens': 100, 'remote_budget_usd': '0.3', **changes}
    return ModelBudgetLedger(tmp_path / 'model-ledger.json', binding='test-task-digest', limits=limits, execution_label='scripted_test_only')


def test_exact_decimal_budget_and_persisted_reservations(tmp_path):
    book = ledger(tmp_path)
    for _ in range(3):
        ref = book.reserve(cost_cap_usd='0.1')
        assert read_json(book.path)['entries'][-1]['status'] == 'pending'
        book.settle(ref, cost_usd='0.1', input_tokens=20, output_tokens=30)
    assert book.summary()['charged_cost_usd'] == '0.3'
    with pytest.raises(BudgetExceeded):
        ledger(tmp_path).reserve(cost_cap_usd='0')


def test_crash_recovery_charges_reservation_without_retry(tmp_path):
    book = ledger(tmp_path)
    book.reserve(cost_cap_usd='0.2')
    reloaded = ledger(tmp_path)
    with pytest.raises(BudgetExceeded, match='recovery'):
        reloaded.reserve(cost_cap_usd='0.1')
    reloaded.recover_pending()
    assert reloaded.summary()['unknown_requests'] == 1
    assert reloaded.summary()['charged_cost_usd'] == '0.2'
    with pytest.raises(BudgetExceeded):
        reloaded.reserve(cost_cap_usd='0.2')
    reloaded.recover_pending()
    assert reloaded.summary()['requests_reserved'] == 1


@pytest.mark.parametrize('usage', [dict(), dict(cost_usd='0'), dict(input_tokens=1, output_tokens=2)])
def test_missing_usage_is_never_zero_cost(tmp_path, usage):
    book = ledger(tmp_path)
    ref = book.reserve(cost_cap_usd='0.1')
    book.settle(ref, **usage)
    assert book.summary()['charged_cost_usd'] == '0.1'
    assert book.summary()['unknown_requests'] == 1
    with pytest.raises(ValueError):
        book.settle(ref, **usage)


@pytest.mark.parametrize('usage', [dict(cost_usd='NaN', input_tokens=1, output_tokens=1),
                                  dict(cost_usd='-1', input_tokens=1, output_tokens=1),
                                  dict(cost_usd='0.01', input_tokens=True, output_tokens=1)])
def test_invalid_usage_conservatively_settled_and_halts(tmp_path, usage):
    book = ledger(tmp_path)
    ref = book.reserve(cost_cap_usd='0.1')
    with pytest.raises(ValueError):
        book.settle(ref, **usage)
    assert book.summary()['charged_cost_usd'] == '0.1'
    assert book.summary()['halted']
    with pytest.raises(BudgetExceeded):
        book.reserve(cost_cap_usd='0.1')


@pytest.mark.parametrize('usage', [dict(cost_usd='0.2', input_tokens=1, output_tokens=10),
                                  dict(cost_usd='0.01', input_tokens=1, output_tokens=101)])
def test_provider_overrun_is_recorded_and_stops_future_requests(tmp_path, usage):
    book = ledger(tmp_path)
    ref = book.reserve(cost_cap_usd='0.1')
    book.settle(ref, **usage)
    assert book.summary()['halted']
    assert book.data['entries'][0]['overrun']


def test_resume_cannot_increase_limits_or_switch_binding(tmp_path):
    ledger(tmp_path)
    with pytest.raises(ValueError, match='changed'):
        ledger(tmp_path, remote_budget_usd=100)


def test_zero_budget_does_not_reserve_paid_request(tmp_path):
    book = ledger(tmp_path, remote_budget_usd=0)
    with pytest.raises(BudgetExceeded):
        book.reserve(cost_cap_usd='0.01')


def test_invalid_tokens_do_not_erase_a_reported_cost_overrun(tmp_path):
    book = ledger(tmp_path)
    ref = book.reserve(cost_cap_usd='0.1')
    with pytest.raises(ValueError):
        book.settle(ref, cost_usd='0.25', input_tokens=-1, output_tokens=1)
    assert book.summary()['charged_cost_usd'] == '0.25'
    assert book.summary()['halted']
