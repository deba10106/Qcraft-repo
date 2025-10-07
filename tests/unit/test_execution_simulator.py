import json
import os

from execution_simulation.execution_simulator import ExecutionSimulatorAPI
from configuration_management.config_manager import ConfigManager


def test_list_backends_returns_list():
    api = ExecutionSimulatorAPI()
    backends = api.list_backends()
    assert isinstance(backends, list)


def test_get_supported_simulation_options_keys():
    ConfigManager.load_registry()
    hw = ConfigManager.load_hardware_json()
    device = hw['device_name']
    api = ExecutionSimulatorAPI()
    opts = api.get_supported_simulation_options(device)
    for key in ['noise_model','max_shots','native_gates','max_qubits','gate_error_rates','readout_errors']:
        assert key in opts


def test_export_result_json_yaml_csv(tmp_path):
    api = ExecutionSimulatorAPI()
    job_id = 'job-xyz'
    # Inject a fake result
    api.simulator.job_results[job_id] = {'backend': 'local', 'counts': {'00': 512, '11': 512}}

    json_path = tmp_path / 'res.json'
    yaml_path = tmp_path / 'res.yaml'
    csv_path = tmp_path / 'res.csv'

    api.export_result(job_id, 'json', str(json_path))
    api.export_result(job_id, 'yaml', str(yaml_path))
    api.export_result(job_id, 'csv', str(csv_path))

    assert json_path.exists() and yaml_path.exists() and csv_path.exists()
    with open(json_path, 'r') as f:
        data = json.load(f)
    assert data.get('backend') == 'local'
    with open(csv_path, 'r') as f:
        content = f.read()
    assert 'bitstring,count' in content and '00,512' in content
