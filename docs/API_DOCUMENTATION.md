# NubemGenesisMCP API Documentation

## Base URL
```
Production: http://34.170.167.74
```

## Authentication

All protected endpoints require authentication using one of the following methods:

### 1. API Key Authentication
```http
X-API-Key: your_api_key_here
```

### 2. Bearer Token Authentication
```http
Authorization: Bearer your_token_here
```

### 3. OAuth 2.0 Device Flow
See [Authentication Flow](#oauth-20-device-flow) section below.

---

## Endpoints

### Health Check

#### `GET /health`
Returns the health status of the service.

**Authentication:** Not required

**Request:**
```bash
curl http://34.170.167.74/health
```

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "service": "NubemSuperFClaude MCP Server",
  "version": "1.2.0-auth",
  "features": {
    "authentication": true,
    "authorization": true,
    "rate_limiting": true,
    "audit_logging": true
  },
  "timestamp": "2025-11-27T10:30:00Z"
}
```

---

### Personas

#### `GET /personas`
List all available AI personas.

**Authentication:** Required

**Query Parameters:**
- `category` (optional): Filter by category
- `limit` (optional): Maximum personas to return (1-100, default: 50)
- `offset` (optional): Pagination offset (default: 0)
- `summary_only` (optional): Return only key and name (default: false)

**Request:**
```bash
curl -H "X-API-Key: YOUR_KEY" \
  "http://34.170.167.74/personas?limit=10&category=development"
```

**Response:** `200 OK`
```json
{
  "personas": [
    {
      "key": "senior-developer",
      "name": "Senior Full-Stack Developer",
      "category": "development",
      "description": "Expert in modern web development",
      "specialties": ["React", "Node.js", "Python", "AWS"],
      "use_cases": ["Feature development", "Architecture design", "Code review"]
    },
    {
      "key": "devops-engineer",
      "name": "DevOps Engineer",
      "category": "operations",
      "description": "CI/CD and infrastructure expert",
      "specialties": ["Docker", "Kubernetes", "Terraform", "Jenkins"],
      "use_cases": ["Deployment automation", "Infrastructure management"]
    }
  ],
  "total": 141,
  "limit": 10,
  "offset": 0
}
```

**Error Response:** `401 Unauthorized`
```json
{
  "error": "Authentication required",
  "message": "Missing or invalid API key"
}
```

---

#### `GET /personas/{key}`
Get detailed information about a specific persona.

**Authentication:** Required

**Path Parameters:**
- `key`: Persona identifier (e.g., "senior-developer")

**Request:**
```bash
curl -H "X-API-Key: YOUR_KEY" \
  http://34.170.167.74/personas/senior-developer
```

**Response:** `200 OK`
```json
{
  "key": "senior-developer",
  "name": "Senior Full-Stack Developer",
  "category": "development",
  "description": "Experienced full-stack developer with expertise in modern web technologies",
  "specialties": [
    "React",
    "Node.js",
    "Python",
    "TypeScript",
    "AWS",
    "PostgreSQL"
  ],
  "use_cases": [
    "Feature development",
    "Architecture design",
    "Code review",
    "Performance optimization"
  ],
  "capabilities": {
    "languages": ["JavaScript", "TypeScript", "Python", "Java"],
    "frameworks": ["React", "Next.js", "Express", "Django"],
    "databases": ["PostgreSQL", "MongoDB", "Redis"],
    "cloud": ["AWS", "GCP", "Azure"]
  },
  "instructions": "Expert developer focusing on clean code and best practices..."
}
```

**Error Response:** `404 Not Found`
```json
{
  "error": "Persona not found",
  "message": "No persona with key 'invalid-key'"
}
```

---

### Orchestration

#### `POST /orchestrate`
Execute a task using persona orchestration.

**Authentication:** Required

**Request Body:**
```json
{
  "task": "Review this Python code for security vulnerabilities",
  "strategy": "persona",
  "context": {
    "code": "def login(username, password):\n    query = f\"SELECT * FROM users WHERE username='{username}' AND password='{password}'\""
  }
}
```

**Request:**
```bash
curl -X POST http://34.170.167.74/orchestrate \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Review this code for security issues",
    "strategy": "persona"
  }'
```

**Response:** `200 OK`
```json
{
  "result": {
    "analysis": "SQL injection vulnerability detected...",
    "recommendations": [
      "Use parameterized queries",
      "Implement input validation",
      "Hash passwords before storage"
    ],
    "severity": "high"
  },
  "persona_used": "security-expert",
  "strategy": "persona",
  "execution_time_ms": 245,
  "timestamp": "2025-11-27T10:30:00Z"
}
```

**Strategies:**
- `persona`: Use single best-fit persona
- `optimized`: Use swarm collaboration for complex tasks

---

### MCP JSON-RPC Endpoint

#### `POST /mcp`
Execute MCP protocol requests (JSON-RPC 2.0).

**Authentication:** Required

**Request Body (JSON-RPC 2.0):**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/list",
  "params": {},
  "id": 1
}
```

