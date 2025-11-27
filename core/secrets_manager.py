#!/usr/bin/env python3
"""
NubemSuperFClaude - Unified Secrets Manager
Handles API keys from Google Secret Manager or environment variables
"""

import os
import logging
from typing import Optional, Dict, Any
from functools import lru_cache

logger = logging.getLogger(__name__)

try:
    from google.cloud import secretmanager
    GOOGLE_CLOUD_AVAILABLE = True
except ImportError:
    GOOGLE_CLOUD_AVAILABLE = False
    logger.warning("Google Cloud Secret Manager not available - using environment variables only")


class SecretsManager:
    """Unified secrets manager for NubemSuperFClaude"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Solo inicializar una vez (Singleton pattern)
        if SecretsManager._initialized:
            return

        # Use nubemsecrets project for secrets
        self.project_id = os.getenv('SECRET_MANAGER_PROJECT', os.getenv('GOOGLE_CLOUD_PROJECT', 'nubemsecrets'))

        # Enable Secret Manager if we have credentials
        # Check for ADC (Application Default Credentials) or explicit credentials
        has_adc = os.path.exists(os.path.expanduser('~/.config/gcloud/application_default_credentials.json'))
        has_explicit_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS') and os.path.exists(os.getenv('GOOGLE_APPLICATION_CREDENTIALS', ''))
        in_cloud_run = os.getenv('K_SERVICE') is not None  # Cloud Run sets this env var
        in_gke = os.getenv('KUBERNETES_SERVICE_HOST') is not None  # GKE/Kubernetes sets this
        has_secret_manager_env = os.getenv('SECRET_MANAGER_PROJECT') is not None  # Explicit config

        self.use_secret_manager = has_adc or has_explicit_creds or in_cloud_run or in_gke or has_secret_manager_env

        # Suprimir warnings de gRPC
        os.environ['GRPC_VERBOSITY'] = 'ERROR'
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

        # Initialize Google Cloud client if available and enabled
        self.client = None
        if self.use_secret_manager and GOOGLE_CLOUD_AVAILABLE:
            try:
                # Suprimir logs al crear el cliente
                import logging as gcp_logging
                gcp_logging.getLogger('google').setLevel(gcp_logging.ERROR)

                # En GKE con Workload Identity: eliminar GOOGLE_APPLICATION_CREDENTIALS
                # para forzar el uso de metadata server
                if in_gke and os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
                    logger.info(f"🔧 Removing GOOGLE_APPLICATION_CREDENTIALS in GKE (using Workload Identity)")
                    del os.environ['GOOGLE_APPLICATION_CREDENTIALS']

                # En GKE, usar Workload Identity (sin credenciales explícitas)
                # En local/Cloud Run, intentará usar ADC
                from google.auth import default as google_auth_default
                from google.auth.exceptions import DefaultCredentialsError

                try:
                    credentials, project = google_auth_default()
                    self.client = secretmanager.SecretManagerServiceClient(credentials=credentials)
                    logger.info(f"✅ Secret Manager initialized with credentials for project: {self.project_id}")
                except DefaultCredentialsError as e:
                    logger.error(f"❌ DefaultCredentialsError: {e}")
                    # Fallback: intentar sin credenciales (confiar en el entorno)
                    self.client = secretmanager.SecretManagerServiceClient()
                    logger.info(f"✅ Secret Manager initialized (using default environment) for project: {self.project_id}")

            except Exception as e:
                logger.error(f"❌ Failed to initialize Secret Manager: {e}")
                import traceback
                traceback.print_exc()
                self.use_secret_manager = False
        elif self.use_secret_manager and not GOOGLE_CLOUD_AVAILABLE:
            if os.getenv('NC_DEBUG') == 'true':
                logger.warning("Secret Manager enabled but google-cloud-secret-manager not installed")
            self.use_secret_manager = False

        SecretsManager._initialized = True
    
    def _get_user_prefix(self, email: str) -> str:
        """
        Convert email to safe prefix for multi-tenancy

        Args:
            email: User email (e.g., 'user@domain.com')

        Returns:
            Safe prefix (e.g., 'user_domain_com')
        """
        return email.replace('@', '_').replace('.', '_')

    def _get_full_secret_name(self, secret_name: str, user_email: Optional[str] = None) -> str:
        """
        Get full secret name with user prefix if applicable

        Args:
            secret_name: Base secret name
            user_email: Optional user email for multi-tenancy

        Returns:
            Full secret name with prefix if user_email provided
        """
        if user_email:
            prefix = self._get_user_prefix(user_email)
            return f"{prefix}_{secret_name}"
        return secret_name

    @lru_cache(maxsize=128)
    def get_secret(self, secret_name: str, user_email: Optional[str] = None) -> Optional[str]:
        """
        Get secret from Google Secret Manager or environment variables

        Args:
            secret_name: Name of the secret (e.g., 'openai-api-key')
            user_email: Optional user email for multi-tenant isolation

        Returns:
            Secret value or None if not found
        """
        # Get full secret name with user prefix if applicable
        full_secret_name = self._get_full_secret_name(secret_name, user_email)

        # Try Google Secret Manager first
        if self.use_secret_manager and self.client and self.project_id:
            try:
                name = f"projects/{self.project_id}/secrets/{full_secret_name}/versions/latest"
                response = self.client.access_secret_version(request={"name": name})
                secret_value = response.payload.data.decode("UTF-8")

                if secret_value:
                    user_info = f" for user {user_email}" if user_email else ""
                    logger.debug(f"Secret {secret_name} loaded from Secret Manager{user_info}")
                    return secret_value

            except Exception as e:
                # If user-specific secret not found and user_email provided, try system secret as fallback
                if user_email:
                    logger.debug(f"User-specific secret {full_secret_name} not found, trying system secret")
                    return self.get_secret(secret_name, user_email=None)
                logger.warning(f"Failed to load secret {full_secret_name} from Secret Manager: {e}")

        # Fallback to environment variables (only for system secrets)
        if not user_email:
            env_name = secret_name.upper().replace('-', '_')
            env_value = os.getenv(env_name)

            if env_value:
                logger.debug(f"Secret {secret_name} loaded from environment variable {env_name}")
                return env_value

            # Try alternative environment variable names
            alternative_names = self._get_alternative_env_names(secret_name)
            for alt_name in alternative_names:
                alt_value = os.getenv(alt_name)
                if alt_value:
                    logger.debug(f"Secret {secret_name} loaded from alternative env var {alt_name}")
                    return alt_value

        user_context = f" for user {user_email}" if user_email else ""
        logger.warning(f"Secret {secret_name} not found{user_context}")
        return None
    
    def _get_alternative_env_names(self, secret_name: str) -> list:
        """Get alternative environment variable names for a secret"""
        alternatives = []
        
        # Common mapping patterns
        mappings = {
            'openai-api-key': ['OPENAI_API_KEY', 'OPENAI_KEY'],
            'anthropic-api-key': ['ANTHROPIC_API_KEY', 'CLAUDE_API_KEY', 'ANTHROPIC_KEY'],
            'gemini-api-key': ['GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_KEY'],
            'huggingface-api-key': ['HUGGINGFACE_API_KEY', 'HF_TOKEN', 'HUGGINGFACE_TOKEN'],
            'jwt-secret': ['JWT_SECRET', 'JWT_SECRET_KEY'],
            'session-secret': ['SESSION_SECRET', 'SESSION_SECRET_KEY']
        }
        
        if secret_name in mappings:
            alternatives.extend(mappings[secret_name])
        
        return alternatives
    
    # Convenience methods for specific API keys
    def get_openai_key(self) -> Optional[str]:
        """Get OpenAI API key"""
        return self.get_secret('openai-api-key')
    
    def get_anthropic_key(self) -> Optional[str]:
        """Get Anthropic API key"""
        return self.get_secret('anthropic-api-key')
    
    def get_gemini_key(self) -> Optional[str]:
        """Get Gemini API key"""
        return self.get_secret('gemini-api-key')
    
    def get_huggingface_key(self) -> Optional[str]:
        """Get Hugging Face API key"""
        return self.get_secret('huggingface-api-key')
    
    def get_jwt_secret(self) -> Optional[str]:
        """Get JWT secret"""
        return self.get_secret('jwt-secret')
    
    def get_session_secret(self) -> Optional[str]:
        """Get session secret"""
        return self.get_secret('session-secret')
    
    # Cloud provider secrets
    def get_aws_credentials(self) -> Dict[str, Optional[str]]:
        """Get AWS credentials"""
        return {
            'access_key_id': self.get_secret('aws-access-key-id'),
            'secret_access_key': self.get_secret('aws-secret-access-key'),
            'region': os.getenv('AWS_REGION', 'us-east-1')
        }
    
    def get_azure_credentials(self) -> Dict[str, Optional[str]]:
        """Get Azure credentials"""
        return {
            'client_id': self.get_secret('azure-client-id'),
            'client_secret': self.get_secret('azure-client-secret'),
            'tenant_id': os.getenv('AZURE_TENANT_ID'),
            'subscription_id': os.getenv('AZURE_SUBSCRIPTION_ID')
        }
    
    def get_gcp_credentials(self) -> Dict[str, Optional[str]]:
        """Get GCP credentials info"""
        return {
            'project_id': self.project_id,
            'credentials_path': os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
            'service_account_email': os.getenv('GOOGLE_SERVICE_ACCOUNT_EMAIL')
        }
    
    def validate_required_secrets(self) -> Dict[str, bool]:
        """Validate that all required secrets are available"""
        required_secrets = {
            'openai-api-key': 'OpenAI API Key',
            'anthropic-api-key': 'Anthropic API Key',
            'gemini-api-key': 'Gemini API Key',
            'jwt-secret': 'JWT Secret',
            'session-secret': 'Session Secret'
        }
        
        results = {}
        missing_secrets = []
        
        for secret_name, description in required_secrets.items():
            value = self.get_secret(secret_name)
            is_available = bool(value and len(value.strip()) > 0)
            results[secret_name] = is_available
            
            if not is_available:
                missing_secrets.append(f"{description} ({secret_name})")
        
        if missing_secrets:
            logger.error(f"Missing required secrets: {', '.join(missing_secrets)}")
        
        return results
    
    def list_secrets(self, user_email: Optional[str] = None) -> list:
        """
        List all secrets, optionally filtered by user

        Args:
            user_email: Optional user email to filter secrets

        Returns:
            List of secret names (without user prefix for user-specific secrets)
        """
        if not self.use_secret_manager or not self.client:
            logger.warning("Secret Manager not available for listing secrets")
            return []

        try:
            parent = f"projects/{self.project_id}"
            request = {"parent": parent}
            secrets_list = self.client.list_secrets(request=request)

            secret_names = []
            user_prefix = self._get_user_prefix(user_email) + "_" if user_email else ""

            for secret in secrets_list:
                secret_name = secret.name.split('/')[-1]

                if user_email:
                    # Filter by user prefix and remove prefix from display
                    if secret_name.startswith(user_prefix):
                        display_name = secret_name[len(user_prefix):]
                        secret_names.append(display_name)
                    # Also show global/system secrets (NOT starting with user_ prefix)
                    elif not secret_name.startswith('user_'):
                        secret_names.append(secret_name)
                else:
                    # System mode: list all non-user secrets
                    # Skip secrets that start with user_ prefix
                    if not secret_name.startswith('user_'):
                        secret_names.append(secret_name)

            return sorted(secret_names)

        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            return []

    def create_secret(self, secret_name: str, secret_value: str, user_email: Optional[str] = None, labels: Optional[Dict[str, str]] = None) -> bool:
        """
        Create a new secret in Secret Manager

        Args:
            secret_name: Base name of the secret
            secret_value: Secret value to store
            user_email: Optional user email for multi-tenancy
            labels: Optional labels to attach to the secret

        Returns:
            True if successful, False otherwise
        """
        if not self.use_secret_manager or not self.client:
            logger.error("Secret Manager not available for creating secrets")
            return False

        full_secret_name = self._get_full_secret_name(secret_name, user_email)

        try:
            # Prepare labels
            secret_labels = labels or {}
            if user_email:
                # Add owner label
                owner_label = self._get_user_prefix(user_email)
                secret_labels['owner'] = owner_label

            # Create secret
            parent = f"projects/{self.project_id}"
            secret = {
                'replication': {'automatic': {}},
                'labels': secret_labels
            }

            response = self.client.create_secret(
                request={
                    'parent': parent,
                    'secret_id': full_secret_name,
                    'secret': secret
                }
            )

            # Add secret version with value
            payload = secret_value.encode('UTF-8')
            self.client.add_secret_version(
                request={
                    'parent': response.name,
                    'payload': {'data': payload}
                }
            )

            user_info = f" for user {user_email}" if user_email else ""
            logger.info(f"Created secret {secret_name}{user_info}")

            # Clear cache for this secret
            self.get_secret.cache_clear()

            return True

        except Exception as e:
            logger.error(f"Failed to create secret {full_secret_name}: {e}")
            return False

    def update_secret(self, secret_name: str, secret_value: str, user_email: Optional[str] = None) -> bool:
        """
        Update an existing secret (add new version)

        Args:
            secret_name: Base name of the secret
            secret_value: New secret value
            user_email: Optional user email for multi-tenancy

        Returns:
            True if successful, False otherwise
        """
        if not self.use_secret_manager or not self.client:
            logger.error("Secret Manager not available for updating secrets")
            return False

        full_secret_name = self._get_full_secret_name(secret_name, user_email)

        try:
            parent = f"projects/{self.project_id}/secrets/{full_secret_name}"
            payload = secret_value.encode('UTF-8')

            self.client.add_secret_version(
                request={
                    'parent': parent,
                    'payload': {'data': payload}
                }
            )

            user_info = f" for user {user_email}" if user_email else ""
            logger.info(f"Updated secret {secret_name}{user_info}")

            # Clear cache for this secret
            self.get_secret.cache_clear()

            return True

        except Exception as e:
            logger.error(f"Failed to update secret {full_secret_name}: {e}")
            return False

    def delete_secret(self, secret_name: str, user_email: Optional[str] = None) -> bool:
        """
        Delete a secret from Secret Manager

        Args:
            secret_name: Base name of the secret
            user_email: Optional user email for multi-tenancy

        Returns:
            True if successful, False otherwise
        """
        if not self.use_secret_manager or not self.client:
            logger.error("Secret Manager not available for deleting secrets")
            return False

        full_secret_name = self._get_full_secret_name(secret_name, user_email)

        try:
            name = f"projects/{self.project_id}/secrets/{full_secret_name}"
            self.client.delete_secret(request={'name': name})

            user_info = f" for user {user_email}" if user_email else ""
            logger.info(f"Deleted secret {secret_name}{user_info}")

            # Clear cache
            self.get_secret.cache_clear()

            return True

        except Exception as e:
            logger.error(f"Failed to delete secret {full_secret_name}: {e}")
            return False

    def get_configuration_info(self) -> Dict[str, Any]:
        """Get current configuration information"""
        return {
            'secret_manager_enabled': self.use_secret_manager,
            'google_cloud_available': GOOGLE_CLOUD_AVAILABLE,
            'project_id': self.project_id,
            'client_initialized': self.client is not None,
            'credentials_path': os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
            'environment': os.getenv('NODE_ENV', 'development')
        }


# Global instance
secrets_manager = SecretsManager()


# Convenience functions for backward compatibility
def get_openai_key() -> Optional[str]:
    """Get OpenAI API key"""
    return secrets_manager.get_openai_key()


def get_anthropic_key() -> Optional[str]:
    """Get Anthropic API key"""
    return secrets_manager.get_anthropic_key()


def get_gemini_key() -> Optional[str]:
    """Get Gemini API key"""
    return secrets_manager.get_gemini_key()


def get_huggingface_key() -> Optional[str]:
    """Get Hugging Face API key"""
    return secrets_manager.get_huggingface_key()


def validate_api_keys() -> bool:
    """Validate that all required API keys are available"""
    validation_results = secrets_manager.validate_required_secrets()
    
    # Check minimum required keys for basic operation
    required_for_operation = ['openai-api-key', 'anthropic-api-key']
    
    available_required = sum(1 for key in required_for_operation 
                           if validation_results.get(key, False))
    
    if available_required < 2:
        logger.error("Insufficient API keys for operation - need at least OpenAI and Anthropic")
        return False
    
    return True


if __name__ == "__main__":
    # Test the secrets manager
    print("🔐 Testing NubemSuperFClaude Secrets Manager")
    print("=" * 50)
    
    # Show configuration
    config = secrets_manager.get_configuration_info()
    print("📋 Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    # Test validation
    print("\n🧪 Validating secrets...")
    validation_results = secrets_manager.validate_required_secrets()
    
    for secret_name, is_available in validation_results.items():
        status = "✅" if is_available else "❌"
        print(f"  {status} {secret_name}")
    
    # Overall status
    print(f"\n🎯 Overall Status: {'✅ Ready' if validate_api_keys() else '❌ Missing Keys'}")