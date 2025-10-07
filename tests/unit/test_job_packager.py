from runtime.job_packager import JobPackager


def test_job_packager_structure():
    device = {'provider_name': 'ibm', 'device_name': 'ibm_fake', 'max_qubits': 5}
    caps = {'mid_circuit_measure': True, 'conditional': True, 'dynamic_circuits': True}
    ft_circuit = {'gates': [{'name': 'X', 'qubits': [0]}]}
    jp = JobPackager(device, caps)
    pkg = jp.package(ft_circuit)
    assert pkg['provider'] == 'ibm'
    assert pkg['device'] == 'ibm_fake'
    assert pkg['capabilities'] == caps
    assert 'instructions' in pkg['native_job']
    assert isinstance(pkg['metadata'].get('timestamp'), float)
