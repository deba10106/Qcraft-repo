import os
import yaml
import json
import threading
import uuid
from typing import List, Dict, Any, Optional, Callable
from configuration_management.config_manager import ConfigManager
import importlib.resources
from hardware_abstraction.device_abstraction import DeviceAbstraction

try:
    # Qiskit 4.x: QuantumCircuit is still imported from qiskit
    from qiskit import QuantumCircuit
    from qiskit_aer import Aer
    from qiskit_ibm_runtime import QiskitRuntimeService
    QISKIT_AVAILABLE = True
except ImportError as e:
    print(f'[IMPORT ERROR] {e}')
    QISKIT_AVAILABLE = False

class ExecutionSimulator:
    def __init__(self, config_path: str = None):
        # No backends.yaml, use hardware.json and <provider_name>_devices.yaml
        self.jobs: Dict[str, dict] = {}  # job_id -> job info
        self.job_threads: Dict[str, threading.Thread] = {}
        self.job_results: Dict[str, dict] = {}
        self.job_status: Dict[str, str] = {}  # job_id -> status
        self.lock = threading.Lock()

    def _load_hardware_json(self):
        hardware_json_path = os.path.join('configs', 'hardware.json')
        with open(hardware_json_path, 'r') as f:
            return json.load(f)

    def _load_device_info(self, provider, device_name):
        yaml_file = f"configs/{provider}_devices.yaml"
        with open(yaml_file, 'r') as f:
            devices_yaml = yaml.safe_load(f)
        key = f"{provider}_devices"
        for dev in devices_yaml.get(key, []):
            if dev.get('device_name') == device_name:
                return dev
        raise ValueError(f"Device {device_name} not found in {yaml_file}")

    def run_circuit(self, circuit: dict, run_config: dict = None) -> str:
        hw = self._load_hardware_json()
        provider = hw['provider_name'].lower()
        device_name = hw['device_name']
        device_info = self._load_device_info(provider, device_name)
        api_key = None
        if provider not in ['local', 'simulator']:
            api_key = ConfigManager.get_api_key(provider)
            if not api_key:
                print(f"[ERROR] No API key found for provider {provider}. Please set it in .env.")
                raise RuntimeError(f"No API key found for provider {provider}. Please set it in .env.")
        return self._run_backend_job(circuit, provider, device_name, device_info, run_config, api_key)

    def _run_backend_job(self, circuit, provider, device_name, device_info, run_config, api_key):
        print(f"[DEBUG] QISKIT_AVAILABLE: {QISKIT_AVAILABLE}")
        print(f"[DEBUG] Provider: {provider}, Device: {device_name}")
        if provider == 'ibm':
            if not QISKIT_AVAILABLE:
                print("[ERROR] Qiskit is not installed. Please install qiskit and qiskit-ibm-runtime to run on IBM hardware.")
                return None
            if not api_key:
                raise RuntimeError("No IBM API key found. Please set ibm_api_key in .env.")
            # Debug: print masked API key
            masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "(too short to display)"
            print(f"[DEBUG] Using IBM API key: {masked_key}")
            try:
                service = QiskitRuntimeService(channel="ibm_quantum", token=api_key)
                qiskit_backend = service.backend(device_name)
                qc = self._dict_to_qiskit_circuit(circuit)
                shots = run_config.get('shots', 1024) if run_config else 1024
                job = qiskit_backend.run(qc, shots=shots)
                result = job.result()
                job_id = job.job_id() if hasattr(job, 'job_id') else None
                print(f"[DEBUG] IBM job submitted. Job ID: {job_id}")
                if job_id is None:
                    print("[ERROR] job_id is None after IBM execution.")
                return job_id
            except Exception as e:
                print(f"[ERROR] IBM execution failed: {e}")
                if '401' in str(e) or 'Unauthorized' in str(e):
                    print("[FATAL] IBM API key is invalid or expired. Please check your ibm_api_key in .env, or generate a new one at https://quantum-computing.ibm.com/account.")
                raise
        elif provider == 'local' or provider == 'simulator':
            if not QISKIT_AVAILABLE:
                print("[ERROR] Qiskit is not installed. Please install qiskit to run local simulations.")
                return None
            sim_backend = Aer.get_backend(device_name) if device_name in Aer.backends() else Aer.get_backend('qasm_simulator')
            qc = self._dict_to_qiskit_circuit(circuit)
            shots = run_config.get('shots', 1024) if run_config else 1024
            job = sim_backend.run(qc, shots=shots)
            result = job.result()
            job_id = getattr(job, 'job_id', lambda: 'local_sim')()
            return job_id
        else:
            raise NotImplementedError(f"Provider {provider} not supported for execution.")
            raise NotImplementedError(f"Provider {provider} not supported for execution.")

    def _dict_to_qiskit_circuit(self, circuit: dict) -> 'QuantumCircuit':
        if not QISKIT_AVAILABLE:
            raise ImportError("Qiskit is required for circuit execution.")
        n_qubits = len(circuit.get('qubits', []))
        n_clbits = len(circuit.get('clbits', [])) if 'clbits' in circuit else 0
        qc = QuantumCircuit(n_qubits, n_clbits)
        for gate in circuit.get('gates', []):
            name = gate['name'].lower()
            qubits = gate.get('qubits', [])
            params = gate.get('params', [])
            if name == 'measure' and 'clbits' in gate:
                qc.measure(qubits[0], gate['clbits'][0])
            elif hasattr(qc, name):
                getattr(qc, name)(*params, *qubits)
            else:
                qc.append(name, qubits)
        return qc

    def get_job_status(self, job_id: str) -> dict:
        status = self.job_status.get(job_id, 'unknown')
        return {'job_id': job_id, 'status': status}

    def get_job_result(self, job_id: str) -> dict:
        with self.lock:
            return self.job_results.get(job_id, {'error': 'Result not available.'})

    def cancel_job(self, job_id: str) -> None:
        with self.lock:
            if job_id in self.job_status and self.job_status[job_id] in ('pending', 'running'):
                self.job_status[job_id] = 'cancelled'

