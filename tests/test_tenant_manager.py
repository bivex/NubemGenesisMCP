"""
Unit Tests for TenantManager
Tests all tenant lifecycle operations and business logic
"""

import pytest
import os
from datetime import datetime, timedelta
from uuid import uuid4

from core.tenant_manager import (
    TenantManager,
    TenantAlreadyExistsError,
    TenantNotFoundError,
    QuotaExceededError,
    TenantManagerError
)
from core.database import (
    init_database, close_database, get_engine,
    session_scope, Tenant, APIKey, TenantQuota, TenantEvent, UsageMetric
)
from core.database.models import Base


# Test database URL
TEST_DB_URL = os.getenv('TEST_DATABASE_URL', 'postgresql://postgres@localhost:5432/nubemsfc_test')


@pytest.fixture(scope='session')
def db_engine():
    """Create test database engine"""
    init_database(TEST_DB_URL, echo=False)
    engine = get_engine()

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Teardown
    Base.metadata.drop_all(engine)
    close_database()


@pytest.fixture(scope='function')
def clean_db(db_engine):
    """Clean database before each test"""
    # Delete all data
    with session_scope() as session:
        session.query(UsageMetric).delete()
        session.query(TenantEvent).delete()
        session.query(APIKey).delete()
        session.query(TenantQuota).delete()
        session.query(Tenant).delete()
        session.commit()

    yield

    # Cleanup after test
    with session_scope() as session:
        session.query(UsageMetric).delete()
        session.query(TenantEvent).delete()
        session.query(APIKey).delete()
        session.query(TenantQuota).delete()
        session.query(Tenant).delete()
        session.commit()


@pytest.fixture
def tenant_manager():
    """Create TenantManager instance"""
    return TenantManager(gcp_project_base="test-tenant", gcp_region="us-central1")


class TestTenantCreation:
    """Test tenant creation operations"""

    def test_create_tenant_free_plan(self, tenant_manager, clean_db):
        """Test creating tenant with free plan"""
        tenant, api_key = tenant_manager.create_tenant(
            name="Test Company",
            email="test@example.com",
            plan="free"
        )

        assert tenant is not None
        assert tenant.name == "Test Company"
        assert tenant.email == "test@example.com"
        assert tenant.plan == "free"
        assert tenant.status == "trial"
        assert tenant.max_requests_per_month == 100
        assert tenant.max_api_keys == 1
        assert tenant.gcp_project_id.startswith("test-tenant-")
        assert tenant.k8s_namespace.startswith("tenant-")

        # Check API key generated
        assert api_key.startswith("nsfc_")
        assert len(api_key) > 20

        # Verify quota created
        with session_scope() as session:
            quota = session.query(TenantQuota).filter_by(tenant_id=tenant.id).first()
            assert quota is not None
            assert quota.requests_limit == 100
            assert quota.requests_count == 0

    def test_create_tenant_pro_plan(self, tenant_manager, clean_db):
        """Test creating tenant with pro plan"""
        tenant, api_key = tenant_manager.create_tenant(
            name="Pro Company",
            email="pro@example.com",
            plan="pro"
        )

        assert tenant.plan == "pro"
        assert tenant.max_requests_per_month == 10000
        assert tenant.max_api_keys == 5

    def test_create_tenant_enterprise_plan(self, tenant_manager, clean_db):
        """Test creating tenant with enterprise plan"""
        tenant, api_key = tenant_manager.create_tenant(
            name="Enterprise Corp",
            email="enterprise@example.com",
            plan="enterprise"
        )

        assert tenant.plan == "enterprise"
        assert tenant.max_requests_per_month == 100000
        assert tenant.max_api_keys == 20

    def test_create_tenant_duplicate_email(self, tenant_manager, clean_db):
        """Test that duplicate email raises error"""
        tenant_manager.create_tenant(
            name="First Company",
            email="duplicate@example.com",
            plan="free"
        )

        with pytest.raises(TenantAlreadyExistsError):
            tenant_manager.create_tenant(
                name="Second Company",
                email="duplicate@example.com",
                plan="pro"
            )

    def test_create_tenant_with_metadata(self, tenant_manager, clean_db):
        """Test creating tenant with custom metadata"""
        metadata = {
            "industry": "fintech",
            "company_size": "50-100",
            "source": "website"
        }

        tenant, _ = tenant_manager.create_tenant(
            name="Metadata Test",
            email="metadata@example.com",
            plan="free",
            metadata=metadata
        )

        assert tenant.metadata == metadata

    def test_create_tenant_no_trial(self, tenant_manager, clean_db):
        """Test creating tenant without trial period"""
        tenant, _ = tenant_manager.create_tenant(
            name="No Trial",
            email="notrial@example.com",
            plan="pro",
            trial_days=0
        )

        assert tenant.status == "active"
        assert tenant.trial_ends_at is None

    def test_create_tenant_logs_event(self, tenant_manager, clean_db):
        """Test that tenant creation logs event"""
        tenant, _ = tenant_manager.create_tenant(
            name="Event Test",
            email="event@example.com",
            plan="free"
        )

        with session_scope() as session:
            events = session.query(TenantEvent).filter_by(
                tenant_id=tenant.id,
                event_type='tenant.created'
            ).all()

            assert len(events) == 1
            assert events[0].event_category == 'lifecycle'
            assert events[0].actor_type == 'system'


