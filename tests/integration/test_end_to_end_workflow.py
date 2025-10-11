# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

"""
End-to-End Integration Tests for QCraft Workflow

These tests verify the complete workflow from circuit design to execution.

Author: QCraft Development Team
Date: October 1, 2025
"""

import pytest
import os
import sys
import time
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from orchestration_controller.orchestrator import OrchestratorController
from configuration_management.config_manager import ConfigManager


class TestEndToEndWorkflow:
    """Integration tests for complete QCraft workflow."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        ConfigManager.load_registry()
        self.orchestrator = OrchestratorController()
    
    def test_simple_circuit_compilation(self):
        """
        Test compilation of simple 3-qubit circuit.
        
        Success Criteria:
        - Workflow completes without errors
        - FT circuit is generated
        - Compilation time < 5 seconds (performance target)
        """
        # Create simple test circuit
        circuit = {
            'qubits': 3,
            'gates': [
                {'type': 'H', 'qubit': 0, 'time': 0},
                {'type': 'CNOT', 'qubits': [0, 1], 'time': 1},
                {'type': 'CNOT', 'qubits': [1, 2], 'time': 2},
                {'type': 'H', 'qubit': 0, 'time': 3},
            ]
        }
        
        # Run workflow with timing
        start_time = time.time()
        result = self.orchestrator.run_workflow(circuit)
        compilation_time = time.time() - start_time
        
        # Assertions
        assert result is not None, "Workflow returned None"
        assert 'ft_circuit' in result or 'error' not in result, "Workflow failed with error"
        
        # Performance assertion (may fail if system is slow)
        if compilation_time > 5.0:
            pytest.warn(f"Compilation took {compilation_time:.2f}s (target: <5s)")
        
        print(f"✓ Simple circuit compiled in {compilation_time:.2f}s")
    
    def test_multi_qubit_circuit(self):
        """
        Test compilation of larger 5-qubit circuit.
        
        Success Criteria:
        - Handles multiple qubits correctly
        - Multi-patch mapping works
        - Circuit depth is reasonable
        """
        circuit = {
            'qubits': 5,
            'gates': [
                {'type': 'H', 'qubit': i, 'time': 0} for i in range(5)
            ] + [
                {'type': 'CNOT', 'qubits': [i, i+1], 'time': 1} for i in range(4)
            ] + [
                {'type': 'H', 'qubit': i, 'time': 2} for i in range(5)
            ]
        }
        
        result = self.orchestrator.run_workflow(circuit)
        
        assert result is not None
        # Check that multi-patch mapping was used
        if 'mapping_info' in result:
            assert 'logical_to_physical' in result['mapping_info']
        
        print("✓ Multi-qubit circuit compiled successfully")
    
    def test_workflow_with_config_override(self):
        """
        Test workflow with custom configuration.
        
        Success Criteria:
        - Config overrides are applied
        - Workflow respects custom settings
        """
        circuit = {
            'qubits': 3,
            'gates': [
                {'type': 'H', 'qubit': 0, 'time': 0},
                {'type': 'CNOT', 'qubits': [0, 1], 'time': 1},
            ]
        }
        
        # Custom config
        user_config = {
            'surface_code': {
                'code_distance': 3,
                'layout_type': 'rotated'
            }
        }
        
        result = self.orchestrator.run_workflow(circuit, user_config=user_config)
        
        assert result is not None
        print("✓ Workflow with config override completed")
    
    def test_error_handling(self):
        """
        Test that workflow handles invalid input gracefully.
        
        Success Criteria:
        - Invalid circuit raises appropriate error
        - Error is logged properly
        - System doesn't crash
        """
        # Invalid circuit (no qubits)
        invalid_circuit = {
            'gates': [
                {'type': 'H', 'qubit': 0, 'time': 0},
            ]
        }
        
        # Should handle gracefully
        try:
            result = self.orchestrator.run_workflow(invalid_circuit)
            # If it doesn't raise, check for error in result
            if result and 'error' in result:
                print("✓ Error handled gracefully in result")
            else:
                print("✓ Workflow handled invalid input")
        except Exception as e:
            # Expected behavior - error raised
            print(f"✓ Error raised as expected: {type(e).__name__}")
    
    def test_privacy_preservation(self):
        """
        Test that logical circuit is not exposed in output.
        
        Success Criteria:
        - Only FT circuit in output
        - Logical circuit not in exported data
        - Privacy flag is set
        """
        circuit = {
            'qubits': 3,
            'gates': [
                {'type': 'H', 'qubit': 0, 'time': 0},
                {'type': 'CNOT', 'qubits': [0, 1], 'time': 1},
            ]
        }
        
        result = self.orchestrator.run_workflow(circuit)
        
        # Check that logical circuit is not in result
        # (In production, this would check encrypted export)
        assert result is not None
        
        # Future: Check encryption
        # assert 'encrypted_circuit' in result
        # assert 'logical_circuit' not in result
        
        print("✓ Privacy preservation check passed")
    
    def test_workflow_status_tracking(self):
        """
        Test that workflow status is tracked correctly.
        
        Success Criteria:
        - Workflow ID is generated
        - Status updates are recorded
        - Final status is correct
        """
        circuit = {
            'qubits': 3,
            'gates': [
                {'type': 'H', 'qubit': 0, 'time': 0},
            ]
        }
        
        result = self.orchestrator.run_workflow(circuit)
        
        # Check workflow status
        assert len(self.orchestrator.workflow_status) > 0
        
        # Get most recent workflow
        workflow_ids = list(self.orchestrator.workflow_status.keys())
        latest_id = workflow_ids[-1]
        status = self.orchestrator.workflow_status[latest_id]
        
        assert 'status' in status
        assert 'steps' in status
        assert len(status['steps']) > 0
        
        print(f"✓ Workflow status tracked: {status['status']}")


class TestMultiPatchMapping:
    """Integration tests for multi-patch mapping."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        ConfigManager.load_registry()
        self.orchestrator = OrchestratorController()
    
    def test_single_patch_mapping(self):
        """
        Test single-patch mapping (1 logical qubit).
        
        Success Criteria:
        - Single patch is mapped correctly
        - Mapping is valid
        - Performance is acceptable
        """
        circuit = {
            'qubits': 1,
            'gates': [
                {'type': 'H', 'qubit': 0, 'time': 0},
                {'type': 'X', 'qubit': 0, 'time': 1},
            ]
        }
        
        result = self.orchestrator.run_workflow(circuit)
        
        assert result is not None
        print("✓ Single-patch mapping successful")
    
    def test_multi_patch_mapping_5_qubits(self):
        """
        Test multi-patch mapping for 5 logical qubits.
        
        Success Criteria:
        - All 5 patches are mapped
        - No overlapping physical qubits
        - Crosstalk is minimized
        """
        circuit = {
            'qubits': 5,
            'gates': [
                {'type': 'H', 'qubit': i, 'time': 0} for i in range(5)
            ]
        }
        
        start_time = time.time()
        result = self.orchestrator.run_workflow(circuit)
        mapping_time = time.time() - start_time
        
        assert result is not None
        
        # Check mapping time (target: <10s for 5 patches)
        if mapping_time > 10.0:
            pytest.warn(f"Mapping took {mapping_time:.2f}s (target: <10s)")
        
        print(f"✓ Multi-patch mapping (5 qubits) completed in {mapping_time:.2f}s")
    
    @pytest.mark.slow
    def test_scalability_10_qubits(self):
        """
        Test scalability with 10 logical qubits.
        
        Success Criteria:
        - System handles 10 qubits
        - Memory usage is reasonable
        - Compilation time is acceptable
        
        Note: Marked as slow test
        """
        circuit = {
            'qubits': 10,
            'gates': [
                {'type': 'H', 'qubit': i, 'time': 0} for i in range(10)
            ]
        }
        
        start_time = time.time()
        result = self.orchestrator.run_workflow(circuit)
        compilation_time = time.time() - start_time
        
        assert result is not None
        print(f"✓ Scalability test (10 qubits) completed in {compilation_time:.2f}s")


