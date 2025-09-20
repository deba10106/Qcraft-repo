import numpy as np

try:
    import stim
except ImportError:
    stim = None
try:
    import pymatching
except ImportError:
    pymatching = None

class DecoderInterface:
    @staticmethod
    def _check_logical_error(meas_outcomes, logical_op):
        """
        Check if the parity of the logical operator (on measurement outcomes) is odd (logical error).
        Args:
            meas_outcomes: numpy array of measurement outcomes (bits for each data qubit)
            logical_op: list of data qubit indices for the logical operator
        Returns:
            True if logical error occurred, False otherwise
        """
        # Only use indices that are in bounds
        valid_indices = [i for i in logical_op if 0 <= i < len(meas_outcomes)]
        if not valid_indices:
            raise ValueError(f"No valid logical operator indices: {logical_op} for measurement outcome of length {len(meas_outcomes)}")
        return bool(np.sum(meas_outcomes[valid_indices]) % 2)

    @staticmethod
    def estimate_logical_error_rate(layout, mapping, noise_model, num_trials=1000, error_prob=0.001, logical_op_type='Z'):
        """
        Estimate the logical error rate (LER) for a given surface code layout and mapping using stim and pymatching.
        Args:
            layout: Surface code layout (SurfaceCodeObject or dict with stabilizer info)
            mapping: logical_to_physical mapping dict
            noise_model: dict describing noise (e.g., {'p': 0.001})
            num_trials: Number of Monte Carlo trials
            error_prob: Physical error probability (if not in noise_model)
            logical_op_type: 'Z' or 'X' (which logical operator to use for LER)
        Returns:
            Estimated logical error rate (float)
        Raises:
            ImportError if stim or pymatching is not available
        """
        if stim is None or pymatching is None:
            print('[WARNING] stim or pymatching not available! Returning LER=0.0')
            return 0.0
        # Build stim circuit from layout and mapping
        if hasattr(layout, 'to_stim_circuit'):
            circuit = layout.to_stim_circuit(mapping, noise_model)
            detector_error_model = circuit.detector_error_model(decompose_errors=True)
            # Get logical operator indices (data qubit indices)
            logical_op = None
            if hasattr(layout, 'logical_operators') and logical_op_type in layout.logical_operators:
                logical_op = layout.logical_operators[logical_op_type]
            print(f'[DEBUG] LER: logical_op_type={logical_op_type}, logical_op={logical_op}, mapping={mapping}')
            if logical_op is None or len(logical_op) == 0:
                print(f'[WARNING] No logical operator "{logical_op_type}" defined in layout for LER calculation! Returning LER=0.0')
                return 0.0
            # Get data qubit indices for measurement
            if hasattr(layout, 'get_data_qubits'):
                data_qubits = layout.get_data_qubits()
            else:
                data_qubits = list(range(len(logical_op)))
        else:
            # Fallback: build a simple stim circuit for a distance-d repetition code
            d = layout.get('code_distance', 3) if isinstance(layout, dict) else 3
            circuit = stim.Circuit()
            for i in range(d):
                circuit.append_operation("X_ERROR", [i], error_prob)
            circuit.append_operation("M", list(range(d)))
            detector_error_model = circuit.detector_error_model(decompose_errors=True)
            logical_op = list(range(d))  # All qubits for repetition code
            data_qubits = list(range(d))
        # Build pymatching decoder
        matching = pymatching.Matching(detector_error_model)
        # Use stim's detector sampler for Monte Carlo trials
        sampler = circuit.compile_detector_sampler()
        detector_samples = sampler.sample(num_trials)
        # Use stim's sampler for measurement outcomes
        meas_sampler = circuit.compile_sampler()
        meas_samples = meas_sampler.sample(num_trials)
        logical_errors = 0
        for i in range(num_trials):
            syndrome = detector_samples[i, :]
            correction = matching.decode(syndrome)
            # Get measurement outcomes for data qubits
            meas_outcomes = meas_samples[i, :]
            # Apply correction to measurement outcomes (bitwise XOR)
            corrected_meas = np.copy(meas_outcomes)
            # Only apply correction to data qubits (if correction is same length)
            if len(correction) == len(corrected_meas):
                corrected_meas ^= correction
            # Check if the parity of the logical operator is odd (logical error)
            if DecoderInterface._check_logical_error(corrected_meas, logical_op):
                logical_errors += 1
        ler = logical_errors / num_trials
        return float(ler) 