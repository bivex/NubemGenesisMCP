"""
Multi-Tenant Database Models
SQLAlchemy ORM models for NubemSuperFClaude multi-tenant architecture
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, DateTime, Date,
    Text, ARRAY, ForeignKey, Index, CheckConstraint, UniqueConstraint,
    DECIMAL, func
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, INET
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.hybrid import hybrid_property

Base = declarative_base()


class Tenant(Base):
    """
    Tenant model - represents a customer/organization using the platform
    """
    __tablename__ = "tenants"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Basic Info
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)

    # Plan & Status
    plan = Column(
        String(50),
        nullable=False,
        default='free'
    )
    status = Column(
        String(20),
        nullable=False,
        default='active'
    )

    # GCP & K8s Resources
    gcp_project_id = Column(String(255), unique=True)
    k8s_namespace = Column(String(255), unique=True)
    service_account_email = Column(String(255))

    # Limits (based on plan)
    max_requests_per_month = Column(Integer, default=100)
    max_personas_active = Column(Integer, default=10)
    max_api_keys = Column(Integer, default=1)

    # Billing
    billing_email = Column(String(255))
    stripe_customer_id = Column(String(255), unique=True)
    subscription_id = Column(String(255))

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime)

    # Trial
    trial_ends_at = Column(DateTime)

    # Metadata
    metadata = Column(JSONB, default={})

    # Relationships
    api_keys = relationship("APIKey", back_populates="tenant", cascade="all, delete-orphan")
    usage_metrics = relationship("UsageMetric", back_populates="tenant", cascade="all, delete-orphan")
    secrets = relationship("TenantSecret", back_populates="tenant", cascade="all, delete-orphan")
    events = relationship("TenantEvent", back_populates="tenant", cascade="all, delete-orphan")
    quota = relationship("TenantQuota", back_populates="tenant", uselist=False, cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            plan.in_(['free', 'pro', 'enterprise', 'custom']),
            name='plan_check'
        ),
        CheckConstraint(
            status.in_(['active', 'suspended', 'deleted', 'trial']),
            name='status_check'
        ),
        Index('idx_tenants_email', 'email', postgresql_where=(deleted_at.is_(None))),
        Index('idx_tenants_status', 'status', postgresql_where=(deleted_at.is_(None))),
        Index('idx_tenants_plan', 'plan'),
        Index('idx_tenants_gcp_project', 'gcp_project_id', postgresql_where=(deleted_at.is_(None))),
        Index('idx_tenants_created_at', created_at.desc()),
    )

    @hybrid_property
    def is_active(self) -> bool:
        """Check if tenant is active"""
        return self.status == 'active' and self.deleted_at is None

    @hybrid_property
    def is_trial(self) -> bool:
        """Check if tenant is in trial"""
        return self.status == 'trial' and (
            self.trial_ends_at is None or
            self.trial_ends_at > datetime.utcnow()
        )

    def __repr__(self):
        return f"<Tenant(id={self.id}, name='{self.name}', plan='{self.plan}', status='{self.status}')>"


class APIKey(Base):
    """
    API Key model - authentication credentials for tenants
    """
    __tablename__ = "api_keys"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(PGUUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)

    # Key Info
    name = Column(String(100), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)  # SHA256 hash
    key_prefix = Column(String(20), nullable=False)  # For display

    # Permissions
    role = Column(String(50), nullable=False, default='member')
    scopes = Column(ARRAY(Text), default=['read'])

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Usage Tracking
    last_used_at = Column(DateTime)
    request_count = Column(BigInteger, default=0)

    # Expiration
    expires_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    revoked_at = Column(DateTime)

    # Metadata
    created_by = Column(String(255))
    metadata = Column(JSONB, default={})

    # Relationships
    tenant = relationship("Tenant", back_populates="api_keys")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            role.in_(['owner', 'admin', 'member', 'readonly']),
            name='role_check'
        ),
        UniqueConstraint('tenant_id', 'name', name='unique_tenant_name'),
        Index('idx_api_keys_tenant', 'tenant_id', postgresql_where=(revoked_at.is_(None))),
        Index('idx_api_keys_hash', 'key_hash', postgresql_where=(is_active == True) & (revoked_at.is_(None))),
        Index('idx_api_keys_prefix', 'key_prefix'),
        Index('idx_api_keys_expires', 'expires_at', postgresql_where=(is_active == True) & (revoked_at.is_(None))),
    )

    @hybrid_property
    def is_valid(self) -> bool:
        """Check if API key is valid"""
        return (
            self.is_active and
            self.revoked_at is None and
            (self.expires_at is None or self.expires_at > datetime.utcnow())
        )

    def __repr__(self):
        return f"<APIKey(id={self.id}, tenant_id={self.tenant_id}, name='{self.name}', role='{self.role}')>"


class UsageMetric(Base):
    """
    Usage Metric model - tracks tenant usage for billing and rate limiting
    """
    __tablename__ = "usage_metrics"
    __table_args__ = (
        {'postgresql_partition_by': 'RANGE (date)'},
    )

    id = Column(BigInteger, primary_key=True)
    tenant_id = Column(PGUUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)

    # Time
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    date = Column(Date, nullable=False, default=func.current_date())
    hour = Column(Integer, nullable=False, default=func.extract('hour', func.now()))

    # Metrics
    requests_count = Column(Integer, nullable=False, default=0)
    tokens_input = Column(BigInteger, default=0)
    tokens_output = Column(BigInteger, default=0)
    tokens_total = Column(BigInteger, default=0)

    # Cost Tracking
    cost_usd = Column(DECIMAL(10, 6), default=0)

    # Resource Usage
    personas_used = Column(ARRAY(Text))
    mcps_used = Column(ARRAY(Text))

    # API Key
    api_key_id = Column(PGUUID(as_uuid=True), ForeignKey('api_keys.id', ondelete='SET NULL'))

    # Response Metrics
    avg_latency_ms = Column(Integer)
    error_count = Column(Integer, default=0)

    # Metadata
    metadata = Column(JSONB, default={})

    # Relationships
    tenant = relationship("Tenant", back_populates="usage_metrics")
    api_key = relationship("APIKey")

    def __repr__(self):
        return f"<UsageMetric(id={self.id}, tenant_id={self.tenant_id}, date={self.date}, requests={self.requests_count})>"


class TenantEvent(Base):
    """
    Tenant Event model - audit log of tenant actions
    """
    __tablename__ = "tenant_events"

    id = Column(BigInteger, primary_key=True)
    tenant_id = Column(PGUUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)

    # Event Info
    event_type = Column(String(50), nullable=False)
    event_category = Column(String(50), nullable=False)

    # Actor
    actor_type = Column(String(50), nullable=False)  # 'user', 'system', 'api'
    actor_id = Column(String(255))

    # Details
    description = Column(Text)

    # Data
    metadata = Column(JSONB, default={})

    # IP & Location
    ip_address = Column(INET)
    user_agent = Column(Text)

    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", back_populates="events")

    # Indexes
    __table_args__ = (
        Index('idx_events_tenant_time', 'tenant_id', created_at.desc()),
        Index('idx_events_type', 'event_type', created_at.desc()),
        Index('idx_events_category', 'event_category'),
    )

    def __repr__(self):
        return f"<TenantEvent(id={self.id}, tenant_id={self.tenant_id}, type='{self.event_type}')>"


class TenantSecret(Base):
    """
    Tenant Secret model - metadata about secrets stored in GCP Secret Manager
    """
    __tablename__ = "tenant_secrets"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(PGUUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)

    # Secret Info
    secret_name = Column(String(255), nullable=False)
    secret_type = Column(String(50), nullable=False)

    # GCP Secret Manager
    gcp_secret_path = Column(String(500), nullable=False)
    gcp_secret_version = Column(String(50))

    # Metadata
    description = Column(Text)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Rotation
    last_rotated_at = Column(DateTime)
    rotation_schedule = Column(String(50))  # Cron expression
    next_rotation_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime)

    # Metadata
    metadata = Column(JSONB, default={})

    # Relationships
    tenant = relationship("Tenant", back_populates="secrets")

    # Constraints
    __table_args__ = (
        UniqueConstraint('tenant_id', 'secret_name', name='unique_tenant_secret_name'),
        CheckConstraint(
            secret_type.in_(['api_key', 'token', 'certificate', 'password', 'custom']),
            name='secret_type_check'
        ),
        Index('idx_secrets_tenant', 'tenant_id', postgresql_where=(deleted_at.is_(None))),
        Index('idx_secrets_rotation', 'next_rotation_at', postgresql_where=(is_active == True) & (deleted_at.is_(None))),
    )

    def __repr__(self):
        return f"<TenantSecret(id={self.id}, tenant_id={self.tenant_id}, name='{self.secret_name}', type='{self.secret_type}')>"


class TenantQuota(Base):
    """
    Tenant Quota model - real-time quota tracking for rate limiting
    """
    __tablename__ = "tenant_quotas"

    tenant_id = Column(PGUUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), primary_key=True)

    # Current Month Counters
    current_month = Column(Date, nullable=False, default=func.date_trunc('month', func.current_date()))
    requests_count = Column(Integer, nullable=False, default=0)
    tokens_used = Column(BigInteger, nullable=False, default=0)

    # Limits
    requests_limit = Column(Integer, nullable=False)
    tokens_limit = Column(BigInteger)

    # Status
    is_quota_exceeded = Column(Boolean, nullable=False, default=False)
    quota_exceeded_at = Column(DateTime)

    # Timestamps
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    reset_at = Column(DateTime, nullable=False, default=func.date_trunc('month', func.current_date()) + func.cast('1 month', func.interval()))

    # Relationships
    tenant = relationship("Tenant", back_populates="quota")

    # Indexes
    __table_args__ = (
        Index('idx_quotas_exceeded', 'is_quota_exceeded', 'current_month'),
    )

    @hybrid_property
    def requests_remaining(self) -> int:
        """Calculate remaining requests"""
        return max(0, self.requests_limit - self.requests_count)

    @hybrid_property
    def usage_percentage(self) -> float:
        """Calculate usage percentage"""
        if self.requests_limit == 0:
            return 100.0
        return (self.requests_count / self.requests_limit) * 100

    def __repr__(self):
        return f"<TenantQuota(tenant_id={self.tenant_id}, requests={self.requests_count}/{self.requests_limit})>"


# Helper function to create all tables
def create_all_tables(engine):
    """
    Create all tables in the database

    Args:
        engine: SQLAlchemy engine
    """
    Base.metadata.create_all(engine)


# Helper function to drop all tables (use with caution!)
def drop_all_tables(engine):
    """
    Drop all tables in the database (DANGEROUS!)

    Args:
        engine: SQLAlchemy engine
    """
    Base.metadata.drop_all(engine)