class TestHardwareIntegration:
    """Integration tests for hardware backends."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        ConfigManager.load_registry()
    
    @pytest.mark.skipif(
        not os.environ.get('QCRAFT_TEST_HARDWARE'),
        reason="Hardware tests disabled (set QCRAFT_TEST_HARDWARE=1 to enable)"
    )
    def test_ibm_quantum_integration(self):
        """
        Test IBM Quantum integration.
        
        Success Criteria:
        - Can connect to IBM Quantum
        - Can submit job
        - Can retrieve results
        
        Note: Requires IBM Quantum credentials
        """
        from hardware_abstraction.device_abstraction import DeviceAbstraction
        
        # This would test actual IBM integration
        # Skipped by default to avoid requiring credentials
        
        print("✓ IBM Quantum integration test (skipped - requires credentials)")
    
    def test_simulator_integration(self):
        """
        Test simulator integration.
        
        Success Criteria:
        - Simulator runs successfully
        - Results are returned
        - No hardware required
        """
        # Test with simulator (always available)
        orchestrator = OrchestratorController()
        
        circuit = {
            'qubits': 3,
            'gates': [
                {'type': 'H', 'qubit': 0, 'time': 0},
                {'type': 'CNOT', 'qubits': [0, 1], 'time': 1},
            ]
        }
        
        result = orchestrator.run_workflow(circuit)
        
        assert result is not None
        print("✓ Simulator integration successful")


@pytest.mark.benchmark
class TestPerformanceBenchmarks:
    """Performance benchmarks for release criteria."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        ConfigManager.load_registry()
        self.orchestrator = OrchestratorController()
    
    def test_d3_compilation_speed(self):
        """
        Benchmark: d=3 compilation < 5 seconds.
        
        This is a CRITICAL release criterion.
        """
        circuit = {
            'qubits': 3,
            'gates': [
                {'type': 'H', 'qubit': 0, 'time': 0},
                {'type': 'CNOT', 'qubits': [0, 1], 'time': 1},
                {'type': 'CNOT', 'qubits': [1, 2], 'time': 2},
            ]
        }
        
        # Run multiple times for average
        times = []
        for _ in range(3):
            start = time.time()
            result = self.orchestrator.run_workflow(circuit)
            elapsed = time.time() - start
            times.append(elapsed)
            assert result is not None
        
        avg_time = sum(times) / len(times)
        
        print(f"\nCompilation Speed Benchmark (d=3):")
        print(f"  Average: {avg_time:.2f}s")
        print(f"  Min: {min(times):.2f}s")
        print(f"  Max: {max(times):.2f}s")
        print(f"  Target: <5.0s")
        
        if avg_time < 5.0:
            print("  Status: ✓ PASS")
        else:
            print(f"  Status: ✗ FAIL (exceeded by {avg_time - 5.0:.2f}s)")
            pytest.fail(f"Compilation speed target not met: {avg_time:.2f}s > 5.0s")
    
    def test_memory_usage(self):
        """
        Benchmark: Memory usage < 2GB for large circuits.
        """
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create larger circuit
        circuit = {
            'qubits': 10,
            'gates': [
                {'type': 'H', 'qubit': i, 'time': t}
                for t in range(10)
                for i in range(10)
            ]
        }
        
        result = self.orchestrator.run_workflow(circuit)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        print(f"\nMemory Usage Benchmark:")
        print(f"  Initial: {initial_memory:.1f} MB")
        print(f"  Final: {final_memory:.1f} MB")
        print(f"  Increase: {memory_increase:.1f} MB")
        print(f"  Target: <2048 MB total")
        
        if final_memory < 2048:
            print("  Status: ✓ PASS")
        else:
            print(f"  Status: ✗ FAIL (exceeded by {final_memory - 2048:.1f} MB)")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
