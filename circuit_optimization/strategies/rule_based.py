class RuleBasedOptimizer:
    """
    Rule-based circuit optimizer implementing basic passes: gate fusion, commutation, SWAP insertion, scheduling, qubit mapping.
    Passes are enabled/disabled via config. Main entry point is optimize().
    """
    def __init__(self, config=None):
        self.config = config or {}
        self.passes = self.config.get('optimization_passes', [
            {'name': 'gate_fusion', 'enabled': True},
            {'name': 'commutation', 'enabled': True},
            {'name': 'swap_insertion', 'enabled': True},
            {'name': 'scheduling', 'enabled': True},
            {'name': 'qubit_mapping', 'enabled': True},
        ])

    def optimize(self, circuit: dict, device_info: dict) -> dict:
        """
        Optimize the circuit by applying enabled rule-based passes in order.
        """
        for p in self.passes:
            if not p.get('enabled', True):
                continue
            name = p['name']
            if name == 'gate_fusion':
                circuit = self._normalize_gates(circuit)
            elif name == 'commutation':
                circuit = self._commutation(circuit)
            elif name == 'swap_insertion':
                circuit = self._swap_insertion(circuit, device_info)
            elif name == 'scheduling':
                circuit = self._scheduling(circuit)
            elif name == 'qubit_mapping':
                circuit = self._qubit_mapping(circuit, device_info)
        # Decompose all non-native gates to the device's native set
        from circuit_optimization.utils import decompose_to_native_gates
        native_gates = set(device_info.get('native_gates', []))
        circuit = decompose_to_native_gates(circuit, native_gates)
        return circuit


    def _normalize_gates(self, circuit: dict) -> dict:
        # Normalize gate names: lowercase, CNOT->cx
        for gate in circuit.get('gates', []):
            name = gate.get('name', '').lower()
            if name == 'cnot':
                name = 'cx'
            gate['name'] = name
        return circuit

    def _commutation(self, circuit: dict) -> dict:
        # Simple commutation: move non-overlapping gates earlier if possible
        gates = circuit.get('gates', [])
        if not gates:
            return circuit
        new_gates = []
        for gate in gates:
            inserted = False
            for i in range(len(new_gates)):
                if set(gate.get('qubits', [])) & set(new_gates[i].get('qubits', [])):
                    continue
                # Commute gate earlier
                new_gates.insert(i, gate)
                inserted = True
                break
            if not inserted:
                new_gates.append(gate)
        circuit['gates'] = new_gates
        return circuit

    def _swap_insertion(self, circuit: dict, device_info: dict) -> dict:
        # Simple SWAP insertion: for each 2-qubit gate, if qubits are not neighbors, insert a SWAP (naive)
        gates = circuit.get('gates', [])
        connectivity = device_info.get('qubit_connectivity', {})
        new_gates = []
        for gate in gates:
            qubits = gate.get('qubits', [])
            if len(qubits) == 2:
                q0, q1 = qubits
                if q1 not in connectivity.get(str(q0), []) and q0 not in connectivity.get(str(q1), []):
                    # Insert a SWAP before this gate (naive: swap q0 and q1)
                    new_gates.append({'name': 'SWAP', 'qubits': [q0, q1]})
            new_gates.append(gate)
        circuit['gates'] = new_gates
        return circuit

    def _scheduling(self, circuit: dict) -> dict:
        # Simple ASAP scheduling: assign each gate a 'time' field so that gates on the same qubit are sequential
        gates = circuit.get('gates', [])
        if not gates:
            return circuit
        qubit_time = {}
        for gate in gates:
            qubits = gate.get('qubits', [])
            # Find the max time among all involved qubits
            t = max([qubit_time.get(q, 0) for q in qubits], default=0)
            gate['time'] = t
            # Update time for all involved qubits
            for q in qubits:
                qubit_time[q] = t + 1
        return circuit

    def _qubit_mapping(self, circuit: dict, device_info: dict) -> dict:
        # Simple 1-to-1 mapping: logical qubit i -> physical qubit i (if possible)
        logical_qubits = circuit.get('qubits', [])
        physical_qubits = list(device_info.get('qubit_connectivity', {}).keys())
        mapping = {lq: pq for lq, pq in zip(logical_qubits, physical_qubits)}
        # Update all gates to use mapped qubits
        for gate in circuit.get('gates', []):
            gate['qubits'] = [mapping.get(q, q) for q in gate.get('qubits', [])]
        circuit['mapping'] = mapping
        return circuit


    def normalize_gates(self, circuit: dict) -> dict:
        # Normalize gate names: lowercase, CNOT->cx
        for gate in circuit.get('gates', []):
            name = gate.get('name', '').lower()
            if name == 'cnot':
                name = 'cx'
            gate['name'] = name
        return circuit


    def commutation(self, circuit: dict) -> dict:
        # Simple commutation: move non-overlapping gates earlier if possible
        gates = circuit.get('gates', [])
        if not gates:
            return circuit
        new_gates = []
        for gate in gates:
            inserted = False
            for i in range(len(new_gates)):
                if set(gate.get('qubits', [])) & set(new_gates[i].get('qubits', [])):
                    continue
                # Commute gate earlier
                new_gates.insert(i, gate)
                inserted = True
                break
            if not inserted:
                new_gates.append(gate)
        circuit['gates'] = new_gates
        return circuit

    def swap_insertion(self, circuit: dict, device_info: dict) -> dict:
        # Simple SWAP insertion: for each 2-qubit gate, if qubits are not neighbors, insert a SWAP (naive)
        gates = circuit.get('gates', [])
        connectivity = device_info.get('qubit_connectivity', {})
        new_gates = []
        for gate in gates:
            qubits = gate.get('qubits', [])
            if len(qubits) == 2:
                q0, q1 = qubits
                if q1 not in connectivity.get(str(q0), []) and q0 not in connectivity.get(str(q1), []):
                    # Insert a SWAP before this gate (naive: swap q0 and q1)
                    new_gates.append({'name': 'SWAP', 'qubits': [q0, q1]})
            new_gates.append(gate)
        circuit['gates'] = new_gates
        return circuit

    def scheduling(self, circuit: dict) -> dict:
        # Simple ASAP scheduling: assign each gate a 'time' field so that gates on the same qubit are sequential
        gates = circuit.get('gates', [])
        if not gates:
            return circuit
        qubit_time = {}
        for gate in gates:
            qubits = gate.get('qubits', [])
            # Find the max time among all involved qubits
            t = max([qubit_time.get(q, 0) for q in qubits], default=0)
            gate['time'] = t
            # Update time for all involved qubits
            for q in qubits:
                qubit_time[q] = t + 1
        return circuit

    def qubit_mapping(self, circuit: dict, device_info: dict) -> dict:
        # Simple 1-to-1 mapping: logical qubit i -> physical qubit i (if possible)
        logical_qubits = circuit.get('qubits', [])
        physical_qubits = list(device_info.get('qubit_connectivity', {}).keys())
        mapping = {lq: pq for lq, pq in zip(logical_qubits, physical_qubits)}
        # Update all gates to use mapped qubits
        for gate in circuit.get('gates', []):
            gate['qubits'] = [mapping.get(q, q) for q in gate.get('qubits', [])]
        circuit['mapping'] = mapping
        return circuit

    def validate_with_device(self, circuit: dict, config_dir: str) -> bool:
        # Use HardwareConfigLoader to validate circuit against device
        loader = HardwareConfigLoader(config_dir, self.config)
        device_info = loader.load_device_config()
        # Example: check qubit count
        if len(circuit.get('qubits', [])) > device_info.get('max_qubits', 0):
            return False
        # Example: check native gates
        native_gates = set(device_info.get('native_gates', []))
        for gate in circuit.get('gates', []):
            if gate['name'] not in native_gates:
                return False
        return True 