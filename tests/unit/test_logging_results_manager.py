import json
import os

from logging_results.logging_results_manager import LoggingResultsManager


def test_log_event_metric_and_run_summary(tmp_path, monkeypatch):
    mgr = LoggingResultsManager(config_overrides={
        'logging': {
            'log_to_file': True,
            'log_to_stdout': False,
            'log_file_path': str(tmp_path / 'app.log'),
        },
        'results': {
            'storage_dir': str(tmp_path / 'results')
        }
    })

    run_id = 'run-1'
    mgr.log_event('run_started', {'run_id': run_id})
    mgr.log_metric('acc', 0.5, step=1, run_id=run_id)
    mgr.log_event('run_ended', {'run_id': run_id})

    metrics = mgr.get_metrics(run_id)
    assert 'acc' in metrics and metrics['acc'][-1]['value'] == 0.5
    runs = mgr.list_runs()
    assert run_id in runs
    summary = mgr.get_run_summary(run_id)
    assert summary['status'] in ('running', 'completed')
    assert 'acc' in summary['key_metrics']


def test_store_and_get_result_roundtrip(tmp_path):
    mgr = LoggingResultsManager(config_overrides={
        'logging': {
            'log_to_file': False,
            'log_to_stdout': False,
            'log_file_path': str(tmp_path / 'app.log'),
        },
        'results': {
            'storage_dir': str(tmp_path / 'results')
        }
    })
    run_id = 'abc123'
    res = {'ok': True, 'value': 42}
    mgr.store_result(run_id, res)
    loaded = mgr.get_result(run_id)
    assert loaded == res

    files = [p for p in (tmp_path / 'results').glob(f'{run_id}*.json')]
    assert files
