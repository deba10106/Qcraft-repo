# DEPRECATED: Use configuration_management.config_manager.ConfigManager and hardware_abstraction.device_abstraction.DeviceAbstraction for all config and device loading.
# This file is retained for legacy compatibility but should not be used in new code.

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