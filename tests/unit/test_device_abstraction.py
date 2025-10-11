# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction


def test_load_selected_device_and_normalization():
    ConfigManager.load_registry()
    hw_path = ConfigManager.config_registry['hardware']
    dev = DeviceAbstraction.load_selected_device(hw_path)
    assert isinstance(dev, dict)
    assert 'device_name' in dev and 'name' in dev
    assert isinstance(dev.get('max_qubits'), int) and dev['max_qubits'] > 0
    if 'qubit_connectivity' in dev:
        for k, v in dev['qubit_connectivity'].items():
            assert isinstance(k, int)
            assert all(isinstance(n, int) for n in v)


def test_list_devices_returns_list():
    ConfigManager.load_registry()
    hw = ConfigManager.load_hardware_json()
    provider = hw.get('provider_name', 'ibm')
    lst = DeviceAbstraction.list_devices(provider)
    assert isinstance(lst, list)


def test_validate_circuit_for_device_native_and_non_native():
    ConfigManager.load_registry()
    hw = ConfigManager.load_hardware_json()
    provider = hw['provider_name']
    device = hw['device_name']
    native = {
        'qubits': [0, 1],
        'gates': [
            {'name': 'x', 'qubits': [0]},
            {'name': 'rz', 'qubits': [0], 'params': [0.1]},
            {'name': 'sx', 'qubits': [1]},
            {'name': 'cx', 'qubits': [0, 1]},
        ],
    }
    assert DeviceAbstraction.validate_circuit_for_device(native, provider, device) is True
    non_native = {'qubits': [0], 'gates': [{'name': 'h', 'qubits': [0]}]}
    assert DeviceAbstraction.validate_circuit_for_device(non_native, provider, device) is False
