import os
import yaml
import json
import csv
import sys
import threading
import datetime
from typing import List, Dict, Any, Optional, Callable
from configuration_management.config_manager import ConfigManager
import importlib.resources
from scode.json_utils import json_default

class ConfigLoader:
    def __init__(self, config_path: str = None):
        self.config_path = config_path or 'configs/logging.yaml'
        self.config = self.load_config(self.config_path)

    def load_config(self, path: str) -> dict:
        fname = os.path.basename(path)
        try:
            with importlib.resources.open_text('configs', fname) as f:
                if fname.endswith('.yaml') or fname.endswith('.yml'):
                    return yaml.safe_load(f)
                elif fname.endswith('.json'):
                    return json.load(f)
        except (FileNotFoundError, ModuleNotFoundError):
            if path.endswith(".yaml") or path.endswith(".yml"):
                with open(path, "r") as f:
                    return yaml.safe_load(f)
            elif path.endswith(".json"):
                with open(path, "r") as f:
                    return json.load(f)
            else:
                raise ValueError("Unsupported config file format.")

    def get_setting(self, key: str, default=None):
        return self.config.get(key, default)

    def reload(self):
        self.config = self.load_config(self.config_path)

class LoggingResultsManager:
    def __init__(self, config_overrides: dict = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('logging_results')
        self.config = self._deep_merge(base_config, config_overrides or {})
        self.log_level = self.config.get('logging', {}).get('level', 'INFO')
        self.log_to_file = self.config.get('logging', {}).get('log_to_file', True)
        self.log_file_path = self.config.get('logging', {}).get('log_file_path', 'logs/app.log')
        self.log_to_stdout = self.config.get('logging', {}).get('log_to_stdout', True)
        self.log_rotation = self.config.get('logging', {}).get('rotation', None)
        self.log_max_bytes = self.config.get('logging', {}).get('max_bytes', 10 * 1024 * 1024)
        self.log_backup_count = self.config.get('logging', {}).get('backup_count', 5)
        self.structured_error_logging = self.config.get('logging', {}).get('structured_error_logging', True)
        self.results_dir = self.config.get('results', {}).get('storage_dir', 'results/')
        self.export_formats = self.config.get('results', {}).get('export_formats', ['json', 'csv', 'yaml'])
        self.result_versioning = self.config.get('results', {}).get('versioning', True)
        self.cloud_backend = self.config.get('results', {}).get('cloud_backend', None)
        self.db_backend = self.config.get('results', {}).get('db_backend', None)
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        self.metrics: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.results: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self.log_backends: List[Callable[[str], None]] = []
        self.result_backends: List[Callable[[str, dict], None]] = []

    def _deep_merge(self, base: dict, override: dict) -> dict:
        if not override:
            return base.copy()
        result = base.copy()
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    # --- Logging APIs ---
    def log_event(self, event: str, details: dict = None, level: str = 'INFO') -> None:
        timestamp = datetime.datetime.now().isoformat()
        log_entry = {
            'timestamp': timestamp,
            'level': level,
            'event': event,
            'details': details or {}
        }
        log_line = json.dumps(log_entry, default=json_default)
        if self.log_to_file:
            self._write_log_file(log_line)
        if self.log_to_stdout:
            print(log_line, file=sys.stdout)
        for backend in self.log_backends:
            backend(log_line)
        # Track run start/end
        if event == 'run_started':
            run_id = details.get('run_id')
            with self.lock:
                self.runs[run_id] = {'start_time': timestamp, 'status': 'running', 'events': [log_entry]}
        elif event == 'run_ended':
            run_id = details.get('run_id')
            with self.lock:
                if run_id in self.runs:
                    self.runs[run_id]['end_time'] = timestamp
                    self.runs[run_id]['status'] = 'completed'
                    self.runs[run_id]['events'].append(log_entry)
        elif 'run_id' in (details or {}):
            run_id = details['run_id']
            with self.lock:
                if run_id in self.runs:
                    self.runs[run_id]['events'].append(log_entry)

    def _write_log_file(self, log_line: str):
        # Advanced log rotation if enabled
        if self.log_rotation == 'size':
            if os.path.exists(self.log_file_path) and os.path.getsize(self.log_file_path) > self.log_max_bytes:
                for i in range(self.log_backup_count, 0, -1):
                    src = f"{self.log_file_path}.{i-1}" if i > 1 else self.log_file_path
                    dst = f"{self.log_file_path}.{i}"
                    if os.path.exists(src):
                        os.rename(src, dst)
                open(self.log_file_path, 'w').close()
        with open(self.log_file_path, 'a') as f:
            f.write(log_line + '\n')

    def log_error(self, error: Exception, context: dict = None, run_id: str = None):
        if self.structured_error_logging:
            self.log_event('error', {'error_type': type(error).__name__, 'message': str(error), 'context': context or {}, 'run_id': run_id}, level='ERROR')
        else:
            self.log_event('error', {'message': str(error), 'context': context or {}, 'run_id': run_id}, level='ERROR')

    def log_metric(self, metric_name: str, value: float, step: int = None, run_id: str = None) -> None:
        with self.lock:
            if run_id not in self.metrics:
                self.metrics[run_id] = {}
            if metric_name not in self.metrics[run_id]:
                self.metrics[run_id][metric_name] = []
            self.metrics[run_id][metric_name].append({'step': step, 'value': value, 'timestamp': datetime.datetime.now().isoformat()})

    def get_metrics(self, run_id: str, metric_name: str = None) -> dict:
        with self.lock:
            if run_id not in self.metrics:
                return {}
            if metric_name:
                return {metric_name: self.metrics[run_id].get(metric_name, [])}
            return self.metrics[run_id]

    def list_runs(self) -> List[str]:
        with self.lock:
            return list(self.runs.keys())

    def get_run_summary(self, run_id: str) -> dict:
        with self.lock:
            run = self.runs.get(run_id, {})
            summary = {
                'run_id': run_id,
                'start_time': run.get('start_time'),
                'end_time': run.get('end_time'),
                'status': run.get('status', 'unknown'),
                'key_metrics': {k: v[-1]['value'] if v else None for k, v in self.metrics.get(run_id, {}).items()},
            }
            return summary

    # --- Results APIs ---
    def store_result(self, run_id: str, result: dict) -> None:
        with self.lock:
            self.results[run_id] = result
        for backend in self.result_backends:
            backend(run_id, result)
        # Optionally persist to disk with versioning
        version = 1
        result_path = os.path.join(self.results_dir, f'{run_id}.json')
        if self.result_versioning:
            while os.path.exists(result_path):
                version += 1
                result_path = os.path.join(self.results_dir, f'{run_id}_v{version}.json')
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2)
        # Optionally send to cloud/db backend (placeholders)
        if self.cloud_backend:
            self._send_to_cloud(run_id, result)
        if self.db_backend:
            self._send_to_db(run_id, result)

    def _send_to_cloud(self, run_id: str, result: dict):
        # Placeholder for cloud backend integration
        pass

    def _send_to_db(self, run_id: str, result: dict):
        # Placeholder for DB backend integration
        pass

    def get_result(self, run_id: str) -> dict:
        with self.lock:
            if run_id in self.results:
                return self.results[run_id]
        # Try loading from disk
        result_path = os.path.join(self.results_dir, f'{run_id}.json')
        if os.path.exists(result_path):
            with open(result_path, 'r') as f:
                return json.load(f)
        # Try versioned results
        version = 1
        while True:
            versioned_path = os.path.join(self.results_dir, f'{run_id}_v{version}.json')
            if os.path.exists(versioned_path):
                with open(versioned_path, 'r') as f:
                    return json.load(f)
                version += 1
            else:
                break
        return {}

    def export_log(self, run_id: str, format: str, path: str) -> None:
        with self.lock:
            run = self.runs.get(run_id, {})
            metrics = self.metrics.get(run_id, {})
            result = self.get_result(run_id)
            events = run.get('events', [])
        if format == 'json':
            with open(path, 'w') as f:
                json.dump({'events': events, 'metrics': metrics, 'result': result}, f, indent=2, default=json_default)
        elif format in ('yaml', 'yml'):
            with open(path, 'w') as f:
                yaml.safe_dump({'events': events, 'metrics': metrics, 'result': result}, f)
        elif format == 'csv':
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['metric', 'step', 'value', 'timestamp'])
                for metric, vals in metrics.items():
                    for v in vals:
                        writer.writerow([metric, v.get('step'), v.get('value'), v.get('timestamp')])
        else:
            raise ValueError(f"Unsupported export format: {format}")

    # --- Extensibility ---
    def register_log_backend(self, backend: Callable[[str], None]):
        self.log_backends.append(backend)

    def register_result_backend(self, backend: Callable[[str, dict], None]):
        self.result_backends.append(backend)

    def reload_config(self, config_overrides: dict = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('logging_results')
        self.config = self._deep_merge(base_config, config_overrides or {})
        self.log_level = self.config.get('logging', {}).get('level', 'INFO')
        self.log_to_file = self.config.get('logging', {}).get('log_to_file', True)
        self.log_file_path = self.config.get('logging', {}).get('log_file_path', 'logs/app.log')
        self.log_to_stdout = self.config.get('logging', {}).get('log_to_stdout', True)
        self.log_rotation = self.config.get('logging', {}).get('rotation', None)
        self.log_max_bytes = self.config.get('logging', {}).get('max_bytes', 10 * 1024 * 1024)
        self.log_backup_count = self.config.get('logging', {}).get('backup_count', 5)
        self.structured_error_logging = self.config.get('logging', {}).get('structured_error_logging', True)
        self.results_dir = self.config.get('results', {}).get('storage_dir', 'results/')
        self.export_formats = self.config.get('results', {}).get('export_formats', ['json', 'csv', 'yaml'])
        self.result_versioning = self.config.get('results', {}).get('versioning', True)
        self.cloud_backend = self.config.get('results', {}).get('cloud_backend', None)
        self.db_backend = self.config.get('results', {}).get('db_backend', None)
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True) 