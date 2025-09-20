import os
try:
    import torch
except ImportError:
    torch = None

class MLBasedOptimizer:
    """
    ML-based circuit optimizer. Uses a trained ML model (e.g., neural network) to optimize the circuit.
    Config-driven model loading and prediction.
    """
    def __init__(self, config=None):
        self.config = config or {}
        self.model_path = self.config.get('supervised_config', {}).get('model_path', None)
        self.model = None
        if self.model_path and os.path.exists(self.model_path):
            self._load_model(self.model_path)

    def _load_model(self, path):
        if torch is None:
            raise ImportError("PyTorch is required for ML-based optimization. Please install it.")
        self.model = torch.load(path)
        self.model.eval()

    def _extract_features(self, circuit, device_info):
        # Use config-driven feature extraction
        features = []
        feature_set = self.config.get('supervised_config', {}).get('feature_set', ['gate_count', 'native_gate_count'])
        if 'gate_count' in feature_set:
            features.append(len(circuit.get('gates', [])))
        if 'native_gate_count' in feature_set:
            features.append(len(device_info.get('native_gates', [])))
        if 'depth' in feature_set:
            # Estimate circuit depth (max number of sequential gates on any qubit)
            qubit_depths = {}
            for gate in circuit.get('gates', []):
                for q in gate.get('qubits', []):
                    qubit_depths[q] = qubit_depths.get(q, 0) + 1
            features.append(max(qubit_depths.values()) if qubit_depths else 0)
        return torch.tensor(features, dtype=torch.float32)

    def _apply_prediction(self, circuit, prediction):
        # Use config-driven mapping from model output to circuit modification
        # Example: if prediction is a mask, remove gates with mask=0
        if hasattr(prediction, 'detach'):
            prediction = prediction.detach().cpu().numpy()
        if isinstance(prediction, (list, tuple)) and len(prediction) == len(circuit.get('gates', [])):
            new_gates = [g for g, keep in zip(circuit['gates'], prediction) if keep > 0.5]
            circuit['gates'] = new_gates
        # Otherwise, return circuit unchanged
        return circuit

    def optimize(self, circuit: dict, device_info: dict) -> dict:
        if self.model is None:
            raise RuntimeError("ML model not loaded. Please provide a valid model path.")
        features = self._extract_features(circuit, device_info)
        with torch.no_grad():
            prediction = self.model(features)
        optimized_circuit = self._apply_prediction(circuit, prediction)
        return optimized_circuit 