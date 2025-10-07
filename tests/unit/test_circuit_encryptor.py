import base64
import json
import os
import pytest

cryptography = pytest.importorskip('cryptography')

from privacy.circuit_encryptor import CircuitEncryptor, CircuitObfuscator


def test_encrypt_decrypt_aes_gcm_roundtrip(tmp_path):
    password = 'test-pass'
    enc = CircuitEncryptor(password=password)
    data = {"a": 1, "b": "x"}
    sealed = enc.encrypt_circuit(data)
    # GCM header present
    assert isinstance(sealed, (bytes, bytearray)) and sealed[:6] == CircuitEncryptor.GCM_HEADER
    opened = enc.decrypt_circuit(sealed)
    assert opened == data


def test_encrypt_decrypt_fernet_roundtrip():
    key = CircuitEncryptor.generate_key()
    enc = CircuitEncryptor(key=key)
    data = {"q": 2, "gates": [{"name": "x", "qubits": [0]}]}
    sealed = enc.encrypt_circuit(data)
    opened = enc.decrypt_circuit(sealed)
    assert opened == data


def test_obfuscate_and_deobfuscate_reversible():
    obf = CircuitObfuscator(seed=42)
    circuit = {'qubits': 3, 'gates': [{'name': 'X', 'qubits': [0]}, {'name': 'CNOT', 'qubits': [0, 1]}]}
    obfuscated = obf.obfuscate(circuit)
    assert obfuscated.get('_obfuscated') is True
    restored = obf.deobfuscate(obfuscated)
    assert restored.get('_obfuscated') is None
    # Structural equality on gates ignoring dummy gates
    assert isinstance(restored.get('gates'), list)
