# SSL/TLS and Firewall Configuration Guide

## Overview
This guide explains how to configure SSL/TLS certificates and firewall rules for NubemGenesisMCP deployment on GKE.

---

## SSL/TLS Configuration

### Current Status
✅ **Static IP Reserved**: `34.8.49.44`
✅ **Ingress Manifest Created**: `kubernetes/production/ingress-ssl.yaml`
⚠️ **Domain Required**: SSL certificate requires a domain name

### Prerequisites
1. **Domain Name**: You need a registered domain (e.g., `mcp.nubemsystems.com`)
2. **DNS Access**: Ability to create DNS A records
3. **GKE Ingress**: Already configured in the manifest

### Setup Steps

#### 1. Configure Domain DNS
Point your domain to the reserved static IP:

```bash
# DNS A Record Configuration
Type: A
Name: mcp (or @)
Value: 34.8.49.44
TTL: 300
```

#### 2. Update Ingress Manifest
Edit `kubernetes/production/ingress-ssl.yaml` and replace `mcp.nubemsystems.com` with your actual domain.

#### 3. Deploy Ingress with SSL
```bash
kubectl apply -f kubernetes/production/ingress-ssl.yaml -n production
```

#### 4. Verify Certificate Provisioning
```bash
# Check managed certificate status
kubectl describe managedcertificate mcp-server-cert -n production

# Status should transition:
# Provisioning -> Active (takes 15-60 minutes)
```

#### 5. Verify SSL
```bash
# Once Active, test HTTPS access
curl https://mcp.nubemsystems.com/health

# Check certificate details
openssl s_client -connect mcp.nubemsystems.com:443 -servername mcp.nubemsystems.com
```

### Without Custom Domain (Current Setup)
Currently using LoadBalancer IP directly: `http://34.170.167.74`

For SSL without a domain, you would need:
- Self-signed certificate (not recommended for production)
- Or use a service like Let's Encrypt with nip.io domains
- Or configure Cloud Armor with SSL termination

---

## Firewall Rules Configuration

### Current Status
✅ **Default GKE Firewall**: Automatically created by GKE
✅ **LoadBalancer**: Exposed on port 80 (HTTP)
⚠️ **Custom Rules**: Need to be configured for enhanced security

### Recommended Firewall Rules

#### 1. Allow HTTPS Traffic
```bash
gcloud compute firewall-rules create allow-https-mcp \
  --project=nubemsgenesis-mcp \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:443 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=gke-nubemsgenesis-cluster
```

#### 2. Restrict HTTP to Specific IPs (Optional)
If you want to restrict access to specific IP ranges:

```bash
gcloud compute firewall-rules create allow-http-mcp-restricted \
  --project=nubemsgenesis-mcp \
  --direction=INGRESS \
  --priority=900 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:80 \
  --source-ranges=YOUR_OFFICE_IP/32,YOUR_VPN_IP/32 \
  --target-tags=gke-nubemsgenesis-cluster
```

#### 3. Block All Other Inbound Traffic
```bash
gcloud compute firewall-rules create deny-all-mcp \
  --project=nubemsgenesis-mcp \
  --direction=INGRESS \
  --priority=2000 \
  --network=default \
  --action=DENY \
  --rules=all \
  --source-ranges=0.0.0.0/0 \
  --target-tags=gke-nubemsgenesis-cluster
```

#### 4. Allow Health Checks from GCP
```bash
gcloud compute firewall-rules create allow-health-checks \
  --project=nubemsgenesis-mcp \
  --direction=INGRESS \
  --priority=800 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=35.191.0.0/16,130.211.0.0/22 \
  --target-tags=gke-nubemsgenesis-cluster
```

### View Current Firewall Rules
```bash
gcloud compute firewall-rules list --project=nubemsgenesis-mcp
```

