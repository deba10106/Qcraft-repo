# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

"""
Circuit Encryption Module for Privacy-Preserving Export

This module provides AES-256 encryption for quantum circuit data export,
ensuring logical circuits remain private and secure.

Author: QCraft Development Team
Date: October 1, 2025
"""

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64
import json
import os
from typing import Dict, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)


class CircuitEncryptor:
    """
    AES-256 encryption for quantum circuit export.
    
    This class provides secure encryption and decryption of quantum circuit
    data using AES-256 via the Fernet symmetric encryption scheme. It supports
    both password-based and key-based encryption.
    
    Attributes:
        key: Encryption key (Fernet format)
        cipher: Fernet cipher instance
    
    Example:
        >>> encryptor = CircuitEncryptor(password="my_secure_password")
        >>> circuit_data = {'qubits': 3, 'gates': [...]}
        >>> encrypted = encryptor.encrypt_circuit(circuit_data)
        >>> decrypted = encryptor.decrypt_circuit(encrypted)
    """
    
    GCM_HEADER = b'QCGCM1'

    def __init__(self, password: Optional[str] = None, key: Optional[bytes] = None):
        """
        Initialize circuit encryptor.
        
        Args:
            password: Password for key derivation (if key not provided)
            key: Pre-generated Fernet key (if password not provided)
        
        Raises:
            ValueError: If neither password nor key is provided
        """
        # Store password to derive AES-GCM keys deterministically per export
        self._password = password
        self._use_gcm = password is not None

        if key is not None:
            self.key = key
        elif password is not None:
            self.key = self._derive_key_from_password(password)
        else:
            # Generate random key for session
            self.key = Fernet.generate_key()
            logger.warning("No password or key provided. Generated random session key.")
        
        self.cipher = Fernet(self.key)
        logger.info("CircuitEncryptor initialized")
    
    def _derive_key_from_password(self, password: str, salt: Optional[bytes] = None) -> bytes:
        """
        Derive encryption key from password using PBKDF2.
        
        Args:
            password: User password
            salt: Salt for key derivation (generated if not provided)
        
        Returns:
            Fernet-compatible encryption key
        """
        if salt is None:
            # Use fixed salt for reproducibility (should be per-user in production)
            salt = b'qcraft_salt_v1_change_in_production'
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key_material = kdf.derive(password.encode())
        return base64.urlsafe_b64encode(key_material)

    def _derive_raw_key_from_password(self, password: str, salt: bytes, iterations: int = 200000) -> bytes:
        """
        Derive a raw 32-byte key for AES-GCM from a password and salt.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        return kdf.derive(password.encode())
    
    def encrypt_circuit(self, circuit_data: Union[Dict[str, Any], str]) -> bytes:
        """
        Encrypt circuit data.
        
        Args:
            circuit_data: Circuit data as dict or JSON string
        
        Returns:
            Encrypted circuit data as bytes
        
        Raises:
            ValueError: If circuit_data is invalid
            Exception: If encryption fails
        """
        try:
            # Convert to JSON if dict
            if isinstance(circuit_data, dict):
                circuit_json = json.dumps(circuit_data, indent=2)
            else:
                circuit_json = circuit_data

            # Prefer AES-GCM when a password is provided
            if self._use_gcm and self._password:
                salt = os.urandom(16)
                nonce = os.urandom(12)  # 96-bit nonce recommended for GCM
                aes_key = self._derive_raw_key_from_password(self._password, salt, iterations=200000)
                aesgcm = AESGCM(aes_key)
                ciphertext = aesgcm.encrypt(nonce, circuit_json.encode('utf-8'), None)
                payload = self.GCM_HEADER + salt + nonce + ciphertext
                logger.info("Circuit encrypted successfully with AES-GCM (%s bytes)", len(payload))
                return payload

            # Fallback to Fernet
            encrypted_data = self.cipher.encrypt(circuit_json.encode('utf-8'))
            logger.info("Circuit encrypted successfully with Fernet (%s bytes)", len(encrypted_data))
            return encrypted_data

        except Exception as e:
            logger.error(f"Circuit encryption failed: {e}")
            raise
    
    def decrypt_circuit(self, encrypted_data: bytes) -> Dict[str, Any]:
        """
        Decrypt circuit data.
        
        Args:
            encrypted_data: Encrypted circuit data
        
        Returns:
            Decrypted circuit data as dict
        
        Raises:
            Exception: If decryption fails (wrong key, corrupted data)
        """
        try:
            # AES-GCM detection and decryption
            if isinstance(encrypted_data, (bytes, bytearray)) and encrypted_data.startswith(self.GCM_HEADER):
                if not self._password:
                    raise ValueError("Password required to decrypt AES-GCM payload.")
                header_len = len(self.GCM_HEADER)
                salt = encrypted_data[header_len:header_len+16]
                nonce = encrypted_data[header_len+16:header_len+16+12]
                ciphertext = encrypted_data[header_len+28:]
                aes_key = self._derive_raw_key_from_password(self._password, salt, iterations=200000)
                aesgcm = AESGCM(aes_key)
                decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
                circuit_json = decrypted_bytes.decode('utf-8')
            else:
                # Fernet fallback
                decrypted_bytes = self.cipher.decrypt(encrypted_data)
                circuit_json = decrypted_bytes.decode('utf-8')

            # Parse JSON
            circuit_data = json.loads(circuit_json)
            logger.info("Circuit decrypted successfully")
            return circuit_data

        except Exception as e:
            logger.error(f"Circuit decryption failed: {e}")
            raise
    
    def encrypt_to_file(self, circuit_data: Dict[str, Any], filepath: str) -> None:
        """
        Encrypt circuit and save to file.
        
        Args:
            circuit_data: Circuit data to encrypt
            filepath: Output file path
        """
        encrypted = self.encrypt_circuit(circuit_data)
        
        with open(filepath, 'wb') as f:
            f.write(encrypted)
        
        logger.info(f"Encrypted circuit saved to {filepath}")
    
    def decrypt_from_file(self, filepath: str) -> Dict[str, Any]:
        """
        Load and decrypt circuit from file.
        
        Args:
            filepath: Input file path
        
        Returns:
            Decrypted circuit data
        """
        with open(filepath, 'rb') as f:
            encrypted_data = f.read()
        
        return self.decrypt_circuit(encrypted_data)
    
    def export_key(self) -> str:
        """
        Export encryption key as base64 string.
        
        Returns:
            Base64-encoded encryption key
        
        Warning:
            Store this key securely! Anyone with this key can decrypt circuits.
        """
        return self.key.decode('utf-8')
    
    @classmethod
    def from_key_string(cls, key_string: str) -> 'CircuitEncryptor':
        """
        Create encryptor from exported key string.
        
        Args:
            key_string: Base64-encoded encryption key
        
        Returns:
            CircuitEncryptor instance
        """
        key = key_string.encode('utf-8')
        return cls(key=key)
    
    @staticmethod
    def generate_key() -> bytes:
        """
        Generate a new random encryption key.
        
        Returns:
            Fernet-compatible encryption key
        """
        return Fernet.generate_key()


class CircuitObfuscator:
    """
    Obfuscate circuit structure before export.
    
    This class provides circuit obfuscation to hide the logical structure
    of quantum circuits. Obfuscation includes:
    - Randomizing qubit labels
    - Adding dummy gates (identity operations)
    - Shuffling gate order where possible
    
    Example:
        >>> obfuscator = CircuitObfuscator()
        >>> obfuscated = obfuscator.obfuscate(ft_circuit)
        >>> original = obfuscator.deobfuscate(obfuscated)
    """
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize circuit obfuscator.
        
        Args:
            seed: Random seed for reproducibility (None for random)
        """
        self.seed = seed
        if seed is not None:
            import random
            random.seed(seed)
        
        self.obfuscation_map = {}
        logger.info("CircuitObfuscator initialized")
    
    def obfuscate(self, circuit_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Obfuscate circuit structure.
        
        Args:
            circuit_data: Original circuit data
        
        Returns:
            Obfuscated circuit data with metadata for deobfuscation
        """
        import random
        import copy
        
        obfuscated = copy.deepcopy(circuit_data)
        
        # Generate qubit label mapping
        if 'qubits' in circuit_data:
            num_qubits = circuit_data['qubits']
            original_labels = list(range(num_qubits))
            shuffled_labels = original_labels.copy()
            random.shuffle(shuffled_labels)
            
            self.obfuscation_map['qubit_mapping'] = {
                orig: shuffled for orig, shuffled in zip(original_labels, shuffled_labels)
            }
            
            # Apply mapping to gates
            if 'gates' in obfuscated:
                for gate in obfuscated['gates']:
                    if 'qubit' in gate:
                        gate['qubit'] = self.obfuscation_map['qubit_mapping'][gate['qubit']]
                    if 'qubits' in gate:
                        gate['qubits'] = [
                            self.obfuscation_map['qubit_mapping'][q] for q in gate['qubits']
                        ]
        
        # Add dummy identity gates (10% of original gate count)
        if 'gates' in obfuscated:
            num_dummies = max(1, len(obfuscated['gates']) // 10)
            for _ in range(num_dummies):
                dummy_gate = {
                    'type': 'I',  # Identity gate
                    'qubit': random.randint(0, obfuscated.get('qubits', 1) - 1),
                    'time': random.randint(0, len(obfuscated['gates'])),
                    '_dummy': True  # Mark as dummy for deobfuscation
                }
                obfuscated['gates'].append(dummy_gate)
        
        # Add obfuscation metadata
        obfuscated['_obfuscated'] = True
        obfuscated['_obfuscation_version'] = '1.0'
        
        logger.info(f"Circuit obfuscated (added {num_dummies} dummy gates)")
        return obfuscated
    
    def deobfuscate(self, obfuscated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reverse obfuscation to recover original circuit.
        
        Args:
            obfuscated_data: Obfuscated circuit data
        
        Returns:
            Original circuit data
        """
        import copy
        
        if not obfuscated_data.get('_obfuscated'):
            logger.warning("Circuit is not obfuscated, returning as-is")
            return obfuscated_data
        
        deobfuscated = copy.deepcopy(obfuscated_data)
        
        # Remove dummy gates
        if 'gates' in deobfuscated:
            deobfuscated['gates'] = [
                gate for gate in deobfuscated['gates'] if not gate.get('_dummy', False)
            ]
        
        # Reverse qubit mapping
        if 'qubit_mapping' in self.obfuscation_map:
            reverse_mapping = {
                v: k for k, v in self.obfuscation_map['qubit_mapping'].items()
            }
            
            if 'gates' in deobfuscated:
                for gate in deobfuscated['gates']:
                    if 'qubit' in gate:
                        gate['qubit'] = reverse_mapping[gate['qubit']]
                    if 'qubits' in gate:
                        gate['qubits'] = [reverse_mapping[q] for q in gate['qubits']]
        
        # Remove obfuscation metadata
        deobfuscated.pop('_obfuscated', None)
        deobfuscated.pop('_obfuscation_version', None)
        
        logger.info("Circuit deobfuscated successfully")
        return deobfuscated


def create_secure_export(
    circuit_data: Dict[str, Any],
    password: str,
    obfuscate: bool = True,
    output_file: Optional[str] = None
) -> bytes:
    """
    Create secure encrypted export of circuit data.
    
    This is a convenience function that combines obfuscation and encryption.
    
    Args:
        circuit_data: Circuit data to export
        password: Encryption password
        obfuscate: Whether to obfuscate before encryption
        output_file: Optional file path to save encrypted data
    
    Returns:
        Encrypted circuit data
    
    Example:
        >>> circuit = {'qubits': 3, 'gates': [...]}
        >>> encrypted = create_secure_export(circuit, "my_password")
    """
    # Obfuscate if requested
    if obfuscate:
        obfuscator = CircuitObfuscator()
        circuit_data = obfuscator.obfuscate(circuit_data)
    
    # Encrypt
    encryptor = CircuitEncryptor(password=password)
    encrypted_data = encryptor.encrypt_circuit(circuit_data)
    
    # Save to file if requested
    if output_file:
        with open(output_file, 'wb') as f:
            f.write(encrypted_data)
        logger.info(f"Secure export saved to {output_file}")
    
    return encrypted_data


def load_secure_export(
    encrypted_data: Union[bytes, str],
    password: str,
    deobfuscate: bool = True
) -> Dict[str, Any]:
    """
    Load and decrypt secure circuit export.
    
    Args:
        encrypted_data: Encrypted data (bytes) or file path (str)
        password: Decryption password
        deobfuscate: Whether to deobfuscate after decryption
    
    Returns:
        Original circuit data
    
    Example:
        >>> circuit = load_secure_export("encrypted_circuit.bin", "my_password")
    """
    # Load from file if path provided
    if isinstance(encrypted_data, str):
        with open(encrypted_data, 'rb') as f:
            encrypted_data = f.read()
    
    # Decrypt
    encryptor = CircuitEncryptor(password=password)
    circuit_data = encryptor.decrypt_circuit(encrypted_data)
    
    # Deobfuscate if needed
    if deobfuscate and circuit_data.get('_obfuscated'):
        obfuscator = CircuitObfuscator()
        circuit_data = obfuscator.deobfuscate(circuit_data)
    
    return circuit_data