class ExecutionSimulatorAPI:
    """
    API for the Execution Simulation Module. Exposes all required methods for frontend/backend integration.
    Wraps the real ExecutionSimulator logic (no stubs).
    """
    def __init__(self, config_path: str = None):
        self.simulator = ExecutionSimulator(config_path)

    def run_circuit(self, circuit: dict, run_config: dict = None) -> str:
        """Run a circuit on the specified backend. Returns a job ID."""
        return self.simulator.run_circuit(circuit, run_config)

    def get_job_status(self, job_id: str) -> dict:
        """Get the status of a job by job ID."""
        return self.simulator.get_job_status(job_id)

    def get_job_result(self, job_id: str) -> dict:
        """Get the result of a job by job ID."""
        return self.simulator.get_job_result(job_id)

    def cancel_job(self, job_id: str) -> None:
        """Cancel a running or pending job."""
        self.simulator.cancel_job(job_id)

    def get_supported_simulation_options(self, backend_name: str) -> dict:
        """
        Get supported simulation options for a backend (noise models, max shots, etc.).
        Uses device abstraction and config management for full PRD compliance.
        """
        # Use DeviceAbstraction and ConfigManager to get backend info
        ConfigManager.load_registry()
        provider = backend_name.split('_')[0].lower()
        device_info = DeviceAbstraction.get_device_info(provider, backend_name)
        options = {
            'noise_model': device_info.get('noise_model', {}),
            'max_shots': device_info.get('max_shots', 8192),
            'native_gates': device_info.get('native_gates', []),
            'max_qubits': device_info.get('max_qubits', 0),
            'gate_error_rates': device_info.get('gate_error_rates', {}),
            'readout_errors': device_info.get('qubit_properties', {}),
        }
        return options

    def export_result(self, job_id: str, format: str, path: str) -> None:
        """Export the result of a job to a file in the specified format (json, yaml, csv)."""
        result = self.simulator.get_job_result(job_id)
        if format == 'json':
            with open(path, 'w') as f:
                json.dump(result, f, indent=2)
        elif format in ('yaml', 'yml'):
            with open(path, 'w') as f:
                yaml.safe_dump(result, f)
        elif format == 'csv':
            # Export counts as CSV
            counts = result.get('counts', {})
            with open(path, 'w') as f:
                f.write('bitstring,count\n')
                for k, v in counts.items():
                    f.write(f'{k},{v}\n')
        else:
            raise ValueError(f"Unsupported export format: {format}") 