### Advanced: Cloud Armor for DDoS Protection
```bash
# Create security policy
gcloud compute security-policies create mcp-armor-policy \
  --project=nubemsgenesis-mcp \
  --description="DDoS protection for MCP Server"

# Add rate limiting rule
gcloud compute security-policies rules create 1000 \
  --security-policy=mcp-armor-policy \
  --expression="true" \
  --action=rate-based-ban \
  --rate-limit-threshold-count=100 \
  --rate-limit-threshold-interval-sec=60 \
  --ban-duration-sec=600 \
  --conform-action=allow \
  --exceed-action=deny-403 \
  --enforce-on-key=IP \
  --project=nubemsgenesis-mcp

# Attach to backend service (after Ingress is created)
BACKEND_SERVICE=$(gcloud compute backend-services list --project=nubemsgenesis-mcp --filter="name~mcp" --format="value(name)")
gcloud compute backend-services update $BACKEND_SERVICE \
  --security-policy=mcp-armor-policy \
  --global \
  --project=nubemsgenesis-mcp
```

---

## Network Security Best Practices

### 1. IP Whitelisting
For production environments with known client IPs:

```yaml
# Add to mcp-server-deployment.yaml
spec:
  template:
    spec:
      containers:
      - name: mcp-server
        env:
        - name: ALLOWED_IPS
          value: "1.2.3.4,5.6.7.8,9.10.11.12"
```

### 2. API Key Security
Currently implemented in the application:
- API keys stored securely
- Rate limiting per key
- Audit logging for all requests
- Token expiration

### 3. Redis Security
```bash
# Update Redis deployment with password
kubectl create secret generic redis-password \
  --from-literal=password=$(openssl rand -base64 32) \
  -n production

# Update redis-deployment.yaml to use password
```

### 4. Network Policies
Create network policies to restrict pod-to-pod communication:

```yaml
# kubernetes/production/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-server-netpol
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: mcp-server
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: redis
    ports:
    - protocol: TCP
      port: 6379
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 53
    - protocol: UDP
      port: 53
```

---

## Monitoring and Alerts

### Firewall Logs
```bash
# Enable firewall logging
gcloud compute firewall-rules update allow-https-mcp \
  --enable-logging \
  --project=nubemsgenesis-mcp

# View logs
gcloud logging read "resource.type=gce_firewall_rule" \
  --limit=50 \
  --project=nubemsgenesis-mcp
```

### SSL Certificate Monitoring
```bash
# Check certificate expiration
kubectl get managedcertificate mcp-server-cert -n production -o yaml

# Set up alert for certificate renewal issues
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="MCP SSL Certificate Alert" \
  --condition-display-name="Certificate not Active" \
  --condition-threshold-value=1 \
  --condition-threshold-duration=300s
```

---

## Troubleshooting

### SSL Certificate Stuck in Provisioning
1. Verify DNS is pointing to correct IP: `dig mcp.nubemsystems.com`
2. Check Ingress status: `kubectl describe ingress mcp-server-ingress -n production`
3. Verify certificate: `kubectl describe managedcertificate mcp-server-cert -n production`
4. Wait 15-60 minutes for provisioning

### Firewall Blocking Traffic
1. Check firewall rules: `gcloud compute firewall-rules list`
2. Verify GKE node tags: `gcloud compute instances list --filter="name~gke-nubemsgenesis"`
3. Test connectivity: `telnet 34.8.49.44 80`

### Health Checks Failing
1. Verify health check source ranges are allowed: `35.191.0.0/16,130.211.0.0/22`
2. Check pod logs: `kubectl logs -l app=mcp-server -n production`
3. Verify port 8080 is accessible within cluster

---

## Quick Reference

### Current Configuration
- **LoadBalancer IP**: 34.170.167.74
- **Reserved Static IP**: 34.8.49.44
- **Ingress**: Ready to deploy (domain required)
- **SSL**: Infrastructure ready (domain required)
- **Firewall**: Default GKE rules active

### Next Steps
1. Register/configure domain name
2. Update DNS A record to 34.8.49.44
3. Update ingress-ssl.yaml with domain
4. Deploy Ingress
5. Wait for SSL certificate provisioning
6. Configure custom firewall rules
7. Enable Cloud Armor (optional)

### Testing Endpoints
```bash
# HTTP (current)
curl http://34.170.167.74/health

# HTTPS (after SSL setup)
curl https://mcp.nubemsystems.com/health

# With authentication
curl -H "X-API-Key: YOUR_KEY" https://mcp.nubemsystems.com/personas
```