class TestTenantRetrieval:
    """Test tenant retrieval operations"""

    def test_get_tenant_by_id(self, tenant_manager, clean_db):
        """Test getting tenant by ID"""
        tenant, _ = tenant_manager.create_tenant(
            name="Get Test",
            email="get@example.com",
            plan="free"
        )

        retrieved = tenant_manager.get_tenant(tenant_id=tenant.id)

        assert retrieved is not None
        assert retrieved.id == tenant.id
        assert retrieved.email == tenant.email

    def test_get_tenant_by_email(self, tenant_manager, clean_db):
        """Test getting tenant by email"""
        tenant, _ = tenant_manager.create_tenant(
            name="Email Test",
            email="email@example.com",
            plan="free"
        )

        retrieved = tenant_manager.get_tenant(email="email@example.com")

        assert retrieved is not None
        assert retrieved.id == tenant.id
        assert retrieved.email == "email@example.com"

    def test_get_tenant_not_found(self, tenant_manager, clean_db):
        """Test getting non-existent tenant returns None"""
        retrieved = tenant_manager.get_tenant(tenant_id=uuid4())
        assert retrieved is None

    def test_get_deleted_tenant_excluded(self, tenant_manager, clean_db):
        """Test that soft-deleted tenants are excluded by default"""
        tenant, _ = tenant_manager.create_tenant(
            name="Delete Test",
            email="delete@example.com",
            plan="free"
        )

        # Soft delete
        tenant_manager.delete_tenant(tenant.id)

        # Should not be found
        retrieved = tenant_manager.get_tenant(tenant_id=tenant.id)
        assert retrieved is None

    def test_get_deleted_tenant_included(self, tenant_manager, clean_db):
        """Test that soft-deleted tenants can be included"""
        tenant, _ = tenant_manager.create_tenant(
            name="Delete Include Test",
            email="delete_include@example.com",
            plan="free"
        )

        # Soft delete
        tenant_manager.delete_tenant(tenant.id)

        # Should be found with include_deleted=True
        retrieved = tenant_manager.get_tenant(tenant_id=tenant.id, include_deleted=True)
        assert retrieved is not None
        assert retrieved.deleted_at is not None


