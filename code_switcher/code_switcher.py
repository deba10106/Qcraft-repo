# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import os
import yaml
import json
from typing import List, Dict, Any, Optional, Callable, Type
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from logging_results.logging_results_manager import LoggingResultsManager

def deep_merge(base: dict, override: dict) -> dict:
    if not override:
        return base.copy()
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

class CodeSwitchingProtocol:
    def __init__(self, params: dict):
        self.params = params
        self.name = params.get('name', 'unknown_protocol')
        self.enabled = params.get('enabled', True)
        self.supported_gates = params.get('supported_gates', [])

    def apply(self, gate: dict, device_info: dict) -> List[dict]:
        logger = LoggingResultsManager()
        logger.log_event('code_switching_protocol_missing', {'protocol': self.name, 'gate': gate, 'device_info': device_info}, level='ERROR')
        raise RuntimeError(f"apply() not implemented for protocol '{self.name}'. Please provide a valid implementation or plugin.")

    def get_info(self) -> dict:
        return self.params

class MagicStateInjectionProtocol(CodeSwitchingProtocol):
    def apply(self, gate: dict, device_info: dict) -> List[dict]:
        ancilla = self.params.get('ancilla_qubits', 1)
        return [
            {'name': 'prepare_magic_state', 'qubits': [gate['qubits'][0] + device_info.get('max_qubits', 0)], 'params': []},
            {'name': 'inject_magic_state', 'qubits': gate['qubits'], 'params': []},
            gate
        ]

class LatticeSurgeryProtocol(CodeSwitchingProtocol):
    def apply(self, gate: dict, device_info: dict) -> List[dict]:
        return [
            {'name': 'lattice_surgery_start', 'qubits': gate['qubits'], 'params': []},
            gate,
            {'name': 'lattice_surgery_end', 'qubits': gate['qubits'], 'params': []}
        ]

class TeleportationProtocol(CodeSwitchingProtocol):
    def apply(self, gate: dict, device_info: dict) -> List[dict]:
        return [
            {'name': 'teleportation_start', 'qubits': gate['qubits'], 'params': []},
            gate,
            {'name': 'teleportation_end', 'qubits': gate['qubits'], 'params': []}
        ]

