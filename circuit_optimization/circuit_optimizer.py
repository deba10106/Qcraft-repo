import os
import json
import yaml
from typing import List, Dict, Any, Optional

from circuit_optimization.strategies.rule_based import RuleBasedOptimizer
from circuit_optimization.strategies.rl_based import RLBasedOptimizer
from circuit_optimization.strategies.ml_based import MLBasedOptimizer
from circuit_optimization.utils import count_gates, calculate_depth, count_swaps

# Qiskit 4.x: QuantumCircuit is still imported from qiskit
from qiskit import QuantumCircuit

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

class HybridOptimizer:
    """
    Hybrid optimizer that combines rule-based and RL/ML optimizers in sequence.
    """
    def __init__(self, config):
        self.rule = RuleBasedOptimizer(config)
        self.rl = RLBasedOptimizer(config)
        self.ml = MLBasedOptimizer(config)
        self.config = config

    def optimize(self, circuit, device_info):
        circuit = self.rule.optimize(circuit, device_info)
        try:
            circuit = self.rl.optimize(circuit, device_info)
        except Exception:
            pass
        try:
            circuit = self.ml.optimize(circuit, device_info)
        except Exception:
            pass
        return circuit

class CircuitOptimizer:
    """
    Circuit Optimization Module for optimizing quantum circuits using rule-based, RL, ML, or hybrid strategies.
    The strategy is selected at runtime via config or config_overrides.
    """
    def __init__(self, config: dict):
        self.config = config
        self.strategy = self.config.get('optimization_strategy', 'rule_based')
        self._init_strategy()

    def _init_strategy(self):
        """Initialize the optimization strategy (rule-based, RL, ML, hybrid)."""
        if self.strategy == 'rule_based':
            self.optimizer = RuleBasedOptimizer(self.config)
        elif self.strategy == 'rl':
            self.optimizer = RLBasedOptimizer(self.config)
        elif self.strategy == 'supervised' or self.strategy == 'ml':
            self.optimizer = MLBasedOptimizer(self.config)
        elif self.strategy == 'hybrid':
            self.optimizer = HybridOptimizer(self.config)
        else:
            raise ValueError(f"Unknown optimization strategy: {self.strategy}")

    def optimize_circuit(self, circuit: dict, device_info: dict, config_overrides: Optional[dict] = None) -> dict:
        """
        Optimize the circuit using the selected strategy.
        Applies gate synthesis, scheduling, SWAP insertion, and qubit mapping as needed.
        Returns the optimized circuit as a data structure.
        """
        config = deep_merge(self.config, config_overrides or {})
        if config_overrides:
            strategy = config_overrides.get('optimization_strategy', self.strategy)
            if strategy != self.strategy:
                self.strategy = strategy
                self._init_strategy()
        return self.optimizer.optimize(circuit, device_info)

    def get_optimization_report(self, original_circuit: dict, optimized_circuit: dict) -> dict:
        """
        Return a report comparing the original and optimized circuits (gate count, depth, SWAPs, resource usage, etc.).
        """
        return {
            'original_gate_count': count_gates(original_circuit),
            'optimized_gate_count': count_gates(optimized_circuit),
            'original_depth': calculate_depth(original_circuit),
            'optimized_depth': calculate_depth(optimized_circuit),
            'depth_reduction': calculate_depth(original_circuit) - calculate_depth(optimized_circuit),
            'original_swap_count': count_swaps(original_circuit),
            'optimized_swap_count': count_swaps(optimized_circuit),
        }

    def validate_circuit(self, circuit: dict, device_info: dict) -> bool:
        """
        Validate that the circuit is compatible with the device (native gates, connectivity, qubit count, etc.).
        """
        if hasattr(self.optimizer, 'validate_with_device'):
            return self.optimizer.validate_with_device(circuit, device_info)
        return True

    def export_circuit(self, circuit: dict, format: str, path: str) -> None:
        """
        Export the optimized circuit to a file in the specified format (QASM, JSON, YAML).
        """
        if format == 'json':
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
        """
        Import a circuit from a file in the specified format.
        """
        if format == 'json':
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

    def _dict_to_qiskit_circuit(self, circuit: dict) -> 'QuantumCircuit':
        # Convert dict-based circuit to Qiskit QuantumCircuit
        if QuantumCircuit is None:
            raise ImportError("qiskit is required for QASM export. Please install qiskit.")
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
        # Convert Qiskit QuantumCircuit to dict-based circuit
        circuit = {'qubits': list(range(getattr(qc, 'max_qubits', getattr(qc, 'num_qubits', 0)))), 'clbits': list(range(qc.num_clbits)), 'gates': []}
        for instr, qargs, cargs in qc.data:
            gate = {'name': instr.name, 'qubits': [q.index for q in qargs]}
            if instr.name == 'measure' and cargs:
                gate['clbits'] = [c.index for c in cargs]
            if instr.params:
                gate['params'] = [float(p) for p in instr.params]
            circuit['gates'].append(gate)
        return circuit

    def get_supported_optimization_passes(self) -> List[str]:
        """
        Return a list of supported optimization passes (e.g., gate fusion, SWAP minimization, scheduling).
        """
        return [
            'gate_fusion',
            'commutation',
            'swap_insertion',
            'scheduling',
            'qubit_mapping',
        ]

    def get_circuit_summary(self, circuit: dict) -> dict:
        """
        Return a summary of the circuit (qubit count, gate count, depth, etc.) for display in the frontend.
        """
        return {
            'max_qubits': len(circuit.get('qubits', [])),
            'gate_count': count_gates(circuit),
            'depth': calculate_depth(circuit),
            'swap_count': count_swaps(circuit),
        } 