**Request:**
```bash
curl -X POST http://34.170.167.74/mcp \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "params": {},
    "id": 1
  }'
```

**Response:** `200 OK`
```json
{
  "jsonrpc": "2.0",
  "result": {
    "tools": [
      {
        "name": "intelligent_respond",
        "description": "TRINITY: Auto-routing AI system",
        "inputSchema": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "User query or task"
            }
          },
          "required": ["query"]
        }
      },
      {
        "name": "orchestrate",
        "description": "Orchestrate task using personas",
        "inputSchema": {
          "type": "object",
          "properties": {
            "task": {
              "type": "string"
            },
            "strategy": {
              "type": "string",
              "enum": ["persona", "optimized"]
            }
          },
          "required": ["task"]
        }
      }
    ]
  },
  "id": 1
}
```

---

### Available MCP Methods

#### `tools/list`
List all available tools.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/list",
  "params": {},
  "id": 1
}
```

#### `tools/call`
Execute a specific tool.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "intelligent_respond",
    "arguments": {
      "query": "Explain quantum computing"
    }
  },
  "id": 2
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Quantum computing is a revolutionary approach..."
      }
    ]
  },
  "id": 2
}
```

---

## OAuth 2.0 Device Flow

### Step 1: Request Device Code

#### `POST /auth/device/code`
Initiate the device authorization flow.

**Authentication:** Not required

**Request:**
```bash
curl -X POST http://34.170.167.74/auth/device/code \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:** `200 OK`
```json
{
  "device_code": "GmRhmhcxhwAzkoEqiMEg_DnyEysNkuNhszIySk9eS",
  "user_code": "WDJB-MJHT",
  "verification_uri": "http://34.170.167.74/device",
  "expires_in": 1800,
  "interval": 5
}
```

### Step 2: User Authorization
User visits `verification_uri` and enters `user_code`.

### Step 3: Poll for Token

#### `POST /auth/device/token`
Exchange device code for access token.

**Authentication:** Not required

**Request:**
```bash
curl -X POST http://34.170.167.74/auth/device/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    "device_code": "GmRhmhcxhwAzkoEqiMEg_DnyEysNkuNhszIySk9eS",
    "client_id": "nubemsfc-client"
  }'
```

**Response (Pending):** `400 Bad Request`
```json
{
  "error": "authorization_pending",
  "error_description": "User has not yet authorized the device"
}
```

**Response (Success):** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "tGzv3JOkF0XG5Qx2TlKWIA",
  "scope": "read write"
}
```

**Response (Expired):** `400 Bad Request`
```json
{
  "error": "expired_token",
  "error_description": "The device code has expired"
}
```

---

## Rate Limiting

### Default Limits
- **Authenticated requests**: 1000 requests/hour per API key
- **Unauthenticated requests**: 60 requests/hour per IP
- **Burst limit**: 10 requests/second

### Rate Limit Headers
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1701097200
```

### Rate Limit Exceeded Response
`429 Too Many Requests`
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please retry after 3600 seconds.",
  "retry_after": 3600
}
```

---

## Error Responses

### Standard Error Format
```json
{
  "error": "error_code",
  "message": "Human-readable error description",
  "details": {
    "field": "Additional context"
  },
  "timestamp": "2025-11-27T10:30:00Z"
}
```

### HTTP Status Codes
- `200 OK`: Success
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily unavailable

---

## Request/Response Examples

### Example 1: List Personas with Filtering
```bash
curl -H "X-API-Key: nsfc_user_abc123..." \
  "http://34.170.167.74/personas?category=security&limit=5&summary_only=true"
```

**Response:**
```json
{
  "personas": [
    {"key": "security-expert", "name": "Security Expert"},
    {"key": "penetration-tester", "name": "Penetration Tester"},
    {"key": "security-architect", "name": "Security Architect"},
    {"key": "compliance-officer", "name": "Compliance Officer"},
    {"key": "incident-responder", "name": "Incident Responder"}
  ],
  "total": 10,
  "limit": 5,
  "offset": 0
}
```

### Example 2: Intelligent Task Execution
```bash
curl -X POST http://34.170.167.74/mcp \
  -H "X-API-Key: nsfc_user_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "intelligent_respond",
      "arguments": {
        "query": "Design a microservices architecture for e-commerce"
      }
    },
    "id": 1
  }'
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "# Microservices Architecture Design for E-Commerce\n\n## Core Services\n1. User Service...\n2. Product Catalog Service...\n3. Order Service...\n..."
      }
    ],
    "strategy": "swarm",
    "personas_used": ["system-architect", "senior-developer", "devops-engineer"],
    "execution_time_ms": 1250
  },
  "id": 1
}
```