class CodeSwitcher:
    def __init__(self, config_overrides: dict = None, device_overrides: dict = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('code_switcher')
        self.config = deep_merge(base_config, config_overrides or {})
        # Validate config against schema if available
        try:
            valid = ConfigManager.validate_config('code_switcher')
            if not valid:
                print("[WARNING][CodeSwitcher INIT] code_switcher config failed schema validation. Proceeding with caution.")
        except Exception as e:
            print(f"[WARNING][CodeSwitcher INIT] Schema validation skipped: {e}")
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device_info = deep_merge(base_device, device_overrides or {})
        self.protocols: Dict[str, CodeSwitchingProtocol] = {}
        self.protocol_classes: Dict[str, Type[CodeSwitchingProtocol]] = {
            'magic_state_injection': MagicStateInjectionProtocol,
            'lattice_surgery': LatticeSurgeryProtocol,
            'teleportation': TeleportationProtocol
        }
        self._load_protocols()
        self.protocol_plugins: Dict[str, Type[CodeSwitchingProtocol]] = {}
        self.logger = LoggingResultsManager()

    def _load_protocols(self):
        for proto in self.config.get('switching_protocols', []):
            if proto.get('enabled', True):
                cls = self.protocol_classes.get(proto['name'])
                if cls:
                    self.protocols[proto['name']] = cls(proto)

    def reload_config(self, config_overrides: dict = None, device_overrides: dict = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('code_switcher')
        self.config = deep_merge(base_config, config_overrides or {})
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device_info = deep_merge(base_device, device_overrides or {})
        self._load_protocols()

    def identify_switching_points(self, circuit: dict, code_info: dict) -> List[dict]:
        supported_gates = code_info.get('supported_gates', [])
        switching_points = []
        for idx, gate in enumerate(circuit.get('gates', [])):
            if gate['name'] not in supported_gates:
                switching_points.append({'index': idx, 'gate': gate['name'], 'qubits': gate.get('qubits', []), 'location': idx})
        return switching_points

    def select_switching_protocol(self, gate: str, available_protocols: List[str], config: dict = None) -> str:
        debug_info = {
            'protocols_config': {k: v.supported_gates if hasattr(v, 'supported_gates') else v for k, v in self.protocols.items()}
        }
        for proto in available_protocols:
            if proto in self.protocols:
                supported = self.protocols[proto].supported_gates if hasattr(self.protocols[proto], 'supported_gates') else []
                if gate in supported:
                    return proto
        print(f"[WARNING] No suitable protocol found for gate {gate}. Skipping code switching for this gate. Available protocols: {available_protocols}. Protocols config: {debug_info['protocols_config']}")
        return None

    def apply_code_switching(self, circuit: dict, switching_points: List[dict], protocols: List[dict], device_info: dict = None) -> dict:
        gates = circuit.get('gates', [])
        new_gates = []
        protocol_map = {p['name']: self.protocols[p['name']] for p in protocols if p and 'name' in p and p['name'] in self.protocols}
        sp_idx = 0
        device = device_info if device_info is not None else self.device_info
        for i, gate in enumerate(gates):
            if sp_idx < len(switching_points) and switching_points[sp_idx]['index'] == i:
                proto_name = switching_points[sp_idx].get('protocol')
                proto = protocol_map.get(proto_name)
                if proto:
                    self.logger.log_event('protocol_applied', {'protocol': proto_name, 'gate': gate, 'device': device}, level='INFO')
                    new_gates.extend(proto.apply(gate, device))
                else:
                    self.logger.log_event('protocol_missing', {'protocol': proto_name, 'gate': gate, 'device': device}, level='WARNING')
                    new_gates.append(gate)
                sp_idx += 1
            else:
                new_gates.append(gate)
        circuit['gates'] = new_gates
        self.logger.log_event('code_switching_completed', {'circuit': circuit, 'protocols': [p['name'] for p in protocols if p and 'name' in p]}, level='INFO')
        return circuit

    def get_supported_switching_protocols(self) -> List[str]:
        return list(self.protocols.keys())

    def get_supported_gates_for_protocol(self, protocol_name: str) -> List[str]:
        proto = self.protocols.get(protocol_name)
        if proto:
            return proto.supported_gates
        return []

    def get_switching_protocol_info(self, protocol_name: str) -> dict:
        proto = self.protocols.get(protocol_name)
        if proto:
            return proto.get_info()
        return {}

    def get_switching_summary(self, circuit: dict) -> dict:
        summary = {'switching_points': []}
        for idx, gate in enumerate(circuit.get('gates', [])):
            if gate['name'].startswith('prepare_magic_state') or gate['name'].startswith('lattice_surgery') or gate['name'].startswith('teleportation'):
                summary['switching_points'].append({'index': idx, 'gate': gate['name'], 'qubits': gate.get('qubits', [])})
        return summary

    def add_switching_protocol(self, protocol_obj: CodeSwitchingProtocol) -> None:
        self.protocols[protocol_obj.name] = protocol_obj

    def list_available_protocol_plugins(self) -> List[str]:
        return list(self.protocol_classes.keys()) + list(self.protocol_plugins.keys())

    def register_protocol_plugin(self, name: str, cls: Type[CodeSwitchingProtocol]):
        self.protocol_plugins[name] = cls
        self.protocol_classes[name] = cls

class CodeSwitcherAPI:
    """
    API for the Code Switcher Module. Exposes all required methods for frontend/backend integration.
    Wraps the real CodeSwitcher logic (no stubs).
    """
    def __init__(self, config_overrides: dict = None, device_overrides: dict = None):
        self.switcher = CodeSwitcher(config_overrides, device_overrides)

    def identify_switching_points(self, circuit: dict, code_info: dict) -> List[dict]:
        return self.switcher.identify_switching_points(circuit, code_info)

    def select_switching_protocol(self, gate: str, available_protocols: List[str], config: dict = None) -> str:
        return self.switcher.select_switching_protocol(gate, available_protocols, config)

    def apply_code_switching(self, circuit: dict, switching_points: List[dict], protocols: List[dict], device_info: dict = None) -> dict:
        return self.switcher.apply_code_switching(circuit, switching_points, protocols, device_info)

    def get_supported_switching_protocols(self) -> List[str]:
        return self.switcher.get_supported_switching_protocols()

    def get_supported_gates_for_protocol(self, protocol_name: str) -> List[str]:
        return self.switcher.get_supported_gates_for_protocol(protocol_name)

    def get_switching_protocol_info(self, protocol_name: str) -> dict:
        return self.switcher.get_switching_protocol_info(protocol_name)

    def get_switching_summary(self, circuit: dict) -> dict:
        return self.switcher.get_switching_summary(circuit)

    def add_switching_protocol(self, protocol_obj: CodeSwitchingProtocol) -> None:
        self.switcher.add_switching_protocol(protocol_obj)

    def list_available_protocol_plugins(self) -> List[str]:
        return self.switcher.list_available_protocol_plugins()

    def register_protocol_plugin(self, name: str, cls: type) -> None:
        """Register a new protocol plugin class."""
        self.switcher.register_protocol_plugin(name, cls) 