import os
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from .graph_transformer import ConnectivityAwareGraphTransformer

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
    transformer = ConnectivityAwareGraphTransformer(
        config=config,
        hardware_graph=device,
        native_gates=device['native_gates'],
        gate_error_rates=device['gate_error_rates'],
        qubit_error_rates={q: device['qubit_properties'][q]['readout_error'] for q in device['qubit_properties']}
    )
    result = transformer.transform(surface_code)
    print(f"Transformed layout: {result['transformed_layout']}")
    print(f"Hardware stabilizer map: {result['hardware_stabilizer_map']}")
    print(f"Connectivity overhead: {result['connectivity_overhead_info']}")
    print(f"Annotated graph nodes: {result['annotated_graph'].nodes(data=True)}")

if __name__ == '__main__':
    main() 