import os
import yaml
import json
from typing import List, Dict, Any
from configuration_management.config_manager import ConfigManager
import importlib.resources

class DeviceAbstraction:
    """
    Device Abstraction Module for managing device information, validation, and config-driven device logic.
    All configuration is YAML/JSON-driven and APIs are pure Python for frontend/backend integration.
    """
    @staticmethod
    def load_selected_device(hardware_json_path: str) -> dict:
        """
        Load the provider and device name from hardware.json, select the correct provider config file, and return the features of the specified device.
        """
        # Robustly load hardware.json from package or fallback to filesystem
        try:
            from importlib.resources import files
            hw_path = files('configs').joinpath('hardware.json')
            with hw_path.open('r') as f:
                hw = json.load(f)
        except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
            with open(hardware_json_path, 'r') as f:
                hw = json.load(f)
        # Validate hardware.json against schema if available
        try:
            from configuration_management.config_manager import ConfigManager
            from configuration_management.schema_validator import SchemaValidator
            try:
                hw_schema = ConfigManager.get_schema('hardware')
            except Exception:
                hw_schema = None
            if hw_schema is not None:
                if not SchemaValidator.validate_with_schema(hw, hw_schema):
                    print("[WARNING][DeviceAbstraction] hardware.json failed schema validation. Proceeding.")
        except Exception as e:
            print(f"[WARNING][DeviceAbstraction] hardware.json schema validation skipped: {e}")
        provider = hw['provider_name'].lower()
        device_name = hw['device_name']
        config_path = ConfigManager.resolve_device_config(provider)
        fname = os.path.basename(config_path)
        # Robustly load provider config YAML from package or fallback to filesystem
        try:
            from importlib.resources import files
            provider_path = files('configs').joinpath(fname)
            with provider_path.open('r') as f:
                devices_yaml = yaml.safe_load(f)
        except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
            with open(config_path, 'r') as f:
                devices_yaml = yaml.safe_load(f)
        # Try '<provider>_devices' first, then 'devices', then any key ending with '_devices'
        provider_key = f'{provider}_devices'
        device_list = devices_yaml.get(provider_key, None)
        used_key = provider_key
        if device_list is None:
            device_list = devices_yaml.get('devices', None)
            used_key = 'devices'
        if device_list is None:
            # Fallback: find the first key ending with '_devices'
            for key in devices_yaml:
                if key.endswith('_devices'):
                    device_list = devices_yaml[key]
                    used_key = key
                    break
        if device_list is None:
            raise ValueError(f"No device list found in {config_path}. Tried keys: '{provider_key}', 'devices', and any '_devices' key.")
        for dev in device_list:
            if dev.get('name') == device_name or dev.get('device_name') == device_name:
                # Ensure both 'name' and 'device_name' are present for compatibility
                if 'name' not in dev:
                    dev['name'] = dev.get('device_name')
                if 'device_name' not in dev:
                    dev['device_name'] = dev.get('name')
                # Ensure 'max_qubits' is present and correct
                if 'max_qubits' not in dev or not isinstance(dev['max_qubits'], int) or not dev['max_qubits']:
                    max_qubits = dev.get('device_limits', {}).get('max_qubits')
                    if max_qubits is not None and isinstance(max_qubits, int) and max_qubits > 0:
                        dev['max_qubits'] = max_qubits
                    else:
                        print(f"[ERROR] Device info for {device_name} is missing a valid max_qubits! dev={dev}")
                        raise ValueError(f"Device info for {device_name} is missing a valid max_qubits!")
                # Normalize common fields (connectivity, positions, provider name)
                dev = DeviceAbstraction._normalize_device_info(provider, dev)
                # Validate device config against provider schema if available
                try:
                    valid = DeviceAbstraction.validate_device_config(dev)
                    if not valid:
                        print(f"[WARNING][DeviceAbstraction] Device config for {device_name} failed schema validation. Proceeding.")
                except Exception as e:
                    print(f"[WARNING][DeviceAbstraction] Schema validation skipped: {e}")
                return dev
        raise ValueError(f"Device {device_name} not found in {config_path} (searched key '{used_key}')")

    @staticmethod
    def list_devices(provider_name: str) -> List[str]:
        """
        Return a list of all available device names for a given provider.
        """
        config_path = ConfigManager.resolve_device_config(provider_name)
        fname = os.path.basename(config_path)
        try:
            from importlib.resources import files
            hw_path = files('configs').joinpath(fname)
            with hw_path.open('r') as f:
                devices_yaml = yaml.safe_load(f)
        except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
            with open(config_path, 'r') as f:
                devices_yaml = yaml.safe_load(f)
        # Try '<provider>_devices' first, then 'devices', then any key ending with '_devices'
        provider_key = f'{provider_name.lower()}_devices'
        device_list = devices_yaml.get(provider_key, None)
        used_key = provider_key
        if device_list is None:
            device_list = devices_yaml.get('devices', None)
            used_key = 'devices'
        if device_list is None:
            # Fallback: find the first key ending with '_devices'
            for key in devices_yaml:
                if key.endswith('_devices'):
                    device_list = devices_yaml[key]
                    used_key = key
                    break
        if device_list is None:
            return []
        return [dev.get('name') or dev.get('device_name') for dev in device_list]

    @staticmethod
    def get_device_info(provider_name: str, device_name: str) -> dict:
        """
        Return detailed information for the specified device from the correct provider config file.
        """
        config_path = ConfigManager.resolve_device_config(provider_name)
        fname = os.path.basename(config_path)
        try:
            from importlib.resources import files
            hw_path = files('configs').joinpath(fname)
            with hw_path.open('r') as f:
                devices_yaml = yaml.safe_load(f)
        except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
            with open(config_path, 'r') as f:
                devices_yaml = yaml.safe_load(f)
        # Try '<provider>_devices' first, then 'devices', then any key ending with '_devices'
        provider_key = f'{provider_name.lower()}_devices'
        device_list = devices_yaml.get(provider_key, None)
        used_key = provider_key

        if device_list is None:
            device_list = devices_yaml.get('devices', None)
            used_key = 'devices'

        if device_list is None:
            for key in devices_yaml:
                if key.endswith('_devices'):
                    device_list = devices_yaml[key]
                    used_key = key

                    break
        if device_list is None:
            raise ValueError(f"No device list found in {config_path}. Tried keys: '{provider_key}', 'devices', and any '_devices' key.")

        for dev in device_list:
            if dev.get('name') == device_name or dev.get('device_name') == device_name:

                if 'name' not in dev:
                    dev['name'] = dev.get('device_name')
                if 'device_name' not in dev:
                    dev['device_name'] = dev.get('name')
                if 'max_qubits' not in dev or not isinstance(dev['max_qubits'], int) or not dev['max_qubits']:
                    max_qubits = dev.get('device_limits', {}).get('max_qubits')
                    if max_qubits is not None and isinstance(max_qubits, int) and max_qubits > 0:
                        dev['max_qubits'] = max_qubits
                    else:
                        print(f"[ERROR] Device info for {device_name} is missing a valid max_qubits! dev={dev}")
                        raise ValueError(f"Device info for {device_name} is missing a valid max_qubits!")
                # Normalize and validate
                dev = DeviceAbstraction._normalize_device_info(provider_name.lower(), dev)
                try:
                    valid = DeviceAbstraction.validate_device_config(dev)
                    if not valid:
                        print(f"[WARNING][DeviceAbstraction] Device config for {device_name} failed schema validation. Proceeding.")
                except Exception as e:
                    print(f"[WARNING][DeviceAbstraction] Schema validation skipped: {e}")
                return dev
        print(f"[ERROR][DeviceAbstraction] Device {device_name} not found in {config_path} (searched key '{used_key}')")
        raise ValueError(f"Device {device_name} not found in {config_path} (searched key '{used_key}')")

    @staticmethod
    def validate_device_config(device_config: dict) -> bool:
        """
        Validate a device configuration against the required schema.
        """
        from configuration_management.config_manager import ConfigManager
        from configuration_management.schema_validator import SchemaValidator
        provider = (device_config.get('provider_name') or '').lower()
        if not provider:
            # Try to infer from device name prefix
            provider = (device_config.get('name') or device_config.get('device_name') or '').split('_')[0].lower()
        module_name = f"{provider}_devices"
        try:
            schema = ConfigManager.get_schema(module_name)
        except Exception:
            return True  # No schema found, treat as valid
        return SchemaValidator.validate_with_schema(device_config, schema)

    @staticmethod
    def _normalize_device_info(provider: str, dev: dict) -> dict:
        """Normalize connectivity aliases and key types for downstream consumers."""
        d = dict(dev)
        # Provider name
        if not d.get('provider_name'):
            d['provider_name'] = provider
        # Connectivity aliasing
        qc = d.get('qubit_connectivity')
        conn = d.get('connectivity')
        if qc is None and conn is not None:
            qc = conn
            d['qubit_connectivity'] = conn
        if conn is None and qc is not None:
            d['connectivity'] = qc
        # Ensure integer keys and neighbor ints
        def _intify_connectivity(c):
            if isinstance(c, dict):
                new_c = {}
                for k, v in c.items():
                    try:
                        ik = int(k)
                    except Exception:
                        ik = k
                    new_c[ik] = [int(n) if not isinstance(n, int) and str(n).isdigit() else int(n) if isinstance(n, bool) is False and isinstance(n, (int,)) else n for n in v]
                return new_c
            return c
        if isinstance(qc, dict):
            qc = _intify_connectivity(qc)
            d['qubit_connectivity'] = qc
            d['connectivity'] = qc
        # Qubit positions keys to int
        qp = d.get('qubit_positions')
        if isinstance(qp, dict):
            new_qp = {}
            for k, v in qp.items():
                try:
                    ik = int(k)
                except Exception:
                    ik = k
                new_qp[ik] = v
            d['qubit_positions'] = new_qp
        # Ensure native_gates present
        if 'native_gates' not in d or not isinstance(d['native_gates'], list):
            d['native_gates'] = d.get('native_gates', []) or []
        return d

    @staticmethod
    def add_device(provider_name: str, device_config: dict) -> None:
        """
        Add a new device configuration to the correct provider config file at runtime.
        """
        config_path = ConfigManager.resolve_device_config(provider_name)
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        if 'devices' not in data:
            data['devices'] = []
        data['devices'].append(device_config)
        with open(config_path, 'w') as f:
            yaml.safe_dump(data, f)

    @staticmethod
    def remove_device(provider_name: str, device_name: str) -> None:
        """
        Remove a device configuration from the correct provider config file.
        """
        config_path = ConfigManager.resolve_device_config(provider_name)
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        data['devices'] = [dev for dev in data.get('devices', []) if dev.get('name') != device_name and dev.get('device_name') != device_name]
        with open(config_path, 'w') as f:
            yaml.safe_dump(data, f)

    @staticmethod
    def update_device(provider_name: str, device_name: str, updates: dict) -> None:
        """
        Update properties of an existing device configuration in the correct provider config file.
        """
        config_path = ConfigManager.resolve_device_config(provider_name)
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        for dev in data.get('devices', []):
            if dev.get('name') == device_name or dev.get('device_name') == device_name:
                dev.update(updates)
        with open(config_path, 'w') as f:
            yaml.safe_dump(data, f)

    @staticmethod
    def is_gate_supported(provider_name: str, device_name: str, gate: str) -> bool:
        """
        Check if a gate is natively supported by the device.
        """
        dev = DeviceAbstraction.get_device_info(provider_name, device_name)
        return gate in dev.get('native_gates', [])

    @staticmethod
    def get_native_gates(provider_name: str, device_name: str) -> List[str]:
        """
        Return the list of native gates for the device.
        """
        dev = DeviceAbstraction.get_device_info(provider_name, device_name)
        return dev.get('native_gates', [])

    @staticmethod
    def validate_circuit_for_device(circuit: dict, provider_name: str, device_name: str) -> bool:
        """
        Validate that a circuit is compatible with the device (native gates, connectivity, qubit count, etc.).
        """
        dev = DeviceAbstraction.get_device_info(provider_name, device_name)
        if len(circuit.get('qubits', [])) > dev.get('max_qubits', 0):
            return False
        native_gates = set(dev.get('native_gates', []))
        for gate in circuit.get('gates', []):
            if gate['name'] not in native_gates:
                return False
        # Optionally check connectivity here
        return True

    @staticmethod
    def get_current_provider_name():
        hw = ConfigManager.load_hardware_json()
        return hw.get('provider_name')

    @staticmethod
    def load_hardware_json(hardware_json_path):
        try:
            from importlib.resources import files
            hw_path = files('configs').joinpath('hardware.json')
            with hw_path.open('r') as f:
                return json.load(f)
        except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
            try:
                from importlib_resources import files
                hw_path = files('configs').joinpath('hardware.json')
                with hw_path.open('r') as f:
                    return json.load(f)
            except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
                with open(hardware_json_path, 'r') as f:
                    return json.load(f)