import pytest

from scode.api import SurfaceCodeAPI


def test_surface_api_lists_and_distances():
    api = SurfaceCodeAPI()
    types_ = api.list_layout_types()
    assert isinstance(types_, list) and len(types_) >= 1
    dists = api.list_code_distances()
    assert isinstance(dists, list) and all(isinstance(d, int) and d % 2 == 1 for d in dists)


def test_calculate_max_code_distance_monotonic():
    api = SurfaceCodeAPI()
    d_small = api.calculate_max_code_distance(max_qubits=20, logical_qubits=1, layout_type='planar')
    d_large = api.calculate_max_code_distance(max_qubits=200, logical_qubits=1, layout_type='planar')
    assert d_large >= d_small


def test_list_supported_logical_gates_basic():
    api = SurfaceCodeAPI()
    gates = api.list_supported_logical_gates(layout_type='rotated', code_distance=3, logical_operators={'X':[0], 'Z':[1]})
    assert 'X' in gates and 'Z' in gates and 'CNOT' in gates and 'H' in gates
