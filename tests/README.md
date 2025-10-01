# QCraft Test Suite

This directory contains the comprehensive test suite for QCraft.

## Test Structure

```
tests/
├── integration/          # Integration tests (end-to-end workflows)
├── unit/                # Unit tests (individual components)
├── benchmarks/          # Performance benchmarks
├── fixtures/            # Test fixtures and data
└── README.md           # This file
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Integration tests only
pytest -m integration

# Unit tests only
pytest -m unit

# Performance benchmarks
pytest -m benchmark

# Exclude slow tests
pytest -m "not slow"
```

### Run Specific Test Files

```bash
# End-to-end workflow tests
pytest tests/integration/test_end_to_end_workflow.py

# With verbose output
pytest tests/integration/test_end_to_end_workflow.py -v -s
```

## Test Markers

Tests are marked with the following markers:

- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.benchmark` - Performance benchmarks
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.hardware` - Tests requiring hardware access

## Performance Benchmarks

Performance benchmarks verify release criteria:

### Critical Benchmarks

1. **Compilation Speed** (d=3): Target < 5 seconds
   ```bash
   pytest tests/integration/test_end_to_end_workflow.py::TestPerformanceBenchmarks::test_d3_compilation_speed
   ```

2. **Memory Usage**: Target < 2GB for 20 logical qubits
   ```bash
   pytest tests/integration/test_end_to_end_workflow.py::TestPerformanceBenchmarks::test_memory_usage
   ```

## Hardware Tests

Hardware tests are disabled by default. To enable:

```bash
# Set environment variable
export QCRAFT_TEST_HARDWARE=1

# Run hardware tests
pytest -m hardware
```

**Note:** Hardware tests require valid credentials for quantum providers.

## Test Coverage

To generate coverage reports (requires `pytest-cov`):

```bash
# Install pytest-cov
pip install pytest-cov

# Run with coverage
pytest --cov=. --cov-report=html --cov-report=term-missing

# View HTML report
open htmlcov/index.html
```

## Writing Tests

### Integration Test Template

```python
import pytest
from orchestration_controller.orchestrator import OrchestratorController

class TestMyFeature:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        self.orchestrator = OrchestratorController()
    
    def test_my_feature(self):
        """Test description."""
        # Arrange
        circuit = {...}
        
        # Act
        result = self.orchestrator.run_workflow(circuit)
        
        # Assert
        assert result is not None
```

### Unit Test Template

```python
import pytest
from my_module import MyClass

class TestMyClass:
    def test_method(self):
        """Test description."""
        obj = MyClass()
        result = obj.method()
        assert result == expected_value
```

## Continuous Integration

Tests are run automatically on:
- Pull requests
- Commits to main branch
- Nightly builds

### CI Configuration

See `.github/workflows/tests.yml` for CI configuration.

## Test Data

Test fixtures and data are stored in `tests/fixtures/`:

- `test_circuits/` - Sample quantum circuits
- `test_configs/` - Test configuration files
- `test_devices/` - Mock device specifications

## Troubleshooting

### Tests Fail with Import Errors

Ensure QCraft is installed in development mode:

```bash
pip install -e .
```

### Tests Timeout

Increase timeout in `pytest.ini` or skip slow tests:

```bash
pytest -m "not slow"
```

### Hardware Tests Fail

1. Check credentials are set correctly
2. Verify network connectivity
3. Check provider service status

## Contributing

When adding new features:

1. Write tests first (TDD)
2. Ensure all tests pass
3. Add integration tests for new workflows
4. Update this README if needed

## Test Metrics

Current test coverage: TBD

Target coverage: > 80%

## Contact

For test-related questions, contact the QCraft development team.
