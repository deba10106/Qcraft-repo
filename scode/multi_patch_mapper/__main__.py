import os
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from .multi_patch_mapper import MultiPatchMapper

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
    multi_patch_cfg = config['multi_patch']
    num_patches = multi_patch_cfg['num_patches']
    patch_shapes = multi_patch_cfg['patch_shapes']
    surface_codes = [
        h_layer.generate_surface_code(
            code_distance=params['code_distance'],
            layout_type=params['layout_type'],
            visualize=False
        ) for _ in range(num_patches)
    ]
    mapping_constraints = multi_patch_cfg
    mapper = MultiPatchMapper(config, device)
    result = mapper.map_patches(surface_codes, mapping_constraints)
    print(f"Multi-patch layout: {result['multi_patch_layout']}")
    print(f"Inter-patch connectivity: {result['inter_patch_connectivity']}")
    print(f"Resource allocation: {result['resource_allocation']}")
    print(f"Optimization metrics: {result['optimization_metrics']}")

if __name__ == '__main__':
    main() 