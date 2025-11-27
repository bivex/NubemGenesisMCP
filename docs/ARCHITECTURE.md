# 🏗️ NubemGenesis-MCP Architecture

## System Architecture Documentation

**Version:** 1.2.0
**Last Updated:** 2025-11-24
**Status:** Production

---

## 📊 Overview

NubemGenesis-MCP is a sophisticated Meta-MCP system that orchestrates 141 specialized AI personas through an intelligent routing system, providing expert knowledge across multiple domains.

---

## 🎯 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Internet / Clients                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      GCP Load Balancer                           │
│                    (External IP: Public)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes Service (LB)                       │
│                    Namespace: production                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
┌──────────────────────┐          ┌──────────────────────┐
│   MCP Server Pods    │          │   Redis Pod          │
│   (3 replicas)       │◄────────▶│   (1 replica)        │
│   - API Gateway      │          │   - Device Flow      │
│   - Auth Handler     │          │   - Session Cache    │
│   - Router           │          └──────────────────────┘
└──────────┬───────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Trinity Router                             │
│              (Strategy Selection: Single/Swarm/RAG/Hybrid)       │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌──────────────┐ ┌──────────┐ ┌──────────────┐
     │   Single     │ │  Swarm   │ │   Hybrid     │
     │   Strategy   │ │ Strategy │ │  Strategy    │
     └──────┬───────┘ └────┬─────┘ └──────┬───────┘
            └──────────────┼──────────────┘
                           ▼
           ┌───────────────────────────────┐
           │    141 AI Personas            │
           │    (Specialized Experts)      │
           └───────────────┬───────────────┘
                           │
                           ▼
           ┌───────────────────────────────┐
           │   External MCP Servers        │
           │   (8+ Integrations)           │
           └───────────────────────────────┘
```

---

## 🧩 Component Architecture

### 1. API Gateway Layer

**Component:** MCP Server
**Technology:** Python FastAPI
**Replicas:** 3 (Auto-scaling: 3-10)
**Port:** 8000 (Internal) → 80 (External)

**Responsibilities:**
- HTTP/HTTPS request handling
- JSON-RPC protocol implementation
- Authentication & authorization
- Rate limiting
- Request routing to Trinity Router
- Response formatting

**Endpoints:**
```
GET  /health              - Health check
POST /mcp                 - MCP JSON-RPC endpoint
GET  /personas            - List all personas
GET  /personas/{key}      - Get specific persona
POST /orchestrate         - Orchestrate task
POST /auth/device/code    - Device flow: get code
POST /auth/device/token   - Device flow: exchange token
```

### 2. Trinity Router

**Component:** Trinity Router Engine
**Technology:** Python
**Algorithm:** Semantic + Rule-based

**Strategies:**

#### a) Single Strategy
- **When:** Simple, direct questions
- **Flow:** Query → Persona Selection → Direct Response
- **Example:** "What is Python?" → python-expert
- **Latency:** <50ms

#### b) Swarm Strategy
- **When:** Complex, multi-domain tasks
- **Flow:** Query → Multiple Personas → Collaboration → Synthesis
- **Example:** "Build secure e-commerce" → architecture + security + backend + frontend
- **Latency:** 200-500ms

#### c) RAG Enhanced Strategy
- **When:** Context-heavy queries
- **Flow:** Query → Embedding → Vector Search → Context + Persona → Response
- **Example:** "Explain our company's architecture" → context retrieval + architect
- **Latency:** 100-200ms

#### d) Hybrid Strategy
- **When:** Requires both reasoning and actions
- **Flow:** Query → Persona Analysis + MCP Actions → Synthesis
- **Example:** "Analyze GitHub repo and create issues" → code-reviewer + github-mcp
- **Latency:** 500-1000ms

**Selection Algorithm:**
```python
def select_strategy(query):
    complexity = analyze_complexity(query)
    context_needed = requires_context(query)
    action_needed = requires_external_action(query)

    if action_needed and complexity > 0.7:
        return "hybrid"
    elif context_needed:
        return "rag_enhanced"
    elif complexity > 0.8:
        return "swarm"
    else:
        return "single"
