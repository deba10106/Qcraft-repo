import os
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from .heuristic_initialization_layer import HeuristicInitializationLayer

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

def main(config_overrides=None, device_overrides=None):
    ConfigManager.load_registry()
    base_config = ConfigManager.get_config('multi_patch_rl_agent')
    config = deep_merge(base_config, config_overrides or {})
    hardware_json_path = ConfigManager.config_registry['hardware']
    base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
    device = deep_merge(base_device, device_overrides or {})
    h_layer = HeuristicInitializationLayer(config, device)
    params = config['surface_code']
    surface_code = h_layer.generate_surface_code(
        code_distance=params['code_distance'],
        layout_type=params['layout_type'],
        visualize=params.get('visualize', False)
    )
    print(f"Generated surface code: d={surface_code.code_distance}, layout={surface_code.layout_type}, connectivity={surface_code.grid_connectivity}")
    print(f"Qubits: {len(surface_code.qubit_layout)} | Stabilizers: {len(surface_code.stabilizer_map)} | Logical ops: {len(surface_code.logical_operators)}")

if __name__ == '__main__':
    main() 