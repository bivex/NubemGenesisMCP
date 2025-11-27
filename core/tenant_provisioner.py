"""
Tenant Provisioner - Orchestrates infrastructure provisioning for new tenants
Integrates Terraform modules to create GCP projects, K8s namespaces, and secrets
"""

import os
import json
import subprocess
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)


class TenantProvisionerError(Exception):
    """Base exception for TenantProvisioner errors"""
    pass


class TerraformError(TenantProvisionerError):
    """Raised when Terraform operations fail"""
    pass


class ProvisioningFailedError(TenantProvisionerError):
    """Raised when resource provisioning fails"""
    pass


class TenantProvisioner:
    """
    Orchestrates tenant infrastructure provisioning

    Responsibilities:
    - Create GCP project for tenant
    - Create Kubernetes namespace with quotas
    - Set up Secret Manager in tenant project
    - Configure Workload Identity
    - Deploy External Secrets Operator manifests
    """

    def __init__(
        self,
        main_project_id: str,
        billing_account_id: str,
        gke_cluster_name: str,
        gke_cluster_location: str = "us-central1",
        terraform_dir: Optional[str] = None
    ):
        """
        Initialize TenantProvisioner

        Args:
            main_project_id: Main/parent GCP project ID
            billing_account_id: GCP billing account ID
            gke_cluster_name: GKE cluster name
            gke_cluster_location: GKE cluster location/region
            terraform_dir: Path to Terraform modules (default: auto-detect)
        """
        self.main_project_id = main_project_id
        self.billing_account_id = billing_account_id
        self.gke_cluster_name = gke_cluster_name
        self.gke_cluster_location = gke_cluster_location

        # Auto-detect terraform directory
        if terraform_dir is None:
            current_dir = Path(__file__).parent.parent
            self.terraform_dir = current_dir / "terraform"
        else:
            self.terraform_dir = Path(terraform_dir)

        if not self.terraform_dir.exists():
            raise TenantProvisionerError(f"Terraform directory not found: {self.terraform_dir}")

        logger.info(f"TenantProvisioner initialized (project: {main_project_id}, cluster: {gke_cluster_name})")

    def provision_tenant(
        self,
        tenant_id: UUID,
        tenant_name: str,
        plan: str = "free",
        environment: str = "production",
        dry_run: bool = False
    ) -> Dict:
        """
        Provision all infrastructure for a new tenant

        Args:
            tenant_id: Tenant UUID
            tenant_name: Tenant/company name
            plan: Subscription plan (free/pro/enterprise/custom)
            environment: Environment name
            dry_run: If True, only plan without applying

        Returns:
            Dictionary with provisioned resources info

        Raises:
            ProvisioningFailedError: If provisioning fails
        """
        tenant_id_str = str(tenant_id)
        tenant_id_short = tenant_id_str[:8]

        logger.info(f"Starting provisioning for tenant {tenant_id_short} ({tenant_name})")

        try:
            # Step 1: Create GCP project
            logger.info("Step 1/4: Creating GCP project...")
            gcp_project = self._provision_gcp_project(
                tenant_id_str,
                tenant_id_short,
                tenant_name,
                environment,
                dry_run
            )

            # Step 2: Create Kubernetes namespace
            logger.info("Step 2/4: Creating Kubernetes namespace...")
            k8s_namespace = self._provision_k8s_namespace(
                tenant_id_str,
                tenant_id_short,
                tenant_name,
                plan,
                gcp_project,
                environment,
                dry_run
            )

            # Step 3: Set up Secret Manager
            logger.info("Step 3/4: Setting up Secret Manager...")
            secrets_info = self._provision_secrets(
                tenant_id_str,
                tenant_id_short,
                tenant_name,
                gcp_project,
                k8s_namespace,
                dry_run
            )

            # Step 4: Verify resources
            logger.info("Step 4/4: Verifying resources...")
            if not dry_run:
                verification = self._verify_provisioning(gcp_project, k8s_namespace)
            else:
                verification = {"status": "dry_run", "verified": False}

            result = {
                "tenant_id": tenant_id_str,
                "tenant_name": tenant_name,
                "gcp_project": gcp_project,
                "k8s_namespace": k8s_namespace,
                "secrets": secrets_info,
                "verification": verification,
                "status": "success" if not dry_run else "dry_run"
            }

            logger.info(f"✅ Provisioning complete for tenant {tenant_id_short}")
            return result

        except Exception as e:
            logger.error(f"❌ Provisioning failed for tenant {tenant_id_short}: {e}")
            raise ProvisioningFailedError(f"Failed to provision tenant: {e}")

    def _provision_gcp_project(
        self,
        tenant_id: str,
        tenant_id_short: str,
        tenant_name: str,
        environment: str,
        dry_run: bool
    ) -> Dict:
        """Provision GCP project for tenant using Terraform"""
        module_path = self.terraform_dir / "modules" / "tenant-project"

        tfvars = {
            "tenant_id": tenant_id,
            "tenant_id_short": tenant_id_short,
            "tenant_name": tenant_name,
            "main_project_id": self.main_project_id,
            "billing_account_id": self.billing_account_id,
            "environment": environment,
            "budget_amount_usd": 500,  # Default budget
            "enable_quota_limits": True,
            "quota_cpus": 24,
            "quota_instances": 10,
            "create_vpc": False  # Use shared VPC by default
        }

        # Run Terraform
        outputs = self._run_terraform(module_path, tfvars, dry_run)

        return {
            "project_id": outputs.get("project_id"),
            "project_number": outputs.get("project_number"),
            "service_account_email": outputs.get("service_account_email")
        }

    def _provision_k8s_namespace(
        self,
        tenant_id: str,
        tenant_id_short: str,
        tenant_name: str,
        plan: str,
        gcp_project: Dict,
        environment: str,
        dry_run: bool
    ) -> Dict:
        """Provision Kubernetes namespace for tenant using Terraform"""
        module_path = self.terraform_dir / "modules" / "tenant-namespace"

        # Plan-based quotas
        plan_quotas = {
            "free": {
                "cpu_requests": "1",
                "cpu_limits": "2",
                "memory_requests": "2Gi",
                "memory_limits": "4Gi",
                "pods": "10",
                "max_requests_per_month": 100
            },
            "pro": {
                "cpu_requests": "4",
                "cpu_limits": "8",
                "memory_requests": "8Gi",
                "memory_limits": "16Gi",
                "pods": "20",
                "max_requests_per_month": 10000
            },
            "enterprise": {
                "cpu_requests": "16",
                "cpu_limits": "32",
                "memory_requests": "32Gi",
                "memory_limits": "64Gi",
                "pods": "50",
                "max_requests_per_month": 100000
            },
            "custom": {
                "cpu_requests": "32",
                "cpu_limits": "64",
                "memory_requests": "64Gi",
                "memory_limits": "128Gi",
                "pods": "100",
                "max_requests_per_month": 999999999
            }
        }

        quotas = plan_quotas.get(plan, plan_quotas["free"])

        tfvars = {
            "tenant_id": tenant_id,
            "tenant_id_short": tenant_id_short,
            "tenant_name": tenant_name,
            "tenant_plan": plan,
            "namespace_name": f"tenant-{tenant_id_short}",
            "gcp_project_id": gcp_project["project_id"],
            "gcp_service_account_email": gcp_project["service_account_email"],
            "environment": environment,
            "quota_cpu_requests": quotas["cpu_requests"],
            "quota_cpu_limits": quotas["cpu_limits"],
            "quota_memory_requests": quotas["memory_requests"],
            "quota_memory_limits": quotas["memory_limits"],
            "quota_pods": quotas["pods"],
            "max_requests_per_month": quotas["max_requests_per_month"],
            "enable_network_policies": True,
            "allow_external_https": True,
            "database_namespace": "production"
        }

        # Run Terraform
        outputs = self._run_terraform(module_path, tfvars, dry_run)

        return {
            "name": outputs.get("namespace_name", f"tenant-{tenant_id_short}"),
            "service_account": outputs.get("service_account_name"),
            "resource_quota": outputs.get("resource_quota_name"),
            "config_map": outputs.get("config_map_name")
        }

    def _provision_secrets(
        self,
        tenant_id: str,
        tenant_id_short: str,
        tenant_name: str,
        gcp_project: Dict,
        k8s_namespace: Dict,
        dry_run: bool
    ) -> Dict:
        """Provision Secret Manager for tenant using Terraform"""
        module_path = self.terraform_dir / "modules" / "tenant-secrets"

        # Initial secrets (placeholders - tenant will update these)
        secrets = {
            "openai-api-key": {
                "value": "placeholder-update-via-ui",
                "type": "api_key"
            },
            "anthropic-api-key": {
                "value": "placeholder-update-via-ui",
                "type": "api_key"
            },
            "groq-api-key": {
                "value": "placeholder-update-via-ui",
                "type": "api_key"
            }
        }

        tfvars = {
            "tenant_id": tenant_id,
            "tenant_id_short": tenant_id_short,
            "tenant_name": tenant_name,
            "tenant_project_id": gcp_project["project_id"],
            "main_project_id": self.main_project_id,
            "tenant_service_account_email": gcp_project["service_account_email"],
            "secrets": secrets,
            "enable_k8s_access": True,
            "enable_k8s_sync": True,
            "k8s_namespace": k8s_namespace["name"],
            "k8s_service_account": k8s_namespace["service_account"],
            "gke_cluster_name": self.gke_cluster_name,
            "gke_cluster_location": self.gke_cluster_location
        }

        # Run Terraform
        outputs = self._run_terraform(module_path, tfvars, dry_run)

        return {
            "secret_ids": outputs.get("secret_ids", {}),
            "secret_names": outputs.get("secret_names", []),
            "secret_store_name": outputs.get("secret_store_name"),
            "external_secrets": outputs.get("external_secret_names", [])
        }

    def _run_terraform(self, module_path: Path, tfvars: Dict, dry_run: bool) -> Dict:
        """
        Run Terraform init, plan, and optionally apply

        Args:
            module_path: Path to Terraform module
            tfvars: Terraform variables
            dry_run: If True, only plan without applying

        Returns:
            Terraform outputs

        Raises:
            TerraformError: If Terraform commands fail
        """
        if not module_path.exists():
            raise TerraformError(f"Terraform module not found: {module_path}")

        # Create tfvars file
        tfvars_file = module_path / "terraform.tfvars.json"
        with open(tfvars_file, 'w') as f:
            json.dump(tfvars, f, indent=2)

        try:
            # Terraform init
            logger.info(f"Running terraform init in {module_path}")
            self._run_command(["terraform", "init"], cwd=module_path)

            # Terraform plan
            plan_file = module_path / "tfplan"
            logger.info(f"Running terraform plan...")
            self._run_command(
                ["terraform", "plan", "-out", str(plan_file)],
                cwd=module_path
            )

            if dry_run:
                logger.info("Dry run - skipping terraform apply")
                return {}

            # Terraform apply
            logger.info(f"Running terraform apply...")
            self._run_command(
                ["terraform", "apply", "-auto-approve", str(plan_file)],
                cwd=module_path
            )

            # Get outputs
            logger.info("Getting terraform outputs...")
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=module_path,
                capture_output=True,
                text=True,
                check=True
            )

            outputs_raw = json.loads(result.stdout)
            outputs = {k: v["value"] for k, v in outputs_raw.items()}

            return outputs

        except subprocess.CalledProcessError as e:
            logger.error(f"Terraform command failed: {e}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            raise TerraformError(f"Terraform command failed: {e}")
        finally:
            # Cleanup tfvars file (contains sensitive data)
            if tfvars_file.exists():
                tfvars_file.unlink()

    def _run_command(self, cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
        """Run shell command and return result"""
        logger.debug(f"Running command: {' '.join(cmd)} in {cwd}")
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return result

    def _verify_provisioning(self, gcp_project: Dict, k8s_namespace: Dict) -> Dict:
        """Verify that resources were provisioned correctly"""
        verification = {
            "gcp_project": self._verify_gcp_project(gcp_project["project_id"]),
            "k8s_namespace": self._verify_k8s_namespace(k8s_namespace["name"]),
            "verified": False
        }

        verification["verified"] = all([
            verification["gcp_project"]["exists"],
            verification["k8s_namespace"]["exists"]
        ])

        return verification

    def _verify_gcp_project(self, project_id: str) -> Dict:
        """Verify GCP project exists"""
        try:
            result = subprocess.run(
                ["gcloud", "projects", "describe", project_id, "--format=json"],
                capture_output=True,
                text=True,
                check=True
            )
            project_info = json.loads(result.stdout)
            return {
                "exists": True,
                "state": project_info.get("lifecycleState"),
                "project_number": project_info.get("projectNumber")
            }
        except subprocess.CalledProcessError:
            return {"exists": False, "state": None, "project_number": None}

    def _verify_k8s_namespace(self, namespace_name: str) -> Dict:
        """Verify Kubernetes namespace exists"""
        try:
            result = subprocess.run(
                ["kubectl", "get", "namespace", namespace_name, "-o", "json"],
                capture_output=True,
                text=True,
                check=True
            )
            ns_info = json.loads(result.stdout)
            return {
                "exists": True,
                "status": ns_info.get("status", {}).get("phase"),
                "labels": ns_info.get("metadata", {}).get("labels", {})
            }
        except subprocess.CalledProcessError:
            return {"exists": False, "status": None, "labels": {}}

    def deprovision_tenant(self, tenant_id: UUID, force: bool = False) -> bool:
        """
        Deprovision tenant infrastructure (use with caution!)

        Args:
            tenant_id: Tenant UUID
            force: If True, skip confirmation checks

        Returns:
            True if successful

        Raises:
            ProvisioningFailedError: If deprovisioning fails
        """
        tenant_id_str = str(tenant_id)
        tenant_id_short = tenant_id_str[:8]

        logger.warning(f"⚠️ Deprovisioning tenant {tenant_id_short}")

        if not force:
            logger.error("Deprovisioning requires force=True flag")
            raise ProvisioningFailedError("Deprovisioning requires force=True")

        try:
            # Delete Kubernetes namespace (will delete all resources in it)
            namespace_name = f"tenant-{tenant_id_short}"
            logger.info(f"Deleting K8s namespace {namespace_name}...")
            subprocess.run(
                ["kubectl", "delete", "namespace", namespace_name, "--ignore-not-found=true"],
                check=True
            )

            # Note: GCP project deletion requires organization-level permissions
            # and should be done carefully (consider marking as deleted instead)
            logger.warning("GCP project NOT deleted (requires manual intervention)")

            logger.info(f"✅ Tenant {tenant_id_short} deprovisioned")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Deprovisioning failed: {e}")
            raise ProvisioningFailedError(f"Failed to deprovision tenant: {e}")
