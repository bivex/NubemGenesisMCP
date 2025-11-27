"""
Multi-Tenant Vault Manager
Unified interface for managing secrets across all tenant GCP projects
Uses GCP Secret Manager with tenant isolation
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from uuid import UUID
from google.cloud import secretmanager
from google.api_core import exceptions as google_exceptions

logger = logging.getLogger(__name__)


class VaultError(Exception):
    """Base exception for vault operations"""
    pass


class SecretNotFoundError(VaultError):
    """Raised when secret is not found"""
    pass


class TenantNotFoundError(VaultError):
    """Raised when tenant is not found"""
    pass


class SecretAccessDeniedError(VaultError):
    """Raised when access to secret is denied"""
    pass


class MultiTenantVaultManager:
    """
    Manages secrets across multiple tenant GCP projects

    Responsibilities:
    - Get/set/delete secrets for tenants
    - List all secrets for a tenant
    - Secret rotation management
    - Audit logging for compliance
    - Cross-project secret management
    """

    def __init__(self, main_project_id: str):
        """
        Initialize MultiTenantVaultManager

        Args:
            main_project_id: Main/parent GCP project ID (for metadata)
        """
        self.main_project_id = main_project_id
        self.client = secretmanager.SecretManagerServiceClient()
        logger.info(f"MultiTenantVaultManager initialized (main project: {main_project_id})")

    def get_secret(
        self,
        tenant_id: UUID,
        secret_name: str,
        version: str = "latest"
    ) -> str:
        """
        Get secret value for tenant

        Args:
            tenant_id: Tenant UUID
            secret_name: Name of the secret
            version: Secret version (default: "latest")

        Returns:
            Secret value as string

        Raises:
            TenantNotFoundError: If tenant not found
            SecretNotFoundError: If secret not found
            SecretAccessDeniedError: If access denied
        """
        try:
            # Get tenant project ID from metadata
            tenant_project_id = self._get_tenant_project_id(tenant_id)

            # Build secret path
            secret_path = f"projects/{tenant_project_id}/secrets/{secret_name}/versions/{version}"

            logger.info(f"Getting secret '{secret_name}' for tenant {str(tenant_id)[:8]}")

            # Access secret
            response = self.client.access_secret_version(request={"name": secret_path})

            # Decode payload
            secret_value = response.payload.data.decode('UTF-8')

            # Log access (audit trail)
            self._log_secret_access(
                tenant_id=tenant_id,
                secret_name=secret_name,
                action="read",
                success=True
            )

            return secret_value

        except google_exceptions.NotFound:
            logger.error(f"Secret '{secret_name}' not found for tenant {str(tenant_id)[:8]}")
            raise SecretNotFoundError(f"Secret '{secret_name}' not found")
        except google_exceptions.PermissionDenied:
            logger.error(f"Access denied to secret '{secret_name}' for tenant {str(tenant_id)[:8]}")
            raise SecretAccessDeniedError(f"Access denied to secret '{secret_name}'")
        except Exception as e:
            logger.error(f"Error getting secret: {e}")
            raise VaultError(f"Failed to get secret: {e}")

    def set_secret(
        self,
        tenant_id: UUID,
        secret_name: str,
        secret_value: str,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Set secret value for tenant

        Args:
            tenant_id: Tenant UUID
            secret_name: Name of the secret
            secret_value: Secret value to store
            labels: Optional labels for the secret
            annotations: Optional annotations

        Returns:
            True if successful

        Raises:
            TenantNotFoundError: If tenant not found
            VaultError: If operation fails
        """
        try:
            # Get tenant project ID
            tenant_project_id = self._get_tenant_project_id(tenant_id)
            tenant_id_short = str(tenant_id)[:8]

            logger.info(f"Setting secret '{secret_name}' for tenant {tenant_id_short}")

            # Check if secret exists
            secret_path = f"projects/{tenant_project_id}/secrets/{secret_name}"
            try:
                self.client.get_secret(request={"name": secret_path})
                secret_exists = True
            except google_exceptions.NotFound:
                secret_exists = False

            # Create secret if it doesn't exist
            if not secret_exists:
                logger.info(f"Creating new secret '{secret_name}'")

                parent = f"projects/{tenant_project_id}"

                # Prepare labels
                secret_labels = {
                    "tenant_id": tenant_id_short,
                    "managed_by": "vault_manager"
                }
                if labels:
                    secret_labels.update(labels)

                # Prepare annotations
                secret_annotations = {
                    "tenant.nubemsfc.com/id": str(tenant_id),
                    "tenant.nubemsfc.com/created_at": datetime.utcnow().isoformat()
                }
                if annotations:
                    secret_annotations.update(annotations)

                # Create secret
                secret = {
                    "replication": {"automatic": {}},
                    "labels": secret_labels,
                    "annotations": secret_annotations
                }

                self.client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_name,
                        "secret": secret
                    }
                )

            # Add new version
            parent = f"projects/{tenant_project_id}/secrets/{secret_name}"
            payload = {"data": secret_value.encode('UTF-8')}

            self.client.add_secret_version(
                request={
                    "parent": parent,
                    "payload": payload
                }
            )

            # Log action
            self._log_secret_access(
                tenant_id=tenant_id,
                secret_name=secret_name,
                action="write",
                success=True
            )

            logger.info(f"✅ Secret '{secret_name}' set successfully for tenant {tenant_id_short}")
            return True

        except google_exceptions.PermissionDenied:
            logger.error(f"Access denied when setting secret '{secret_name}'")
            raise SecretAccessDeniedError(f"Access denied to set secret '{secret_name}'")
        except Exception as e:
            logger.error(f"Error setting secret: {e}")
            raise VaultError(f"Failed to set secret: {e}")

    def delete_secret(
        self,
        tenant_id: UUID,
        secret_name: str,
        permanent: bool = False
    ) -> bool:
        """
        Delete secret for tenant

        Args:
            tenant_id: Tenant UUID
            secret_name: Name of the secret
            permanent: If True, permanently delete (cannot be recovered)

        Returns:
            True if successful

        Raises:
            TenantNotFoundError: If tenant not found
            SecretNotFoundError: If secret not found
        """
        try:
            # Get tenant project ID
            tenant_project_id = self._get_tenant_project_id(tenant_id)
            tenant_id_short = str(tenant_id)[:8]

            secret_path = f"projects/{tenant_project_id}/secrets/{secret_name}"

            logger.warning(f"Deleting secret '{secret_name}' for tenant {tenant_id_short} (permanent={permanent})")

            # Delete secret
            self.client.delete_secret(request={"name": secret_path})

            # Log action
            self._log_secret_access(
                tenant_id=tenant_id,
                secret_name=secret_name,
                action="delete",
                success=True,
                metadata={"permanent": permanent}
            )

            logger.info(f"✅ Secret '{secret_name}' deleted for tenant {tenant_id_short}")
            return True

        except google_exceptions.NotFound:
            logger.error(f"Secret '{secret_name}' not found")
            raise SecretNotFoundError(f"Secret '{secret_name}' not found")
        except Exception as e:
            logger.error(f"Error deleting secret: {e}")
            raise VaultError(f"Failed to delete secret: {e}")

    def list_secrets(self, tenant_id: UUID) -> List[Dict[str, Any]]:
        """
        List all secrets for tenant

        Args:
            tenant_id: Tenant UUID

        Returns:
            List of secret information dictionaries

        Raises:
            TenantNotFoundError: If tenant not found
        """
        try:
            # Get tenant project ID
            tenant_project_id = self._get_tenant_project_id(tenant_id)
            tenant_id_short = str(tenant_id)[:8]

            parent = f"projects/{tenant_project_id}"

            logger.info(f"Listing secrets for tenant {tenant_id_short}")

            # List secrets
            secrets = []
            for secret in self.client.list_secrets(request={"parent": parent}):
                # Get latest version info
                try:
                    latest_version = self.client.access_secret_version(
                        request={"name": f"{secret.name}/versions/latest"}
                    )
                    version_created = latest_version.create_time
                except:
                    version_created = None

                secrets.append({
                    "name": secret.name.split("/")[-1],
                    "full_path": secret.name,
                    "labels": dict(secret.labels),
                    "annotations": dict(secret.annotations) if hasattr(secret, 'annotations') else {},
                    "created_at": secret.create_time.isoformat() if secret.create_time else None,
                    "latest_version_created": version_created.isoformat() if version_created else None
                })

            logger.info(f"Found {len(secrets)} secrets for tenant {tenant_id_short}")
            return secrets

        except Exception as e:
            logger.error(f"Error listing secrets: {e}")
            raise VaultError(f"Failed to list secrets: {e}")

    def rotate_secret(
        self,
        tenant_id: UUID,
        secret_name: str,
        new_value: str
    ) -> bool:
        """
        Rotate secret value (add new version)

        Args:
            tenant_id: Tenant UUID
            secret_name: Name of the secret
            new_value: New secret value

        Returns:
            True if successful
        """
        try:
            tenant_id_short = str(tenant_id)[:8]
            logger.info(f"Rotating secret '{secret_name}' for tenant {tenant_id_short}")

            # Set new value (automatically creates new version)
            self.set_secret(
                tenant_id=tenant_id,
                secret_name=secret_name,
                secret_value=new_value,
                annotations={
                    "tenant.nubemsfc.com/rotated_at": datetime.utcnow().isoformat(),
                    "tenant.nubemsfc.com/rotation_type": "manual"
                }
            )

            # Log rotation
            self._log_secret_access(
                tenant_id=tenant_id,
                secret_name=secret_name,
                action="rotate",
                success=True
            )

            logger.info(f"✅ Secret '{secret_name}' rotated for tenant {tenant_id_short}")
            return True

        except Exception as e:
            logger.error(f"Error rotating secret: {e}")
            raise VaultError(f"Failed to rotate secret: {e}")

    def get_secret_versions(
        self,
        tenant_id: UUID,
        secret_name: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get version history for a secret

        Args:
            tenant_id: Tenant UUID
            secret_name: Name of the secret
            limit: Maximum number of versions to return

        Returns:
            List of version information

        Raises:
            SecretNotFoundError: If secret not found
        """
        try:
            # Get tenant project ID
            tenant_project_id = self._get_tenant_project_id(tenant_id)
            secret_path = f"projects/{tenant_project_id}/secrets/{secret_name}"

            logger.info(f"Getting versions for secret '{secret_name}'")

            # List versions
            versions = []
            count = 0
            for version in self.client.list_secret_versions(request={"parent": secret_path}):
                if count >= limit:
                    break

                versions.append({
                    "name": version.name.split("/")[-1],
                    "state": version.state.name,
                    "created_at": version.create_time.isoformat() if version.create_time else None,
                    "destroyed_at": version.destroy_time.isoformat() if version.destroy_time else None
                })
                count += 1

            logger.info(f"Found {len(versions)} versions for secret '{secret_name}'")
            return versions

        except google_exceptions.NotFound:
            raise SecretNotFoundError(f"Secret '{secret_name}' not found")
        except Exception as e:
            logger.error(f"Error getting secret versions: {e}")
            raise VaultError(f"Failed to get secret versions: {e}")

    def _get_tenant_project_id(self, tenant_id: UUID) -> str:
        """
        Get GCP project ID for tenant from metadata

        Args:
            tenant_id: Tenant UUID

        Returns:
            Tenant's GCP project ID

        Raises:
            TenantNotFoundError: If tenant not found
        """
        tenant_id_short = str(tenant_id)[:8]

        # Get project metadata from main project
        metadata_secret = f"projects/{self.main_project_id}/secrets/tenant-{tenant_id_short}-project-metadata/versions/latest"

        try:
            response = self.client.access_secret_version(request={"name": metadata_secret})
            metadata = eval(response.payload.data.decode('UTF-8'))  # JSON stored as string
            return metadata["project_id"]

        except google_exceptions.NotFound:
            logger.error(f"Tenant {tenant_id_short} not found in metadata")
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")
        except Exception as e:
            logger.error(f"Error getting tenant project ID: {e}")
            raise VaultError(f"Failed to get tenant project ID: {e}")

    def _log_secret_access(
        self,
        tenant_id: UUID,
        secret_name: str,
        action: str,
        success: bool,
        metadata: Optional[Dict] = None
    ):
        """
        Log secret access for audit trail

        Args:
            tenant_id: Tenant UUID
            secret_name: Secret name
            action: Action performed (read/write/delete/rotate)
            success: Whether action succeeded
            metadata: Optional additional metadata
        """
        # In production, this should write to a proper audit log
        # For now, just use logger
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": str(tenant_id),
            "tenant_id_short": str(tenant_id)[:8],
            "secret_name": secret_name,
            "action": action,
            "success": success,
            "metadata": metadata or {}
        }

        if success:
            logger.info(f"Audit: {action} on '{secret_name}' for {log_entry['tenant_id_short']} - SUCCESS")
        else:
            logger.warning(f"Audit: {action} on '{secret_name}' for {log_entry['tenant_id_short']} - FAILED")

        # TODO: Write to structured audit log (BigQuery, Cloud Logging, etc.)

    def get_secrets_needing_rotation(self, days: int = 90) -> List[Dict]:
        """
        Get list of secrets that need rotation

        Args:
            days: Number of days since last rotation

        Returns:
            List of secrets needing rotation
        """
        # This would query all tenants and check secret ages
        # Implementation would depend on how rotation metadata is stored
        logger.info(f"Checking for secrets needing rotation (older than {days} days)")

        # TODO: Implement rotation check
        # Would need to:
        # 1. List all tenants
        # 2. For each tenant, list secrets
        # 3. Check last rotation date
        # 4. Return secrets older than threshold

        return []

    def bulk_rotate_secrets(
        self,
        secret_name: str,
        tenant_ids: Optional[List[UUID]] = None
    ) -> Dict[str, bool]:
        """
        Rotate a specific secret across multiple tenants

        Args:
            secret_name: Name of secret to rotate
            tenant_ids: List of tenant IDs (None = all tenants)

        Returns:
            Dictionary mapping tenant_id to success status
        """
        logger.info(f"Bulk rotating secret '{secret_name}' across tenants")

        # TODO: Implement bulk rotation
        # Would need to:
        # 1. Get list of tenants (from database or metadata)
        # 2. For each tenant, generate new secret value
        # 3. Rotate secret
        # 4. Track success/failure

        return {}
