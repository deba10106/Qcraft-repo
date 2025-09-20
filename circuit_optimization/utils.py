def fuse_gates(circuit: dict) -> dict:
    """
    Fuse consecutive identical single-qubit gates (same name, qubit, params) into one.
    This is a minimal, production-compatible placeholder for RL compatibility.
    """
    gates = circuit.get('gates', [])
    if not gates:
        return circuit
    fused = []
    for g in gates:
        if fused and g['name'] == fused[-1]['name'] and g.get('qubits') == fused[-1].get('qubits') and g.get('params') == fused[-1].get('params'):
            continue  # fuse
        fused.append(g)
    circuit['gates'] = fused
    return circuit

def map_qubits(circuit: dict) -> dict:
    """
    Map qubits by reversing the qubit list and updating all gate qubit indices accordingly.
    This is a minimal, production-compatible placeholder for RL compatibility.
    """
    qubits = circuit.get('qubits', [])
    if not qubits:
        return circuit
    qubit_map = {q: qubits[::-1][i] for i, q in enumerate(qubits)}
    for gate in circuit.get('gates', []):
        gate['qubits'] = [qubit_map.get(q, q) for q in gate.get('qubits', [])]
    circuit['qubits'] = qubits[::-1]
    return circuit

def commute_gates(circuit: dict) -> dict:
    """
    Commute gates by reversing their order (minimal placeholder).
    Replace with advanced commutation logic as needed.
    """
    gates = circuit.get('gates', [])
    circuit['gates'] = list(reversed(gates))
    return circuit

def schedule_gates(circuit: dict) -> dict:
    """
    Schedule gates by sorting them by their 'time' field (if present).
    This is a minimal, production-compatible placeholder for RL compatibility.
    """
    gates = circuit.get('gates', [])
    if all('time' in g for g in gates):
        circuit['gates'] = sorted(gates, key=lambda g: g['time'])
    # If no 'time' field, leave unchanged
    return circuit

def insert_swaps(circuit: dict) -> dict:
    """
    Insert a SWAP gate between the first two qubits (if available) at the end of the circuit.
    This is a minimal placeholder for RL compatibility. Replace with advanced logic as needed.
    """
    qubits = circuit.get('qubits', [])
    if len(qubits) >= 2:
        swap_gate = {'name': 'swap', 'qubits': [qubits[0], qubits[1]], 'params': []}
        circuit.setdefault('gates', []).append(swap_gate)
    return circuit

def count_gates(circuit: dict) -> int:
    """Return the number of gates in the circuit."""
    return len(circuit.get('gates', []))

def calculate_depth(circuit: dict) -> int:
    """Estimate the circuit depth (max time step)."""
    # Assume each gate has a 'time' field; otherwise, return 0
    if not circuit.get('gates'):
        return 0
    return max((g.get('time', 0) for g in circuit['gates']), default=0) + 1

def count_swaps(circuit: dict) -> int:
    """Count the number of SWAP gates in the circuit."""
    return sum(1 for g in circuit.get('gates', []) if g.get('name', '').lower() == 'swap')


def optimize_measurements(circuit: dict) -> dict:
    """
    Move all measurement gates to the end of the circuit.
    This is a minimal, production-compatible placeholder for RL compatibility.
    """
    gates = circuit.get('gates', [])
    if not gates:
        return circuit
    non_meas = [g for g in gates if g.get('name', '').lower() != 'measure']
    meas = [g for g in gates if g.get('name', '').lower() == 'measure']
    circuit['gates'] = non_meas + meas
    return circuit

def remove_redundant_gates(circuit: dict) -> dict:
    """
    Remove consecutive duplicate gates (same name, qubits, params).
    This is a minimal, production-compatible placeholder for RL compatibility.
    """
    gates = circuit.get('gates', [])
    if not gates:
        return circuit
    new_gates = [gates[0]]
    for g in gates[1:]:
        prev = new_gates[-1]
        if g['name'] == prev['name'] and g.get('qubits') == prev.get('qubits') and g.get('params') == prev.get('params'):
            continue  # skip redundant
        new_gates.append(g)
    circuit['gates'] = new_gates
    return circuit

def decompose_to_native_gates(circuit: dict, native_gates: set) -> dict:
    """
    Decompose all non-native gates in the circuit into the provided native gate set.
    Known decompositions:
      - 'h' -> rz(pi/2), sx, rz(pi/2)
      - 't' -> rz(pi/4)
      - 's' -> rz(pi/2)
      - 'y' -> sx, rz(pi), sx
      - 'z' -> rz(pi)
      - 'x' -> sx, sx
    Any gate not in native_gates and not in known decompositions will raise an error.
    Args:
        circuit: Circuit dict with 'gates' key (list of gate dicts)
        native_gates: Set of gate names supported by the device
    Returns:
        Circuit dict with all gates in native_gates
    """
    import math
    decomposed_gates = []
    for gate in circuit.get('gates', []):
        name = gate['name'].lower()
        qubits = gate.get('qubits', [])
        params = gate.get('params', [])
        # Always allow measure gates (any case)
        if name == 'measure':
            decomposed_gates.append(gate)
        elif name in native_gates:
            decomposed_gates.append(gate)
        elif name == 'h':
            decomposed_gates.extend([
                {'name': 'rz', 'qubits': qubits, 'params': [math.pi/2]},
                {'name': 'sx', 'qubits': qubits, 'params': []},
                {'name': 'rz', 'qubits': qubits, 'params': [math.pi/2]},
            ])
        elif name == 't':
            decomposed_gates.append({'name': 'rz', 'qubits': qubits, 'params': [math.pi/4]})
        elif name == 's':
            decomposed_gates.append({'name': 'rz', 'qubits': qubits, 'params': [math.pi/2]})
        elif name == 'y':
            decomposed_gates.extend([
                {'name': 'sx', 'qubits': qubits, 'params': []},
                {'name': 'rz', 'qubits': qubits, 'params': [math.pi]},
                {'name': 'sx', 'qubits': qubits, 'params': []},
            ])
        elif name == 'z':
            decomposed_gates.append({'name': 'rz', 'qubits': qubits, 'params': [math.pi]})
        elif name == 'x' and 'sx' in native_gates:
            # x = sx sx if only sx is native
            decomposed_gates.extend([
                {'name': 'sx', 'qubits': qubits, 'params': []},
                {'name': 'sx', 'qubits': qubits, 'params': []},
            ])
        elif name == 'swap' and 'cx' in native_gates:
            # SWAP(q0, q1) = CX(q0,q1) CX(q1,q0) CX(q0,q1)
            q0, q1 = qubits
            decomposed_gates.extend([
                {'name': 'cx', 'qubits': [q0, q1], 'params': []},
                {'name': 'cx', 'qubits': [q1, q0], 'params': []},
                {'name': 'cx', 'qubits': [q0, q1], 'params': []},
            ])
        else:
            raise ValueError(f"No decomposition for gate '{name}' to native gates {native_gates}")
    circuit['gates'] = decomposed_gates
    return circuit