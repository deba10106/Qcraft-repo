# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import os
import yaml
import json
import importlib.resources
from typing import List, Dict, Any, Optional, Callable
from configuration_management.config_manager import ConfigManager
from policy.decision_policy import select_non_transversal_policy

# Qiskit 4.x: QuantumCircuit is still imported from qiskit
from qiskit import QuantumCircuit

class FaultTolerantCircuitBuilder:
    def __init__(self, config_overrides: dict = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('ft_builder')
        self.config = self._deep_merge(base_config, config_overrides or {})
        # Validate config against schema if available (warn-only)
        try:
            valid = ConfigManager.validate_config('ft_builder')
            if not valid:
                print("[WARNING][FTBuilder INIT] ft_builder config failed schema validation. Proceeding with caution.")
        except Exception as e:
            print(f"[WARNING][FTBuilder INIT] Schema validation skipped: {e}")
        self.export_formats = self.config.get('export_formats', ['qasm', 'json', 'yaml'])
        self.code_switching_protocols = self.config.get('code_switching_protocols', [])
        self.protocol_registry = {p['name']: p for p in self.code_switching_protocols}
        self.export_handlers = {}
        self.import_handlers = {}
        self.code_space_annotation_hooks: List[Callable[[dict, List[dict]], dict]] = []
        self.validation_hooks: List[Callable[[dict, dict], bool]] = []
        self.summary_hooks: List[Callable[[dict], dict]] = []

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

    # --- Extensibility APIs ---
    def register_code_switching_protocol(self, protocol: dict):
        self.protocol_registry[protocol['name']] = protocol

    def register_export_handler(self, fmt: str, handler: Callable[[dict, str], None]):
        self.export_handlers[fmt] = handler
        if fmt not in self.export_formats:
            self.export_formats.append(fmt)

    def register_import_handler(self, fmt: str, handler: Callable[[str], dict]):
        self.import_handlers[fmt] = handler
        if fmt not in self.export_formats:
            self.export_formats.append(fmt)

    def register_code_space_annotation_hook(self, hook: Callable[[dict, List[dict]], dict]):
        self.code_space_annotation_hooks.append(hook)

    def register_validation_hook(self, hook: Callable[[dict, dict], bool]):
        self.validation_hooks.append(hook)

    def register_summary_hook(self, hook: Callable[[dict], dict]):
        self.summary_hooks.append(hook)

    def reload_config(self, config_overrides: dict = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('ft_builder')
        self.config = self._deep_merge(base_config, config_overrides or {})
        self.export_formats = self.config.get('export_formats', ['qasm', 'json', 'yaml'])
        self.code_switching_protocols = self.config.get('code_switching_protocols', [])
        self.protocol_registry = {p['name']: p for p in self.code_switching_protocols}

    # --- Main APIs ---
    def assemble_fault_tolerant_circuit(self, logical_circuit: dict, mapping_info: dict, code_spaces: List[dict], device_info: dict) -> dict:
        """
        Assemble a fault-tolerant circuit by transforming logical gates into supported gates for each code space.
        If a gate is not transformable, insert code switching at the appropriate point.
        """
        # Multi-patch support: mapping_info['multi_patch_mapping']
        if 'multi_patch_mapping' in mapping_info:
            circuit = self._apply_multi_patch_mapping(logical_circuit, mapping_info['multi_patch_mapping'], code_spaces)
        else:
            circuit = self._apply_mapping(logical_circuit, mapping_info, code_spaces)
        # Fail fast if no code_spaces provided
        if not code_spaces:
            print("[ERROR] No code_spaces provided to FT circuit builder. The layout step must return at least one code space with supported_logical_gates.")
            print(f"[DEBUG] mapping_info: {mapping_info}")
            print(f"[DEBUG] device_info: {device_info}")
            print(f"[DEBUG] logical_circuit: {logical_circuit}")
            raise ValueError("No code_spaces provided by layout. Please check that your layout step returns at least one code space with supported_logical_gates.")
        # Store device for downstream policy decisions
        self._device_info = device_info
        # Transform logical gates to supported gates with policy-based selection for non-transversal gates
        circuit, switching_points = self.transform_logical_to_supported(circuit, code_spaces)
        # If not transformable, insert code switching at switching_points
        if switching_points:
            circuit = self.insert_code_switching(circuit, switching_points, code_spaces)
        if not self.validate_fault_tolerant_circuit(circuit, device_info):
            print("[ERROR] Assembled circuit is not valid for the target device.")
            print(f"[DEBUG] mapping_info: {mapping_info}")
            print(f"[DEBUG] device_info: {device_info}")
            print(f"[DEBUG] code_spaces: {code_spaces}")
            print(f"[DEBUG] logical_circuit: {logical_circuit}")
            raise ValueError("Assembled circuit is not valid for the target device.")
        return circuit

    def transform_logical_to_supported(self, circuit: dict, code_spaces: list):
        """
        Transform logical gates to supported gates for each code space. If a gate is not supported by any code space,
        mark it for code switching.
        Returns transformed circuit and list of switching points.
        """
        # Build lookup per code_space for accurate transversality checks
        supported_by_space = {
            cs.get('name'): set(cs.get('supported_logical_gates', [])) for cs in code_spaces
        }
        gates = circuit.get('gates', [])
        new_gates = []
        switching_points = []
        for idx, gate in enumerate(gates):
            gname = gate.get('name')
            cs_name = gate.get('code_space')
            is_supported = False
            if cs_name and cs_name in supported_by_space:
                is_supported = gname in supported_by_space[cs_name]
            else:
                # Fallback: supported in any space
                is_supported = any(gname in s for s in supported_by_space.values())
            if is_supported:
                new_gates.append(gate)
            else:
                policy = select_non_transversal_policy(gname, self._device_info, self.config)
                switching_points.append({'index': idx, 'to_code_space': policy})
                new_gates.append(gate)
        circuit['gates'] = new_gates
        return circuit, switching_points


    def _apply_multi_patch_mapping(self, logical_circuit: dict, multi_patch_mapping: dict, code_spaces: List[dict]) -> dict:
        print("[DEBUG] FTBuilder: multi_patch_mapping:", multi_patch_mapping)
        
        # Null check for multi_patch_mapping
        if not multi_patch_mapping:
            print("[ERROR] FTBuilder: multi_patch_mapping is empty or None")
            return {'qubits': logical_circuit.get('qubits', []), 'gates': [], 'error': 'No mapping available'}
        
        multi_patch_layout = multi_patch_mapping.get('multi_patch_layout', {})
        resource_allocation = multi_patch_mapping.get('resource_allocation', {})
        
        # Null checks for required mapping components
        if not multi_patch_layout:
            print("[ERROR] FTBuilder: multi_patch_layout is empty or None")
            return {'qubits': logical_circuit.get('qubits', []), 'gates': [], 'error': 'No patch layout available'}
            
        if not resource_allocation:
            print("[WARNING] FTBuilder: resource_allocation is empty, patches may not be correctly identified")
            
        circuit = {'qubits': logical_circuit.get('qubits', []), 'gates': []}
        
        # Track which qubits we successfully map
        mapped_qubits = set()
        unmapped_qubits = set()
        
        # Print mapping completeness for each patch
        for patch_id, patch in multi_patch_layout.items():
            layout = patch.get('layout', {})
            print(f"[DEBUG] Patch {patch_id}: {len(layout)} qubits in layout")
        
        for gate in logical_circuit.get('gates', []):
            mapped_gate = gate.copy()
            mapped_gate['patches'] = []
            mapped_gate['qubits'] = []
            for q in gate.get('qubits', []):
                patch_id = None
                for (pid, lq), pidx in resource_allocation.items():
                    if lq == q:
                        patch_id = pid
                        break
                if patch_id is not None and patch_id in multi_patch_layout:
                    patch_layout = multi_patch_layout[patch_id]['layout']
                    if q in patch_layout:
                        mapped_gate['qubits'].append(q)
                        mapped_gate['patches'].append(patch_id)
                        mapped_qubits.add(q)
                    else:
                        print(f"[WARNING] FTBuilder: Qubit {q} not found in patch {patch_id} layout")
                        unmapped_qubits.add(q)
                else:
                    print(f"[WARNING] FTBuilder: No patch found for qubit {q}")
                    unmapped_qubits.add(q)
                    
            # Only add gates if they have qubits
            if mapped_gate['qubits']:
                for hook in self.code_space_annotation_hooks:
                    mapped_gate = hook(mapped_gate, code_spaces)
                # Default annotation if no hook
                if not any(hook for hook in self.code_space_annotation_hooks):
                    for cs in code_spaces:
                        if gate['name'] in cs.get('supported_logical_gates', []):
                            mapped_gate['code_space'] = cs['name']
                circuit['gates'].append(mapped_gate)
                
        print(f"[DEBUG] FTBuilder: Mapped {len(mapped_qubits)} qubits, {len(unmapped_qubits)} qubits could not be mapped")
        if unmapped_qubits:
            print(f"[DEBUG] FTBuilder: Unmapped qubits: {unmapped_qubits}")
            
        circuit['code_spaces'] = code_spaces
        print("[DEBUG] FTBuilder: _apply_multi_patch_mapping result:", circuit)
        return circuit

    def _apply_mapping(self, logical_circuit: dict, mapping_info: dict, code_spaces: List[dict]) -> dict:
        circuit = {'qubits': logical_circuit.get('qubits', []), 'gates': []}
        logical_to_physical = mapping_info.get('logical_to_physical', {})
        for gate in logical_circuit.get('gates', []):
            mapped_gate = gate.copy()
            mapped_gate['qubits'] = [logical_to_physical.get(q, q) for q in gate.get('qubits', [])]
            # Flexible code space annotation
            for hook in self.code_space_annotation_hooks:
                mapped_gate = hook(mapped_gate, code_spaces)
            # Default annotation if no hook
            if not any(hook for hook in self.code_space_annotation_hooks):
                for cs in code_spaces:
                    if gate['name'] in cs.get('supported_logical_gates', []):
                        mapped_gate['code_space'] = cs['name']
            circuit['gates'].append(mapped_gate)
        circuit['code_spaces'] = code_spaces
        return circuit

    def insert_code_switching(self, circuit: dict, switching_points: List[dict], code_spaces: List[dict]) -> dict:
        gates = circuit.get('gates', [])
        new_gates = []
        for i, gate in enumerate(gates):
            new_gates.append(gate)
            for sp in switching_points:
                if sp['index'] == i:
                    protocol = self.protocol_registry.get(sp['to_code_space']) or next((cs for cs in code_spaces if cs['name'] == sp['to_code_space']), None)
                    if protocol:
                        new_gates.append({'name': f'code_switch_{protocol["name"]}', 'qubits': gate['qubits'], 'params': [], 'code_space': protocol['name']})
        circuit['gates'] = new_gates
        return circuit

    def validate_fault_tolerant_circuit(self, circuit: dict, device_info: dict) -> bool:
        # Built-in validation
        if len(circuit.get('qubits', [])) > device_info.get('max_qubits', 0):
            print(f"[VALIDATION ERROR] Circuit uses {len(circuit.get('qubits', []))} qubits, but device supports only {device_info.get('max_qubits', 0)}.")
            return False
        # Device native gate validation is intentionally DISABLED for FT circuit builder output
        # The FT circuit builder output is allowed to be in terms of code space supported gates
        # Only check qubit count and required device info keys
        for gate in circuit.get('gates', []):
            if str(gate['name']).strip().lower() == 'measure':
                continue
            # No native gate check here
        # Check for required device_info keys
        required_keys = ['max_qubits', 'native_gates', 'qubit_positions', 'connectivity']
        for k in required_keys:
            if k not in device_info:
                print(f"[VALIDATION WARNING] device_info is missing key: '{k}'")
        # Configurable validation hooks
        for hook in self.validation_hooks:
            if not hook(circuit, device_info):
                print(f"[VALIDATION ERROR] Custom validation hook {hook.__name__} failed.")
                return False
        print("[VALIDATION] FT circuit builder: Skipping device native gate check. Circuit may contain code space logical gates.")
        return True

    def export_circuit(self, circuit: dict, format: str, path: str) -> None:
        if format in self.export_handlers:
            self.export_handlers[format](circuit, path)
        elif format == 'json':
            with open(path, 'w') as f:
                json.dump(circuit, f, indent=2)
        elif format in ('yaml', 'yml'):
            with open(path, 'w') as f:
                yaml.safe_dump(circuit, f)
        elif format == 'qasm':
            qc = self._dict_to_qiskit_circuit(circuit)
            with open(path, 'w') as f:
                qc.qasm(f)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def import_circuit(self, path: str, format: str) -> dict:
        if format in self.import_handlers:
            return self.import_handlers[format](path)
        elif format == 'json':
            with open(path, 'r') as f:
                return json.load(f)
        elif format in ('yaml', 'yml'):
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        elif format == 'qasm':
            with open(path) as f:
                qc = QuantumCircuit.from_qasm_file(f)
            return self._qiskit_circuit_to_dict(qc)
        else:
            raise ValueError(f"Unsupported import format: {format}")

    def get_supported_export_formats(self) -> List[str]:
        return self.export_formats

    # REMOVED: _rewrite_to_native_gates and all device native gate decomposition logic from FT builder.
    # The FT builder now only outputs code space logical gates and inserts code switching protocols as needed.
    # All decomposition to device native gates must be handled in the optimizer module, not here.



    def get_circuit_summary(self, circuit: dict) -> dict:
        max_qubits = len(circuit.get('qubits', []))
        gate_count = len(circuit.get('gates', []))
        depth = self._calculate_depth(circuit)
        code_switch_points = [i for i, g in enumerate(circuit.get('gates', [])) if g['name'].startswith('code_switch_')]
        summary = {
            'max_qubits': max_qubits,
            'gate_count': gate_count,
            'depth': depth,
            'code_switch_points': code_switch_points,
        }
        # Extensible summary
        for hook in self.summary_hooks:
            summary.update(hook(circuit))
        return summary

    def _calculate_depth(self, circuit: dict) -> int:
        if not circuit.get('gates'):
            return 0
        qubit_timesteps = {q: 0 for q in circuit.get('qubits', [])}
        for gate in circuit['gates']:
            max_t = max([qubit_timesteps.get(q, 0) for q in gate.get('qubits', [])], default=0)
            for q in gate.get('qubits', []):
                qubit_timesteps[q] = max_t + 1
        return max(qubit_timesteps.values(), default=0)

    def _dict_to_qiskit_circuit(self, circuit: dict) -> 'QuantumCircuit':
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

    def _qiskit_circuit_to_dict(self, qc: 'QuantumCircuit') -> dict:
        circuit = {'qubits': list(range(qc.num_qubits)), 'clbits': list(range(qc.num_clbits)), 'gates': []}
        for instr, qargs, cargs in qc.data:
            gate = {'name': instr.name, 'qubits': [q.index for q in qargs]}
            if instr.name == 'measure' and cargs:
                gate['clbits'] = [c.index for c in cargs]
            if instr.params:
                gate['params'] = [float(p) for p in instr.params]
            circuit['gates'].append(gate)
        return circuit 