```

### 3. Personas System

**Total Personas:** 141
**Storage:** In-memory + ConfigMap
**Format:** JSON/YAML

**Persona Structure:**
```json
{
  "key": "senior-developer",
  "name": "Senior Developer",
  "category": "development",
  "level": "L5",
  "specialties": [
    "Software Architecture",
    "Code Review",
    "Design Patterns",
    "Performance Optimization"
  ],
  "system_prompt": "You are a senior software developer...",
  "description": "Expert in software development...",
  "capabilities": {
    "code_review": true,
    "architecture_design": true,
    "mentoring": true
  }
}
```

**Categories Distribution:**
```
Development:    30 personas (21%)
Security:       10 personas (7%)
AI/ML:          10 personas (7%)
Architecture:   15 personas (11%)
Data:           12 personas (8%)
Management:     15 personas (11%)
Specialized:    49 personas (35%)
```

### 4. Meta-MCP Orchestrator

**Component:** MCP Integration Layer
**Technology:** Python Async
**Connections:** 8+ external MCPs

**Supported MCPs:**
1. **Google Workspace** - Email, Docs, Calendar
2. **Slack** - Team communication
3. **PostgreSQL** - Database operations
4. **MongoDB** - NoSQL operations
5. **Redis** - Caching & pub/sub
6. **Docker** - Container management
7. **SQLite** - Local storage
8. **Brave Search** - Web search

**Connection Management:**
- Connection pooling (max 10 per MCP)
- Circuit breaker pattern (threshold: 5 failures)
- Retry logic (exponential backoff)
- Health monitoring (every 30s)

### 5. Authentication System

**Type:** OAuth 2.0 Device Flow
**Storage:** Redis
**Token Lifetime:** 1 hour
**Refresh:** Supported

**Flow:**
```
1. Client → POST /auth/device/code
   Response: { device_code, user_code, verification_uri }

2. User → Opens verification_uri, enters user_code

3. Client → POST /auth/device/token (polling)
   Response: { access_token, expires_in, token_type }

4. Client → Authenticated requests with Bearer token
```

**Roles:**
- `admin` - Full access
- `developer` - Read/write personas, execute tasks
- `readonly` - Read-only access

### 6. Caching Layer

**Component:** Redis
**Version:** 7.x
**Purpose:** Device flow, session management

**Cached Data:**
- Device codes (TTL: 10 minutes)
- User sessions (TTL: 1 hour)
- Frequently accessed personas (TTL: 1 hour)
- Rate limit counters (TTL: 1 minute)

**Configuration:**
```yaml
Maxmemory: 512MB
Eviction Policy: allkeys-lru
Persistence: AOF (every second)
```

---

## 🔄 Data Flow

### Request Flow (Simple)

```
1. Client sends request
   POST /orchestrate
   { "task": "Explain Docker", "strategy": "single" }

2. API Gateway validates request
   - Check authentication
   - Check rate limits
   - Parse JSON

3. Trinity Router selects strategy
   - Analyzes query complexity: LOW
   - Selects strategy: SINGLE
   - Chooses persona: docker-expert

4. Persona processes request
   - Loads system prompt
   - Generates response
   - Returns result

5. API Gateway formats response
   {
     "status": "success",
     "strategy": "single",
     "persona": "docker-expert",
     "result": "Docker is a containerization platform..."
   }

6. Response sent to client
   Latency: 15-50ms
```

### Request Flow (Complex - Hybrid)

```
1. Client sends request
   POST /orchestrate
   {
     "task": "Analyze GitHub repo and create security issues",
     "strategy": "hybrid"
   }

2. API Gateway validates request

3. Trinity Router selects hybrid strategy
   - Analyzes query complexity: HIGH
   - Detects need for external actions: YES
   - Selects personas: [security-engineer, code-reviewer]
   - Detects needed MCPs: [github]

4. Hybrid Orchestrator executes

   Phase 1: Persona Analysis
   - security-engineer analyzes security requirements
   - code-reviewer reviews code patterns

   Phase 2: MCP Actions
   - Connect to GitHub MCP
   - Fetch repository code
   - Analyze files

   Phase 3: Persona + MCP Integration
   - Personas analyze MCP data
   - Generate security findings

   Phase 4: MCP Actions
   - Create GitHub issues for findings

   Phase 5: Synthesis
   - Combine results
   - Generate final report

5. API Gateway formats response
   {
     "status": "success",
     "strategy": "hybrid",
     "personas_used": ["security-engineer", "code-reviewer"],
     "mcps_used": ["github"],
     "actions_performed": [
       "analyzed_repo",
       "created_5_issues"
     ],
     "result": "Analysis complete. 5 security issues created..."
   }

6. Response sent to client
   Latency: 500-2000ms
```

---

## 🛡️ Security Architecture

### Defense in Depth

```
Layer 1: Network Security
├─ GCP Firewall Rules
├─ VPC Network Isolation
└─ DDoS Protection

Layer 2: Load Balancer
├─ SSL/TLS Termination
├─ Rate Limiting
└─ IP Allowlisting (optional)

Layer 3: API Gateway
├─ OAuth 2.0 Authentication
├─ JWT Token Validation
├─ API Key Verification
└─ Request Validation

Layer 4: Application
├─ Input Sanitization
├─ Prompt Injection Prevention
├─ RBAC Authorization
└─ Audit Logging

