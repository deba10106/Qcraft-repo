"""
Secure Credential Management for QCraft

This module provides secure storage and retrieval of API credentials
using system keyring and encryption.

Author: QCraft Development Team
Date: October 1, 2025
"""

from cryptography.fernet import Fernet
import keyring
import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class CredentialManager:
    """
    Secure credential storage using system keyring and encryption.
    
    This class provides secure storage for API credentials (IBM Quantum,
    IonQ, Rigetti) using the system keyring for key storage and Fernet
    encryption for credential data.
    
    Attributes:
        service_name: Service identifier for keyring
        key: Encryption key (stored in system keyring)
        cipher: Fernet cipher instance
    
    Example:
        >>> cred_mgr = CredentialManager()
        >>> cred_mgr.store_credential("ibm_quantum", "my_api_token")
        >>> token = cred_mgr.get_credential("ibm_quantum")
    """
    
    SERVICE_NAME = "qcraft"
    KEY_NAME = "encryption_key"
    
    def __init__(self):
        """Initialize credential manager with system keyring."""
        self.service_name = self.SERVICE_NAME
        self.key = self._get_or_create_key()
        self.cipher = Fernet(self.key)
        logger.info("CredentialManager initialized")
    
    def _get_or_create_key(self) -> bytes:
        """
        Get encryption key from system keyring or create new one.
        
        Returns:
            Fernet-compatible encryption key
        """
        try:
            # Try to get existing key
            key_str = keyring.get_password(self.service_name, self.KEY_NAME)
            
            if key_str is None:
                # Generate new key
                key = Fernet.generate_key()
                key_str = key.decode('utf-8')
                
                # Store in keyring
                keyring.set_password(self.service_name, self.KEY_NAME, key_str)
                logger.info("Generated new encryption key and stored in system keyring")
            else:
                key = key_str.encode('utf-8')
                logger.info("Retrieved encryption key from system keyring")
            
            return key
            
        except Exception as e:
            logger.error(f"Failed to access system keyring: {e}")
            logger.warning("Falling back to environment variable for encryption key")
            
            # Fallback to environment variable
            key_str = os.environ.get('QCRAFT_ENCRYPTION_KEY')
            if key_str is None:
                # Generate and warn
                key = Fernet.generate_key()
                logger.warning(
                    "No encryption key found. Generated temporary key. "
                    "Set QCRAFT_ENCRYPTION_KEY environment variable for persistence."
                )
                return key
            
            return key_str.encode('utf-8')
    
    def store_credential(
        self,
        service: str,
        credential: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Store encrypted credential in system keyring.
        
        Args:
            service: Service identifier (e.g., 'ibm_quantum', 'ionq', 'rigetti')
            credential: Credential string (API key, token, etc.)
            metadata: Optional metadata (username, endpoint, etc.)
        
        Example:
            >>> cred_mgr.store_credential(
            ...     "ibm_quantum",
            ...     "my_api_token",
            ...     {"username": "user@example.com", "instance": "ibm-q/open/main"}
            ... )
        """
        try:
            # Create credential object
            cred_data = {
                'credential': credential,
                'metadata': metadata or {}
            }
            
            # Encrypt
            cred_json = json.dumps(cred_data)
            encrypted = self.cipher.encrypt(cred_json.encode('utf-8'))
            encrypted_str = encrypted.decode('utf-8')
            
            # Store in keyring
            keyring.set_password(self.service_name, service, encrypted_str)
            
            logger.info(f"Stored encrypted credential for service: {service}")
            
        except Exception as e:
            logger.error(f"Failed to store credential for {service}: {e}")
            raise
    
    def get_credential(self, service: str) -> Optional[str]:
        """
        Retrieve and decrypt credential from system keyring.
        
        Args:
            service: Service identifier
        
        Returns:
            Decrypted credential string, or None if not found
        
        Raises:
            ValueError: If credential not found
            Exception: If decryption fails
        
        Example:
            >>> token = cred_mgr.get_credential("ibm_quantum")
        """
        try:
            # Retrieve from keyring
            encrypted_str = keyring.get_password(self.service_name, service)
            
            if encrypted_str is None:
                logger.warning(f"No credential found for service: {service}")
                return None
            
            # Decrypt
            encrypted = encrypted_str.encode('utf-8')
            decrypted = self.cipher.decrypt(encrypted)
            cred_data = json.loads(decrypted.decode('utf-8'))
            
            logger.info(f"Retrieved credential for service: {service}")
            return cred_data['credential']
            
        except Exception as e:
            logger.error(f"Failed to retrieve credential for {service}: {e}")
            raise
    
    def get_credential_with_metadata(self, service: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve credential and metadata.
        
        Args:
            service: Service identifier
        
        Returns:
            Dict with 'credential' and 'metadata' keys, or None if not found
        """
        try:
            encrypted_str = keyring.get_password(self.service_name, service)
            
            if encrypted_str is None:
                return None
            
            encrypted = encrypted_str.encode('utf-8')
            decrypted = self.cipher.decrypt(encrypted)
            cred_data = json.loads(decrypted.decode('utf-8'))
            
            return cred_data
            
        except Exception as e:
            logger.error(f"Failed to retrieve credential with metadata for {service}: {e}")
            raise
    
    def delete_credential(self, service: str) -> None:
        """
        Delete credential from system keyring.
        
        Args:
            service: Service identifier
        """
        try:
            keyring.delete_password(self.service_name, service)
            logger.info(f"Deleted credential for service: {service}")
            
        except keyring.errors.PasswordDeleteError:
            logger.warning(f"No credential found to delete for service: {service}")
        except Exception as e:
            logger.error(f"Failed to delete credential for {service}: {e}")
            raise
    
    def list_services(self) -> list:
        """
        List all services with stored credentials.
        
        Note: This is a best-effort method. Not all keyring backends
        support listing credentials.
        
        Returns:
            List of service identifiers
        """
        # This is backend-dependent and may not work on all systems
        logger.warning("list_services() is not reliably supported across all keyring backends")
        return []
    
    def update_credential(
        self,
        service: str,
        credential: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update existing credential or metadata.
        
        Args:
            service: Service identifier
            credential: New credential (None to keep existing)
            metadata: New metadata (None to keep existing)
        """
        try:
            # Get existing data
            existing = self.get_credential_with_metadata(service)
            
            if existing is None:
                raise ValueError(f"No existing credential found for service: {service}")
            
            # Update fields
            if credential is not None:
                existing['credential'] = credential
            if metadata is not None:
                existing['metadata'].update(metadata)
            
            # Store updated data
            self.store_credential(
                service,
                existing['credential'],
                existing['metadata']
            )
            
            logger.info(f"Updated credential for service: {service}")
            
        except Exception as e:
            logger.error(f"Failed to update credential for {service}: {e}")
            raise


class ConfigCredentialLoader:
    """
    Load credentials from config files with fallback to CredentialManager.
    
    This class provides a unified interface for loading credentials from
    either config files (for development) or secure storage (for production).
    
    Example:
        >>> loader = ConfigCredentialLoader()
        >>> token = loader.get_credential("ibm_quantum", config_path="configs/hardware.json")
    """
    
    def __init__(self, use_secure_storage: bool = True):
        """
        Initialize credential loader.
        
        Args:
            use_secure_storage: Whether to use CredentialManager (True) or
                                config files only (False)
        """
        self.use_secure_storage = use_secure_storage
        if use_secure_storage:
            self.cred_mgr = CredentialManager()
        else:
            self.cred_mgr = None
        
        logger.info(f"ConfigCredentialLoader initialized (secure_storage={use_secure_storage})")
    
    def get_credential(
        self,
        service: str,
        config_path: Optional[str] = None,
        config_key: Optional[str] = None
    ) -> Optional[str]:
        """
        Get credential with fallback logic.
        
        Priority:
        1. CredentialManager (if enabled)
        2. Config file (if path provided)
        3. Environment variable
        
        Args:
            service: Service identifier
            config_path: Optional path to config file
            config_key: Optional key in config file (defaults to service name)
        
        Returns:
            Credential string or None
        """
        # Try secure storage first
        if self.use_secure_storage and self.cred_mgr:
            try:
                cred = self.cred_mgr.get_credential(service)
                if cred is not None:
                    logger.info(f"Loaded credential for {service} from secure storage")
                    return cred
            except Exception as e:
                logger.warning(f"Failed to load from secure storage: {e}")
        
        # Try config file
        if config_path:
            try:
                with open(config_path, 'r') as f:
                    import yaml
                    config = yaml.safe_load(f)
                
                key = config_key or service
                cred = config.get(key)
                
                if cred:
                    logger.info(f"Loaded credential for {service} from config file")
                    return cred
                    
            except Exception as e:
                logger.warning(f"Failed to load from config file: {e}")
        
        # Try environment variable
        env_var = f"QCRAFT_{service.upper()}_CREDENTIAL"
        cred = os.environ.get(env_var)
        
        if cred:
            logger.info(f"Loaded credential for {service} from environment variable")
            return cred
        
        logger.warning(f"No credential found for service: {service}")
        return None
    
    def migrate_from_config(self, config_path: str, service_mapping: Dict[str, str]) -> None:
        """
        Migrate credentials from config file to secure storage.
        
        Args:
            config_path: Path to config file
            service_mapping: Dict mapping config keys to service names
        
        Example:
            >>> loader.migrate_from_config(
            ...     "configs/hardware.json",
            ...     {"ibm_token": "ibm_quantum", "ionq_api_key": "ionq"}
            ... )
        """
        if not self.use_secure_storage:
            raise RuntimeError("Secure storage is disabled")
        
        try:
            with open(config_path, 'r') as f:
                import yaml
                config = yaml.safe_load(f)
            
            for config_key, service in service_mapping.items():
                cred = config.get(config_key)
                if cred:
                    self.cred_mgr.store_credential(service, cred)
                    logger.info(f"Migrated credential for {service}")
            
            logger.info(f"Migration complete from {config_path}")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise


# Convenience functions
def store_ibm_quantum_credentials(token: str, instance: Optional[str] = None) -> None:
    """Store IBM Quantum credentials."""
    cred_mgr = CredentialManager()
    metadata = {'instance': instance} if instance else {}
    cred_mgr.store_credential('ibm_quantum', token, metadata)


def store_ionq_credentials(api_key: str) -> None:
    """Store IonQ credentials."""
    cred_mgr = CredentialManager()
    cred_mgr.store_credential('ionq', api_key)


def store_rigetti_credentials(api_key: str, user_id: Optional[str] = None) -> None:
    """Store Rigetti credentials."""
    cred_mgr = CredentialManager()
    metadata = {'user_id': user_id} if user_id else {}
    cred_mgr.store_credential('rigetti', api_key, metadata)


def get_credentials(service: str) -> Optional[str]:
    """Get credentials for a service."""
    cred_mgr = CredentialManager()
    return cred_mgr.get_credential(service)
