import pytest

from scripts.azure_api import Arm
from scripts.azure_idle_guard import reason


def cost_client(columns, rows, next_link=None):
    client = object.__new__(Arm)
    client.request = lambda *args, **kwargs: {'properties': {
        'columns': [{'name': name} for name in columns], 'rows': rows, 'nextLink': next_link}}
    return client


def test_cost_uses_usd_column_not_billing_currency():
    client = cost_client(['Cost', 'Currency', 'CostUSD'], [[136475, 'KRW', 100], [68237.5, 'KRW', 50]])
    assert client.cost_usd('subscription') == 150


@pytest.mark.parametrize('columns,next_link', [(['Cost'], None), (['CostUSD'], 'more')])
def test_incomplete_cost_cannot_admit_paid_compute(columns, next_link):
    with pytest.raises(RuntimeError, match='Incomplete'):
        cost_client(columns, [[0]], next_link).cost_usd('subscription')


def test_guard_boundaries_and_hard_cap_even_when_recently_busy():
    assert reason(28799, 1199) is None
    assert reason(100, 1200) == 'twenty_minutes_idle'
    assert reason(28800, 0) == 'eight_hour_cap'