Layer 5: Data
├─ Encryption at Rest
├─ Encryption in Transit
├─ Secret Management (GCP Secret Manager)
└─ PII Detection & Redaction
```

### Threat Model

**Threats Mitigated:**
- ✅ SQL Injection (parameterized queries)
- ✅ Prompt Injection (input sanitization)
- ✅ XSS (output encoding)
- ✅ CSRF (token-based)
- ✅ SSRF (URL validation)
- ✅ Authentication Bypass (multi-layer auth)
- ✅ Data Leakage (access controls)
- ✅ DDoS (rate limiting)

---

## ⚡ Performance Architecture

### Optimization Strategies

**1. Caching:**
- Redis for frequently accessed data
- In-memory persona cache
- HTTP response caching (optional)

**2. Connection Pooling:**
- MCP connection pools (10 per MCP)
- Redis connection pool (20 connections)
- Keep-alive connections

**3. Async Processing:**
- AsyncIO for I/O operations
- Non-blocking MCP calls
- Parallel persona execution (swarm)

**4. Auto-scaling:**
- HPA based on CPU (70%) and Memory (80%)
- Min replicas: 3, Max replicas: 10
- Scale-up: 30s, Scale-down: 5min

**5. Load Balancing:**
- Round-robin across pods
- Session affinity (optional)
- Health check-based routing

### Performance Targets

```
Metric               Target    Current   Status
─────────────────────────────────────────────────
P50 Latency          <20ms     15ms      ✅
P95 Latency          <100ms    85ms      ✅
P99 Latency          <200ms    150ms     ✅
Throughput           >100rps   120rps    ✅
Error Rate           <1%       0.5%      ✅
Availability         >99.9%    99.95%    ✅
```

---

## 🔧 Deployment Architecture

### Infrastructure as Code

**Tools:**
- Terraform (infrastructure)
- Kubernetes manifests (application)
- Helm charts (optional)

**Environments:**
- **Production** - 3-10 replicas, LoadBalancer
- **Development** - 2 replicas, NodePort
- **Staging** - 2 replicas, LoadBalancer (optional)

### CI/CD Pipeline

```
1. Code Commit → GitHub

2. Automated Tests
   ├─ Unit Tests
   ├─ Integration Tests
   ├─ Security Scans
   └─ Code Quality

3. Build
   ├─ Docker Image Build
   ├─ Tag with version
   └─ Push to GCR

4. Deploy to Staging (optional)
   ├─ Kubernetes apply
   ├─ Health checks
   └─ Smoke tests

5. Deploy to Production
   ├─ Rolling update
   ├─ Health checks
   ├─ Automated rollback (if failed)
   └─ Notify team
```

---

## 📊 Monitoring Architecture

### Metrics Collection

**Prometheus Metrics:**
```
- http_requests_total
- http_request_duration_seconds
- persona_selection_duration
- mcp_connection_duration
- active_connections
- error_rate
- cache_hit_ratio
```

**Custom Metrics:**
```
- personas_invoked_total
- strategy_selection_count
- mcp_call_duration
- authentication_attempts
```

### Logging

**Structured Logging (JSON):**
```json
{
  "timestamp": "2025-11-24T16:00:00Z",
  "level": "INFO",
  "service": "mcp-server",
  "request_id": "abc123",
  "user_id": "user_xyz",
  "action": "orchestrate",
  "strategy": "hybrid",
  "personas": ["security-engineer"],
  "latency_ms": 450,
  "status": "success"
}
```

**Log Levels:**
- DEBUG - Development debugging
- INFO - Normal operations
- WARNING - Potential issues
- ERROR - Errors requiring attention
- CRITICAL - System failures

### Alerting

**Alert Rules:**
- Error rate > 5% (5min)
- Latency P95 > 200ms (5min)
- Pod restarts > 5 (10min)
- CPU usage > 90% (5min)
- Memory usage > 90% (5min)
- Available replicas < min (1min)

---

## 🔄 Disaster Recovery

### Backup Strategy

**What's Backed Up:**
- Personas configuration (daily)
- Redis snapshots (every 6h)
- Secrets (encrypted, GCP Secret Manager)
- Kubernetes manifests (version controlled)

**Recovery Time Objectives:**
- RTO: 30 minutes
- RPO: 1 hour

### Failure Scenarios

**1. Pod Failure:**
- Auto-restart by Kubernetes
- Load balanced to healthy pods
- Impact: None (if >1 healthy pod)

**2. Node Failure:**
- Pods rescheduled to other nodes
- Impact: Brief disruption (<30s)

**3. Zone Failure:**
- Multi-zone deployment (future)
- Impact: Degraded performance

**4. Region Failure:**
- Multi-region deployment (future)
- Manual failover required
- Impact: Service interruption

---

## 📚 References

- [Google Kubernetes Engine](https://cloud.google.com/kubernetes-engine)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [OAuth 2.0 Device Flow](https://oauth.net/2/device-flow/)

---

**Architecture Document Version:** 1.0
**Last Review:** 2025-11-24
**Next Review:** 2026-01-24
**Owner:** Nubem Systems Architecture Team
