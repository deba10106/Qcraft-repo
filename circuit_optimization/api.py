from circuit_optimization.circuit_optimizer import CircuitOptimizer
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from typing import Dict, Any, Optional, List

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

class CircuitOptimizationAPI:
    """
    API for the Circuit Optimization Module. Exposes all required methods for frontend/backend integration.
    All configuration is loaded via the configuration management module.
    """
    def __init__(self, config_overrides: dict = None, device_overrides: dict = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('optimization')
        self.config = deep_merge(base_config, config_overrides or {})
        # Validate optimization config if schema available
        try:
            valid = ConfigManager.validate_config('optimization')
            if not valid:
                print("[WARNING][OPT API INIT] optimization config failed schema validation. Proceeding with caution.")
        except Exception as e:
            print(f"[WARNING][OPT API INIT] Schema validation skipped: {e}")
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device = deep_merge(base_device, device_overrides or {})
        self.optimizer = CircuitOptimizer(config=self.config)

    def optimize_circuit(self, circuit: Dict, device_info: Dict = None, config_overrides: Optional[Dict] = None) -> Dict:
        """
        Optimize the input circuit for the given device. Returns the optimized circuit as a data structure.
        """
        device = device_info if device_info is not None else self.device
        config = deep_merge(self.config, config_overrides or {})
        return self.optimizer.optimize_circuit(circuit, device, config_overrides)

    def get_optimization_report(self, original_circuit: Dict, optimized_circuit: Dict) -> Dict:
        """
        Return a report comparing the original and optimized circuits (gate count, depth, SWAPs, resource usage, etc.).
        """
        return self.optimizer.get_optimization_report(original_circuit, optimized_circuit)

    def validate_circuit(self, circuit: Dict, device_info: Dict = None) -> bool:
        """
        Validate that the circuit is compatible with the device (native gates, connectivity, qubit count, etc.).
        """
        device = device_info if device_info is not None else self.device
        return self.optimizer.validate_circuit(circuit, device)

    def export_circuit(self, circuit: Dict, format: str, path: str) -> None:
        """
        Export the optimized circuit to a file in the specified format (QASM, JSON, YAML).
        """
        self.optimizer.export_circuit(circuit, format, path)

    def import_circuit(self, path: str, format: str) -> Dict:
        """
        Import a circuit from a file in the specified format.
        """
        return self.optimizer.import_circuit(path, format)

    def get_supported_optimization_passes(self) -> List[str]:
        """
        Return a list of supported optimization passes (e.g., gate fusion, SWAP minimization, scheduling).
        """
        return self.optimizer.get_supported_optimization_passes()

    def get_circuit_summary(self, circuit: Dict) -> Dict:
        """
        Return a summary of the circuit (qubit count, gate count, depth, etc.) for display in the frontend.
        """
        return self.optimizer.get_circuit_summary(circuit) 