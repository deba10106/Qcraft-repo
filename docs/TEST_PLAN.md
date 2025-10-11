<!-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 | SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com> -->

# QCraft Test Plan (Repository: Qcraft-repo)

Last updated: 2025-10-07 10:12 (local)

## Scope and Objectives
- **Goal**: Achieve high-confidence correctness for core modules, APIs, and end-to-end workflows described in `QCraft_Technical_Specification_Document.md`.
- **Focus**: Deterministic behavior, config-driven paths, optional dependency guards, robust error handling, and reproducibility.
- **Out of scope**: Performance/stress benchmarks beyond smoke metrics; vendor cloud submissions (mocked/skipped). RL training runs are exercised via smoke and existing `scode/tests/` where applicable.

## Strategy
- **Unit tests**: Self-contained, fast tests for pure Python modules, config IO, capability detection, encryption, provenance, job packaging, device abstraction, execution simulator helpers, code switcher, logging manager.
- **Integration tests**: Keep `tests/integration/test_end_to_end_workflow.py` as main e2e; expand with variants as needed (skipped if heavy deps are missing).
- **Dependency-conditional tests**: Use `pytest.importorskip()` for optional deps like `qiskit`, `stable_baselines3`, `cryptography`, `keyring`, `matplotlib`.
- **Fixtures**: Use real configs from `configs/` via `ConfigManager` where feasible; avoid network and external services.

## Environments and Optional Dependencies
- `qiskit`, `qiskit_aer`, `qiskit_ibm_runtime` for execution simulators and local runs.
- `stable-baselines3` for RL in `scode/` and optimizer training in `circuit_designer/workflow_bridge.py`.
- `cryptography` and `keyring` for secure credential and circuit encryption.
- `matplotlib` for visualization (skip in headless CI).

## Module Coverage and Test Cases

### configuration_management/config_manager.py
- **load_registry basics**: `load_registry()` populates expected keys (e.g., `'hardware'`, `'workflow_policy'`).
- **get_config YAML/JSON**: Package resource fallback and filesystem fallback return dicts.
- **save_config fallback**: On write failure (simulate PermissionError), writes to `~/.qcraft/configs/<file>`.
- **validate_config missing schema**: Returns True when schema not present; uses schema when available.
- **.env API keys**: `load_env()`, `set_api_key()`, `get_api_key()` roundtrip using temp `.env`.

### hardware_abstraction/device_abstraction.py
- **load_selected_device() normalization**: Ensures `'name'`/`'device_name'` present; `'max_qubits'` correct; connectivity keys coerced to ints.
- **list_devices()**: Non-empty for known providers.
- **get_device_info()**: Accepts either `'name'` or `'device_name'`, validates and normalizes.
- **validate_circuit_for_device()**: Rejects circuits exceeding `max_qubits` or with non-native gates.

### runtime/provider_capabilities.py
- **detect_capabilities(ibm)**: Defaults true for mid-circuit, conditional, dynamic.
- **detect_capabilities(other)**: Conservative false defaults unless specified.
- **ProviderCapabilities.as_dict()**: Reflects properties.

### runtime/job_packager.py
- **package structure**: Returns dict with `'provider'`, `'device'`, `'capabilities'`, `'native_job'`, `'metadata'` (includes timestamp). No logical IR leakage beyond `native_job.qcraft_circuit`.

### execution_simulation/execution_simulator.py
- **list_backends()**: Returns list (empty or real) depending on Aer presence; no raise.
- **export_result()**: Supports json/yaml/csv formats. Writing correct keys.
- **get_supported_simulation_options()**: Returns keys derived from device info (`noise_model`, `max_shots`, `native_gates`, `max_qubits`, `gate_error_rates`, `readout_errors`).

### privacy/circuit_encryptor.py
- **encrypt/decrypt (AES-GCM)**: With password provided, roundtrip payload using header, 16B salt, 12B nonce.
- **encrypt/decrypt (Fernet)**: With key provided, roundtrip string/dict.
- **obfuscate/deobfuscate**: `CircuitObfuscator` adds dummy gates and can reverse.

### utils/credential_manager.py
- Tests are isolated with an in-memory stub keyring to avoid mutating the system. Cover:
  - **store/get/delete** roundtrip via stubbed keyring.
  - **get_credential_with_metadata** returns both fields.
  - **fallback env** path exercised if keyring is unavailable (optional).

### provenance/manifest.py
- **manifest structure**: `'version'`, `'timestamp'`, `'metadata'`, `'signature'`, `'signature_alg'`.
- **signature determinism**: For same metadata and fixed timestamp, signature stable.

### code_switcher/code_switcher.py
- **identify_switching_points()**: Flags unsupported gates vs `supported_gates` (e.g., SWAP, T when not listed).
- **select_switching_protocol()**: Selects protocol whose `supported_gates` includes the gate (teleportation for SWAP per `configs/switcher_config.yaml`).
- **apply_code_switching()**: Inserts protocol wrappers correctly.

### logging_results/logging_results_manager.py
- **log_event/log_metric**: Updates internal state; run summaries.
- **store_result/get_result**: Roundtrip and persisted-to-disk JSON.

### scode/* and RL
- Rich coverage exists under `scode/tests/`. Retain as source of truth for RL, mapping, reward engine, and full frontend workflow. Complement with the above unit tests for non-scode modules.

## Integration Tests
- Keep and parameterize `tests/integration/test_end_to_end_workflow.py` for minimal orchestrator run variants (skip heavy deps). Ensure key result fields exist even on failure paths.

## Skips and Marks
- Use `pytest.importorskip('cryptography')` or in-test stubs for crypto and keyring sensitive tests.
- Conditionals for `qiskit` and `stable_baselines3` functionality.

## Coverage Priorities
- Prioritize non-RL modules: config manager, device abstraction, provider capabilities, job packager, provenance, privacy, execution simulator, code switcher, logging manager.

## Open Items
- Add smoke tests for orchestrator policy branches if gaps found in integration test.
- Add optional Qiskit run smoke when dependencies and credentials are available.