class TestTenantUpdate:
    """Test tenant update operations"""

    def test_update_tenant_name(self, tenant_manager, clean_db):
        """Test updating tenant name"""
        tenant, _ = tenant_manager.create_tenant(
            name="Old Name",
            email="update@example.com",
            plan="free"
        )

        updated = tenant_manager.update_tenant(tenant.id, name="New Name")

        assert updated.name == "New Name"
        assert updated.email == "update@example.com"  # Unchanged

    def test_update_tenant_plan(self, tenant_manager, clean_db):
        """Test updating tenant plan"""
        tenant, _ = tenant_manager.create_tenant(
            name="Plan Test",
            email="plan@example.com",
            plan="free"
        )

        updated = tenant_manager.update_tenant(tenant.id, plan="pro")

        assert updated.plan == "pro"
        assert updated.max_requests_per_month == 10000  # Pro plan limit

        # Verify quota updated
        with session_scope() as session:
            quota = session.query(TenantQuota).filter_by(tenant_id=tenant.id).first()
            assert quota.requests_limit == 10000

    def test_update_tenant_status(self, tenant_manager, clean_db):
        """Test updating tenant status"""
        tenant, _ = tenant_manager.create_tenant(
            name="Status Test",
            email="status@example.com",
            plan="free"
        )

        updated = tenant_manager.update_tenant(tenant.id, status="suspended")

        assert updated.status == "suspended"

    def test_update_tenant_not_found(self, tenant_manager, clean_db):
        """Test updating non-existent tenant raises error"""
        with pytest.raises(TenantNotFoundError):
            tenant_manager.update_tenant(uuid4(), name="Fail")

    def test_update_tenant_logs_event(self, tenant_manager, clean_db):
        """Test that tenant update logs event"""
        tenant, _ = tenant_manager.create_tenant(
            name="Event Update",
            email="event_update@example.com",
            plan="free"
        )

        tenant_manager.update_tenant(tenant.id, plan="pro")

        with session_scope() as session:
            events = session.query(TenantEvent).filter_by(
                tenant_id=tenant.id,
                event_type='tenant.updated'
            ).all()

            assert len(events) == 1
            assert 'plan' in events[0].metadata['changes']


class TestTenantDeletion:
    """Test tenant deletion operations"""

    def test_soft_delete_tenant(self, tenant_manager, clean_db):
        """Test soft deleting tenant"""
        tenant, _ = tenant_manager.create_tenant(
            name="Soft Delete",
            email="soft@example.com",
            plan="free"
        )

        result = tenant_manager.delete_tenant(tenant.id, hard_delete=False)

        assert result is True

        # Verify soft deleted
        with session_scope() as session:
            deleted = session.query(Tenant).filter_by(id=tenant.id).first()
            assert deleted.deleted_at is not None
            assert deleted.status == "deleted"

    def test_soft_delete_logs_event(self, tenant_manager, clean_db):
        """Test that soft delete logs event"""
        tenant, _ = tenant_manager.create_tenant(
            name="Delete Event",
            email="delete_event@example.com",
            plan="free"
        )

        tenant_manager.delete_tenant(tenant.id)

        with session_scope() as session:
            events = session.query(TenantEvent).filter_by(
                tenant_id=tenant.id,
                event_type='tenant.deleted'
            ).all()

            assert len(events) == 1

    def test_delete_tenant_not_found(self, tenant_manager, clean_db):
        """Test deleting non-existent tenant raises error"""
        with pytest.raises(TenantNotFoundError):
            tenant_manager.delete_tenant(uuid4())


class TestQuotaManagement:
    """Test quota checking and enforcement"""

    def test_check_quota_available(self, tenant_manager, clean_db):
        """Test checking quota when available"""
        tenant, _ = tenant_manager.create_tenant(
            name="Quota Test",
            email="quota@example.com",
            plan="free"
        )

        quota_info = tenant_manager.check_quota(tenant.id)

        assert quota_info['requests_count'] == 0
        assert quota_info['requests_limit'] == 100
        assert quota_info['requests_remaining'] == 100
        assert quota_info['usage_percentage'] == 0.0
        assert quota_info['is_exceeded'] is False

    def test_check_quota_after_usage(self, tenant_manager, clean_db):
        """Test checking quota after some usage"""
        tenant, _ = tenant_manager.create_tenant(
            name="Quota Usage",
            email="quota_usage@example.com",
            plan="free"
        )

        # Increment usage
        tenant_manager.increment_usage(tenant.id, requests=50)

        quota_info = tenant_manager.check_quota(tenant.id)

        assert quota_info['requests_count'] == 50
        assert quota_info['requests_remaining'] == 50
        assert quota_info['usage_percentage'] == 50.0

    def test_check_quota_exceeded(self, tenant_manager, clean_db):
        """Test quota exceeded error"""
        tenant, _ = tenant_manager.create_tenant(
            name="Quota Exceeded",
            email="quota_exceeded@example.com",
            plan="free"
        )

        # Use all quota
        tenant_manager.increment_usage(tenant.id, requests=100)

        with pytest.raises(QuotaExceededError):
            tenant_manager.check_quota(tenant.id)


