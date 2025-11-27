"""
Secure Secrets Manager - Sistema seguro y unificado de gestión de secretos
Soporta múltiples proveedores: Google Secret Manager, AWS, Azure, Local
Implementa rotación automática, caché seguro y auditoría
"""

import os
import json
import base64
import hashlib
import secrets
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import asyncio
from functools import lru_cache
from core.safe_serialization import safe_dumps, safe_loads, safe_dumps_bytes, safe_loads_bytes

# Import cloud providers conditionally
try:
    from google.cloud import secretmanager
    from google.api_core import exceptions as gcp_exceptions
    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False

try:
    import boto3
    from botocore.exceptions import ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

try:
    from azure.keyvault.secrets import SecretClient
    from azure.identity import DefaultAzureCredential
    from azure.core.exceptions import AzureError
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class SecretMetadata:
    """Metadata for a secret"""
    name: str
    version: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    rotation_schedule: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    last_rotated: Optional[datetime] = None


@dataclass
class SecureCache:
    """Secure in-memory cache for secrets"""
    
    def __init__(self, ttl: int = 300, encryption_key: Optional[bytes] = None):
        self.ttl = ttl  # Time to live in seconds
        self.cache: Dict[str, Tuple[Any, datetime]] = {}
        self.access_log: List[Tuple[str, datetime]] = []
        
        # Initialize encryption
        if encryption_key:
            self.cipher = Fernet(encryption_key)
        else:
            self.cipher = Fernet(Fernet.generate_key())
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with TTL check"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                self.access_log.append((key, datetime.now()))
                # Decrypt value
                if isinstance(value, bytes):
                    try:
                        decrypted = self.cipher.decrypt(value)
                        return safe_loads_bytes(decrypted)
                    except:
                        return value
                return value
            else:
                # Expired, remove from cache
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Set value in cache with encryption"""
        # Encrypt value
        try:
            serialized = safe_dumps_bytes(value)
            encrypted = self.cipher.encrypt(serialized)
            self.cache[key] = (encrypted, datetime.now())
        except:
            # If encryption fails, store as-is (for non-serializable objects)
            self.cache[key] = (value, datetime.now())
    
    def clear(self):
        """Clear all cached values"""
        self.cache.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'size': len(self.cache),
            'ttl': self.ttl,
            'total_accesses': len(self.access_log),
            'keys': list(self.cache.keys())
        }


class BaseSecretsProvider(ABC):
    """Abstract base class for secrets providers"""
    
    @abstractmethod
    async def get_secret(self, secret_id: str, version: Optional[str] = None) -> Optional[str]:
        """Get a secret value"""
        pass
    
    @abstractmethod
    async def set_secret(self, secret_id: str, value: str, metadata: Optional[Dict] = None) -> bool:
        """Set a secret value"""
        pass
    
    @abstractmethod
    async def delete_secret(self, secret_id: str) -> bool:
        """Delete a secret"""
        pass
    
    @abstractmethod
    async def list_secrets(self) -> List[str]:
        """List all available secrets"""
        pass
    
    @abstractmethod
    async def rotate_secret(self, secret_id: str, new_value: str) -> bool:
        """Rotate a secret to a new value"""
        pass


class GoogleSecretManagerProvider(BaseSecretsProvider):
    """Google Secret Manager provider implementation"""
    
    def __init__(self, project_id: str):
        if not GCP_AVAILABLE:
            raise ImportError("google-cloud-secret-manager not installed")
        
        self.project_id = project_id
        self.client = secretmanager.SecretManagerServiceClient()
        self.parent = f"projects/{project_id}"
    
    async def get_secret(self, secret_id: str, version: Optional[str] = None) -> Optional[str]:
        """Get secret from Google Secret Manager"""
        try:
            if version:
                name = f"{self.parent}/secrets/{secret_id}/versions/{version}"
            else:
                name = f"{self.parent}/secrets/{secret_id}/versions/latest"
            
            response = await asyncio.to_thread(
                self.client.access_secret_version,
                request={"name": name}
            )
            
            return response.payload.data.decode("UTF-8")
        except gcp_exceptions.NotFound:
            logger.warning(f"Secret {secret_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting secret {secret_id}: {e}")
            return None
    
    async def set_secret(self, secret_id: str, value: str, metadata: Optional[Dict] = None) -> bool:
        """Create or update secret in Google Secret Manager"""
        try:
            # Try to create the secret
            try:
                secret = await asyncio.to_thread(
                    self.client.create_secret,
                    request={
                        "parent": self.parent,
                        "secret_id": secret_id,
                        "secret": {
                            "replication": {"automatic": {}},
                            "labels": metadata or {}
                        }
                    }
                )
            except gcp_exceptions.AlreadyExists:
                # Secret already exists, that's fine
                pass
            
            # Add the secret version
            parent = f"{self.parent}/secrets/{secret_id}"
            await asyncio.to_thread(
                self.client.add_secret_version,
                request={
                    "parent": parent,
                    "payload": {"data": value.encode("UTF-8")}
                }
            )
            
            return True
        except Exception as e:
            logger.error(f"Error setting secret {secret_id}: {e}")
            return False
    
    async def delete_secret(self, secret_id: str) -> bool:
        """Delete secret from Google Secret Manager"""
        try:
            name = f"{self.parent}/secrets/{secret_id}"
            await asyncio.to_thread(
                self.client.delete_secret,
                request={"name": name}
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting secret {secret_id}: {e}")
            return False
    
    async def list_secrets(self) -> List[str]:
        """List all secrets in the project"""
        try:
            secrets = []
            request = {"parent": self.parent}
            
            page_result = await asyncio.to_thread(
                self.client.list_secrets,
                request=request
            )
            
            for secret in page_result:
                secret_name = secret.name.split('/')[-1]
                secrets.append(secret_name)
            
            return secrets
        except Exception as e:
            logger.error(f"Error listing secrets: {e}")
            return []
    
    async def rotate_secret(self, secret_id: str, new_value: str) -> bool:
        """Rotate a secret by adding a new version"""
        return await self.set_secret(secret_id, new_value)


class AWSSecretsManagerProvider(BaseSecretsProvider):
    """AWS Secrets Manager provider implementation"""
    
    def __init__(self, region_name: str = 'us-east-1'):
        if not AWS_AVAILABLE:
            raise ImportError("boto3 not installed")
        
        self.client = boto3.client('secretsmanager', region_name=region_name)
        self.region = region_name
    
    async def get_secret(self, secret_id: str, version: Optional[str] = None) -> Optional[str]:
        """Get secret from AWS Secrets Manager"""
        try:
            kwargs = {'SecretId': secret_id}
            if version:
                kwargs['VersionId'] = version
            
            response = await asyncio.to_thread(
                self.client.get_secret_value,
                **kwargs
            )
            
            if 'SecretString' in response:
                return response['SecretString']
            else:
                # Binary secret
                return base64.b64decode(response['SecretBinary']).decode('utf-8')
        except ClientError as e:
            logger.error(f"Error getting secret {secret_id}: {e}")
            return None
    
    async def set_secret(self, secret_id: str, value: str, metadata: Optional[Dict] = None) -> bool:
        """Create or update secret in AWS Secrets Manager"""
        try:
            # Try to create the secret
            try:
                await asyncio.to_thread(
                    self.client.create_secret,
                    Name=secret_id,
                    SecretString=value,
                    Tags=[{'Key': k, 'Value': v} for k, v in (metadata or {}).items()]
                )
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceExistsException':
                    # Update existing secret
                    await asyncio.to_thread(
                        self.client.update_secret,
                        SecretId=secret_id,
                        SecretString=value
                    )
                else:
                    raise
            
            return True
        except Exception as e:
            logger.error(f"Error setting secret {secret_id}: {e}")
            return False
    
    async def delete_secret(self, secret_id: str) -> bool:
        """Delete secret from AWS Secrets Manager"""
        try:
            await asyncio.to_thread(
                self.client.delete_secret,
                SecretId=secret_id,
                ForceDeleteWithoutRecovery=True
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting secret {secret_id}: {e}")
            return False
    
    async def list_secrets(self) -> List[str]:
        """List all secrets"""
        try:
            secrets = []
            paginator = self.client.get_paginator('list_secrets')
            
            async for page in asyncio.to_thread(paginator.paginate):
                for secret in page.get('SecretList', []):
                    secrets.append(secret['Name'])
            
            return secrets
        except Exception as e:
            logger.error(f"Error listing secrets: {e}")
            return []
    
    async def rotate_secret(self, secret_id: str, new_value: str) -> bool:
        """Rotate a secret"""
        return await self.set_secret(secret_id, new_value)


class LocalSecretsProvider(BaseSecretsProvider):
    """Local file-based secrets provider with encryption"""
    
    def __init__(self, secrets_dir: str = ".secrets", master_password: Optional[str] = None):
        self.secrets_dir = Path(secrets_dir)
        self.secrets_dir.mkdir(exist_ok=True, mode=0o700)
        
        # Initialize encryption
        if master_password:
            kdf = PBKDF2(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'nubem_salt_v1',  # In production, use random salt
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
        else:
            key = Fernet.generate_key()
        
        self.cipher = Fernet(key)
        self.metadata_file = self.secrets_dir / "metadata.json"
        self._load_metadata()
    
    def _load_metadata(self):
        """Load metadata from file"""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {}
    
    def _save_metadata(self):
        """Save metadata to file"""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2, default=str)
    
    async def get_secret(self, secret_id: str, version: Optional[str] = None) -> Optional[str]:
        """Get secret from local encrypted file"""
        try:
            secret_file = self.secrets_dir / f"{secret_id}.enc"
            if not secret_file.exists():
                return None
            
            with open(secret_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            secret_data = json.loads(decrypted_data.decode())
            
            # Update access metadata
            if secret_id in self.metadata:
                self.metadata[secret_id]['access_count'] += 1
                self.metadata[secret_id]['last_accessed'] = datetime.now().isoformat()
                self._save_metadata()
            
            return secret_data.get('value')
        except Exception as e:
            logger.error(f"Error getting local secret {secret_id}: {e}")
            return None
    
    async def set_secret(self, secret_id: str, value: str, metadata: Optional[Dict] = None) -> bool:
        """Set secret in local encrypted file"""
        try:
            secret_data = {
                'value': value,
                'created_at': datetime.now().isoformat(),
                'metadata': metadata or {}
            }
            
            encrypted_data = self.cipher.encrypt(
                json.dumps(secret_data).encode()
            )
            
            secret_file = self.secrets_dir / f"{secret_id}.enc"
            with open(secret_file, 'wb') as f:
                f.write(encrypted_data)
            
            # Set file permissions to be readable only by owner
            os.chmod(secret_file, 0o600)
            
            # Update metadata
            self.metadata[secret_id] = {
                'created_at': datetime.now().isoformat(),
                'tags': metadata or {},
                'access_count': 0
            }
            self._save_metadata()
            
            return True
        except Exception as e:
            logger.error(f"Error setting local secret {secret_id}: {e}")
            return False
    
    async def delete_secret(self, secret_id: str) -> bool:
        """Delete local secret file"""
        try:
            secret_file = self.secrets_dir / f"{secret_id}.enc"
            if secret_file.exists():
                secret_file.unlink()
            
            if secret_id in self.metadata:
                del self.metadata[secret_id]
                self._save_metadata()
            
            return True
        except Exception as e:
            logger.error(f"Error deleting local secret {secret_id}: {e}")
            return False
    
    async def list_secrets(self) -> List[str]:
        """List all local secrets"""
        try:
            secrets = []
            for file in self.secrets_dir.glob("*.enc"):
                secret_name = file.stem
                secrets.append(secret_name)
            return secrets
        except Exception as e:
            logger.error(f"Error listing local secrets: {e}")
            return []
    
    async def rotate_secret(self, secret_id: str, new_value: str) -> bool:
        """Rotate a local secret"""
        # Backup old secret
        old_value = await self.get_secret(secret_id)
        if old_value:
            backup_id = f"{secret_id}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            await self.set_secret(backup_id, old_value)
        
        # Set new value
        success = await self.set_secret(secret_id, new_value)
        
        if success and secret_id in self.metadata:
            self.metadata[secret_id]['last_rotated'] = datetime.now().isoformat()
            self._save_metadata()
        
        return success


class SecureSecretsManager:
    """
    Unified secrets manager with multi-provider support,
    automatic rotation, caching, and audit logging
    """
    
    def __init__(self, provider: Optional[str] = None, config: Optional[Dict] = None):
        self.config = config or {}
        self.provider = self._initialize_provider(provider)
        self.cache = SecureCache(ttl=self.config.get('cache_ttl', 300))
        self.rotation_schedules: Dict[str, str] = {}
        self.audit_log: List[Dict] = []
        self._rotation_task = None
    
    def _initialize_provider(self, provider: Optional[str]) -> BaseSecretsProvider:
        """Initialize the appropriate secrets provider"""
        if provider == 'gcp' or (not provider and os.getenv('GOOGLE_CLOUD_PROJECT')):
            project_id = self.config.get('gcp_project') or os.getenv('GOOGLE_CLOUD_PROJECT')
            if project_id and GCP_AVAILABLE:
                logger.info(f"Using Google Secret Manager for project: {project_id}")
                return GoogleSecretManagerProvider(project_id)
        
        if provider == 'aws' or (not provider and os.getenv('AWS_REGION')):
            region = self.config.get('aws_region') or os.getenv('AWS_REGION', 'us-east-1')
            if AWS_AVAILABLE:
                logger.info(f"Using AWS Secrets Manager in region: {region}")
                return AWSSecretsManagerProvider(region)
        
        if provider == 'azure' or (not provider and os.getenv('AZURE_TENANT_ID')):
            if AZURE_AVAILABLE:
                logger.info("Using Azure Key Vault")
                # Azure implementation would go here
                pass
        
        # Fallback to local provider
        logger.info("Using local encrypted secrets provider")
        return LocalSecretsProvider(
            secrets_dir=self.config.get('local_dir', '.secrets'),
            master_password=self.config.get('master_password')
        )
    
    async def get_secret(self, secret_id: str, use_cache: bool = True) -> Optional[str]:
        """
        Get a secret with caching and audit logging
        
        Args:
            secret_id: The secret identifier
            use_cache: Whether to use cache
        
        Returns:
            The secret value or None if not found
        """
        # Check cache first
        if use_cache:
            cached_value = self.cache.get(secret_id)
            if cached_value is not None:
                self._log_access(secret_id, 'cache_hit')
                return cached_value
        
        # Get from provider
        value = await self.provider.get_secret(secret_id)
        
        if value is not None:
            # Cache the value
            if use_cache:
                self.cache.set(secret_id, value)
            
            self._log_access(secret_id, 'provider_fetch')
        else:
            self._log_access(secret_id, 'not_found')
        
        return value
    
    async def set_secret(
        self, 
        secret_id: str, 
        value: str,
        metadata: Optional[Dict] = None,
        rotation_schedule: Optional[str] = None
    ) -> bool:
        """
        Set a secret with optional rotation schedule
        
        Args:
            secret_id: The secret identifier
            value: The secret value
            metadata: Optional metadata
            rotation_schedule: Cron expression for rotation (e.g., "0 0 * * 0" for weekly)
        
        Returns:
            True if successful
        """
        success = await self.provider.set_secret(secret_id, value, metadata)
        
        if success:
            # Clear cache for this secret
            self.cache.set(secret_id, value)
            
            # Set rotation schedule if provided
            if rotation_schedule:
                self.rotation_schedules[secret_id] = rotation_schedule
            
            self._log_access(secret_id, 'set')
        
        return success
    
    async def rotate_secret(self, secret_id: str, new_value: Optional[str] = None) -> bool:
        """
        Rotate a secret to a new value
        
        Args:
            secret_id: The secret identifier
            new_value: New value (if None, generates a secure random value)
        
        Returns:
            True if successful
        """
        if new_value is None:
            # Generate secure random value
            new_value = secrets.token_urlsafe(32)
        
        success = await self.provider.rotate_secret(secret_id, new_value)
        
        if success:
            # Clear cache
            self.cache.set(secret_id, new_value)
            self._log_access(secret_id, 'rotated')
            
            # Notify rotation (could send alerts here)
            await self._notify_rotation(secret_id)
        
        return success
    
    async def delete_secret(self, secret_id: str) -> bool:
        """Delete a secret"""
        success = await self.provider.delete_secret(secret_id)
        
        if success:
            # Clear from cache
            if secret_id in self.cache.cache:
                del self.cache.cache[secret_id]
            
            # Remove rotation schedule
            if secret_id in self.rotation_schedules:
                del self.rotation_schedules[secret_id]
            
            self._log_access(secret_id, 'deleted')
        
        return success
    
    async def list_secrets(self) -> List[str]:
        """List all available secrets"""
        return await self.provider.list_secrets()
    
    async def get_api_keys(self) -> Dict[str, Optional[str]]:
        """
        Get all API keys for LLM providers
        
        Returns:
            Dictionary of provider -> API key
        """
        api_keys = {}
        
        # Standard API key names
        key_mappings = {
            'openai': ['openai-api-key', 'OPENAI_API_KEY'],
            'anthropic': ['anthropic-api-key', 'ANTHROPIC_API_KEY', 'CLAUDE_API_KEY'],
            'gemini': ['gemini-api-key', 'GEMINI_API_KEY', 'GOOGLE_API_KEY'],
            'groq': ['groq-api-key', 'GROQ_API_KEY'],
            'together': ['together-api-key', 'TOGETHER_API_KEY']
        }
        
        for provider, possible_keys in key_mappings.items():
            for key_name in possible_keys:
                # Try secret manager first
                value = await self.get_secret(key_name)
                if value:
                    api_keys[provider] = value
                    break
                
                # Fallback to environment variable
                env_value = os.getenv(key_name)
                if env_value:
                    api_keys[provider] = env_value
                    break
        
        return api_keys
    
    async def start_rotation_scheduler(self):
        """Start automatic rotation scheduler"""
        if self._rotation_task is None:
            self._rotation_task = asyncio.create_task(self._rotation_loop())
            logger.info("Started automatic rotation scheduler")
    
    async def stop_rotation_scheduler(self):
        """Stop automatic rotation scheduler"""
        if self._rotation_task:
            self._rotation_task.cancel()
            try:
                await self._rotation_task
            except asyncio.CancelledError:
                pass
            self._rotation_task = None
            logger.info("Stopped automatic rotation scheduler")
    
    async def _rotation_loop(self):
        """Background task for automatic rotation"""
        while True:
            try:
                # Check rotation schedules every hour
                await asyncio.sleep(3600)
                
                for secret_id, schedule in self.rotation_schedules.items():
                    # Here you would implement cron-like scheduling
                    # For simplicity, we'll rotate weekly
                    if self._should_rotate(secret_id, schedule):
                        await self.rotate_secret(secret_id)
                        logger.info(f"Auto-rotated secret: {secret_id}")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rotation loop: {e}")
    
    def _should_rotate(self, secret_id: str, schedule: str) -> bool:
        """Check if secret should be rotated based on schedule"""
        # Simplified implementation - in production use croniter or similar
        # For now, just check if it's been more than 7 days
        for entry in self.audit_log:
            if entry['secret_id'] == secret_id and entry['action'] == 'rotated':
                last_rotation = datetime.fromisoformat(entry['timestamp'])
                if datetime.now() - last_rotation > timedelta(days=7):
                    return True
        return False
    
    async def _notify_rotation(self, secret_id: str):
        """Send notification about secret rotation"""
        # In production, this would send emails, Slack messages, etc.
        logger.info(f"Secret rotated: {secret_id}")
    
    def _log_access(self, secret_id: str, action: str):
        """Log access for audit trail"""
        log_entry = {
            'secret_id': secret_id,
            'action': action,
            'timestamp': datetime.now().isoformat(),
            'provider': type(self.provider).__name__
        }
        self.audit_log.append(log_entry)
        
        # Keep only last 1000 entries
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]
    
    def get_audit_log(self, secret_id: Optional[str] = None) -> List[Dict]:
        """Get audit log entries"""
        if secret_id:
            return [e for e in self.audit_log if e['secret_id'] == secret_id]
        return self.audit_log
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics"""
        return {
            'provider': type(self.provider).__name__,
            'cache_stats': self.cache.get_stats(),
            'rotation_schedules': len(self.rotation_schedules),
            'audit_log_size': len(self.audit_log),
            'secrets_count': len(asyncio.run(self.list_secrets()))
        }