# DEPRECATED: Use configuration_management.config_manager.ConfigManager and hardware_abstraction.device_abstraction.DeviceAbstraction for all config and device loading.
# This file now hard-fails on import to prevent accidental usage.
raise ImportError("scode.heuristic_layer.config_loader is deprecated. Use ConfigManager and DeviceAbstraction instead.")

def _deprecated(*args, **kwargs):
    raise NotImplementedError("This config loader is deprecated. Use ConfigManager and DeviceAbstraction instead.")

class ConfigLoader:
    @staticmethod
    def load_yaml(path):
        _deprecated()
    @staticmethod
    def load_json(path):
        _deprecated()

# def load_surface_code_config():
#     _deprecated() 