class TestUsageTracking:
    """Test usage tracking and metrics"""

    def test_increment_usage_basic(self, tenant_manager, clean_db):
        """Test basic usage increment"""
        tenant, _ = tenant_manager.create_tenant(
            name="Usage Test",
            email="usage@example.com",
            plan="free"
        )

        result = tenant_manager.increment_usage(
            tenant.id,
            requests=1,
            tokens_input=100,
            tokens_output=200
        )

        assert result is True

        # Verify quota updated
        with session_scope() as session:
            quota = session.query(TenantQuota).filter_by(tenant_id=tenant.id).first()
            assert quota.requests_count == 1
            assert quota.tokens_used == 300

    def test_increment_usage_with_metadata(self, tenant_manager, clean_db):
        """Test usage increment with personas and MCPs"""
        tenant, _ = tenant_manager.create_tenant(
            name="Usage Metadata",
            email="usage_meta@example.com",
            plan="free"
        )

        result = tenant_manager.increment_usage(
            tenant.id,
            requests=1,
            tokens_input=100,
            tokens_output=200,
            personas_used=['system-architect', 'backend-developer'],
            mcps_used=['openai', 'anthropic'],
            latency_ms=250
        )

        assert result is True

        # Verify metric recorded
        with session_scope() as session:
            metrics = session.query(UsageMetric).filter_by(tenant_id=tenant.id).all()
            assert len(metrics) == 1
            assert metrics[0].personas_used == ['system-architect', 'backend-developer']
            assert metrics[0].mcps_used == ['openai', 'anthropic']
            assert metrics[0].avg_latency_ms == 250

    def test_get_usage_summary(self, tenant_manager, clean_db):
        """Test getting usage summary"""
        tenant, _ = tenant_manager.create_tenant(
            name="Summary Test",
            email="summary@example.com",
            plan="free"
        )

        # Add some usage
        tenant_manager.increment_usage(tenant.id, requests=5, tokens_input=500, tokens_output=1000)
        tenant_manager.increment_usage(tenant.id, requests=3, tokens_input=300, tokens_output=600)

        summary = tenant_manager.get_usage_summary(tenant.id, days=30)

        assert summary['total_requests'] == 8
        assert summary['total_tokens'] == 2400
        assert summary['total_cost_usd'] > 0


class TestAPIKeyManagement:
    """Test API key generation and management"""

    def test_generate_api_key(self, tenant_manager, clean_db):
        """Test generating additional API key"""
        tenant, initial_key = tenant_manager.create_tenant(
            name="API Key Test",
            email="apikey@example.com",
            plan="pro"  # Pro allows 5 keys
        )

        new_key, key_obj = tenant_manager.generate_api_key(
            tenant.id,
            name="Second Key",
            role="readonly",
            scopes=["read"]
        )

        assert new_key.startswith("nsfc_")
        assert key_obj.name == "Second Key"
        assert key_obj.role == "readonly"
        assert key_obj.scopes == ["read"]

    def test_generate_api_key_max_exceeded(self, tenant_manager, clean_db):
        """Test that max API keys limit is enforced"""
        tenant, _ = tenant_manager.create_tenant(
            name="Max Keys",
            email="maxkeys@example.com",
            plan="free"  # Free allows only 1 key
        )

        # Try to create second key (should fail)
        with pytest.raises(TenantManagerError, match="maximum API keys limit"):
            tenant_manager.generate_api_key(tenant.id, name="Second Key")

    def test_api_key_with_expiration(self, tenant_manager, clean_db):
        """Test generating API key with expiration"""
        tenant, _ = tenant_manager.create_tenant(
            name="Expiring Key",
            email="expiring@example.com",
            plan="pro"
        )

        new_key, key_obj = tenant_manager.generate_api_key(
            tenant.id,
            name="Expiring Key",
            expires_days=30
        )

        assert key_obj.expires_at is not None
        assert key_obj.expires_at > datetime.utcnow()

    def test_api_key_logs_event(self, tenant_manager, clean_db):
        """Test that API key creation logs event"""
        tenant, _ = tenant_manager.create_tenant(
            name="Key Event",
            email="key_event@example.com",
            plan="pro"
        )

        tenant_manager.generate_api_key(tenant.id, name="Test Key")

        with session_scope() as session:
            events = session.query(TenantEvent).filter_by(
                tenant_id=tenant.id,
                event_type='api_key.created'
            ).all()

            assert len(events) == 1
            assert events[0].event_category == 'security'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