### Example 3: OAuth Device Flow Complete Example
```bash
# Step 1: Get device code
RESPONSE=$(curl -s -X POST http://34.170.167.74/auth/device/code -H "Content-Type: application/json" -d '{}')
DEVICE_CODE=$(echo $RESPONSE | jq -r '.device_code')
USER_CODE=$(echo $RESPONSE | jq -r '.user_code')
VERIFICATION_URI=$(echo $RESPONSE | jq -r '.verification_uri')

echo "Visit $VERIFICATION_URI and enter code: $USER_CODE"

# Step 2: Poll for token (every 5 seconds)
while true; do
  TOKEN_RESPONSE=$(curl -s -X POST http://34.170.167.74/auth/device/token \
    -H "Content-Type: application/json" \
    -d "{
      \"grant_type\": \"urn:ietf:params:oauth:grant-type:device_code\",
      \"device_code\": \"$DEVICE_CODE\",
      \"client_id\": \"nubemsfc-client\"
    }")

  ERROR=$(echo $TOKEN_RESPONSE | jq -r '.error // empty')

  if [ -z "$ERROR" ]; then
    ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')
    echo "Success! Access token: $ACCESS_TOKEN"
    break
  elif [ "$ERROR" == "authorization_pending" ]; then
    echo "Waiting for user authorization..."
    sleep 5
  else
    echo "Error: $ERROR"
    break
  fi
done

# Step 3: Use token
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://34.170.167.74/personas
```

---

## Client SDKs

### Python
```python
import requests

class NubemGenesisMCPClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}

    def list_personas(self, category=None, limit=50):
        params = {"limit": limit}
        if category:
            params["category"] = category

        response = requests.get(
            f"{self.base_url}/personas",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()

    def orchestrate(self, task, strategy="persona"):
        response = requests.post(
            f"{self.base_url}/orchestrate",
            headers=self.headers,
            json={"task": task, "strategy": strategy}
        )
        response.raise_for_status()
        return response.json()

# Usage
client = NubemGenesisMCPClient(
    base_url="http://34.170.167.74",
    api_key="nsfc_user_abc123..."
)

personas = client.list_personas(category="development", limit=10)
result = client.orchestrate("Review this code for bugs")
```

### JavaScript/Node.js
```javascript
class NubemGenesisMCPClient {
  constructor(baseUrl, apiKey) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
  }

  async listPersonas(category = null, limit = 50) {
    const params = new URLSearchParams({ limit });
    if (category) params.append('category', category);

    const response = await fetch(`${this.baseUrl}/personas?${params}`, {
      headers: { 'X-API-Key': this.apiKey }
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }

  async orchestrate(task, strategy = 'persona') {
    const response = await fetch(`${this.baseUrl}/orchestrate`, {
      method: 'POST',
      headers: {
        'X-API-Key': this.apiKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ task, strategy })
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }
}

// Usage
const client = new NubemGenesisMCPClient(
  'http://34.170.167.74',
  'nsfc_user_abc123...'
);

const personas = await client.listPersonas('development', 10);
const result = await client.orchestrate('Review this code for bugs');
```

---

## Best Practices

### 1. Authentication
- **Store API keys securely**: Use environment variables or secret management
- **Rotate keys regularly**: Every 90 days minimum
- **Use least privilege**: Request only necessary permissions

### 2. Error Handling
- **Implement retries**: With exponential backoff for 5xx errors
- **Handle rate limits**: Respect `Retry-After` header
- **Log errors**: For debugging and monitoring

### 3. Performance
- **Use pagination**: For large result sets
- **Cache responses**: When data doesn't change frequently
- **Batch requests**: Where possible to reduce overhead

### 4. Security
- **Use HTTPS**: In production (currently HTTP, SSL setup pending)
- **Validate inputs**: Before sending to API
- **Never log API keys**: Mask sensitive data in logs

---

## Support

### Documentation
- **Architecture**: See `docs/ARCHITECTURE.md`
- **Deployment**: See `DEPLOYMENT_SUCCESS.md`
- **Monitoring**: See `docs/MONITORING_GUIDE.md`

### Contact
- **Repository**: https://github.com/NUbem000/NubemGenesisMCP
- **Issues**: https://github.com/NUbem000/NubemGenesisMCP/issues

---

## Changelog

### v1.2.0-auth (Current)
- OAuth 2.0 Device Flow authentication
- API key authentication
- Rate limiting
- Audit logging
- 141 AI personas
- Trinity Router (4 strategies)
- Meta-MCP orchestration

### Future Releases
- HTTPS/SSL support
- WebSocket streaming
- Batch operations
- GraphQL endpoint
- Enhanced monitoring
