from scripts.gemma_latency_check import percentile, summarize


def test_summarize_counts_status_retries_and_keys():
    rows = [dict(wall_s=1., status=200, key_indexes=[2], retry_metrics=dict(retry_count=0, first_failure_count=0)),
            dict(wall_s=3., status=200, key_indexes=[1, 3], retry_metrics=dict(retry_count=1, first_failure_count=1)),
            dict(wall_s=9., status=503, key_indexes=[1])]
    s = summarize(rows)
    assert s['status'] == {'200': 2, '503': 1}
    assert (s['retried'], s['first_failure'], s['keys_used']) == (1, 1, [1, 2, 3])
    assert s['wall_median_s'] == 3. and s['wall_p90_s'] == 9.
    assert percentile([], .9) is None
