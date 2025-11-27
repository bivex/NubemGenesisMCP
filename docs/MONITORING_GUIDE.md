# Monitoring Guide for NubemGenesisMCP

## Overview
This guide explains how to monitor the NubemGenesisMCP deployment on GKE using Google Cloud Monitoring (formerly Stackdriver).

---

## Built-in GKE Monitoring

### Current Status
✅ **Cloud Monitoring**: Enabled automatically with GKE
✅ **Cloud Logging**: Enabled for all pods
✅ **Resource Metrics**: CPU, Memory, Disk, Network
✅ **Application Logs**: Automatically collected

### Access Monitoring Dashboard

#### Via Google Cloud Console
```bash
# Open monitoring dashboard
https://console.cloud.google.com/monitoring/dashboards?project=nubemsgenesis-mcp

# GKE-specific metrics
https://console.cloud.google.com/kubernetes/workload?project=nubemsgenesis-mcp
```

#### Via CLI
```bash
# View recent logs
gcloud logging read "resource.type=k8s_container AND resource.labels.namespace_name=production" \
  --limit=50 \
  --project=nubemsgenesis-mcp

# View MCP server logs
kubectl logs -l app=mcp-server -n production --tail=100 -f

# View specific pod logs
kubectl logs <pod-name> -n production --tail=100 -f
```

---

## Key Metrics to Monitor

### 1. Application Health
```bash
# Check pod status
kubectl get pods -n production -w

# Check health endpoint
curl http://34.170.167.74/health

# Watch pod events
kubectl get events -n production --sort-by='.lastTimestamp'
```

**Key Indicators:**
- Pod Status: All should be "Running"
- Ready Containers: Should be "1/1" or "2/2"
- Restarts: Should be 0 or minimal
- Health Check: Should return 200 OK

### 2. Resource Utilization
```bash
# CPU and Memory usage
kubectl top pods -n production

# Node resource usage
kubectl top nodes

# Detailed resource metrics
kubectl describe pod <pod-name> -n production
```

**Thresholds:**
- CPU: < 70% average, < 90% peak
- Memory: < 80% average, < 95% peak
- Disk: < 80%
- Network: Monitor for unusual spikes

### 3. Performance Metrics
```bash
# Response time test
time curl -s http://34.170.167.74/health

# Load test (10 concurrent requests)
for i in {1..10}; do
  (curl -s http://34.170.167.74/health &)
done
```

**SLO Targets:**
- P50 Latency: < 20ms
- P95 Latency: < 100ms
- P99 Latency: < 200ms
- Error Rate: < 0.1%
- Availability: > 99.9%

### 4. Scaling Metrics
```bash
# Check HPA status
kubectl get hpa -n production

# Detailed HPA metrics
kubectl describe hpa mcp-server-hpa -n production

# Current replica count
kubectl get deployment mcp-server -n production
```

**Expected Behavior:**
- Min replicas: 3
- Max replicas: 10
- Scale up: When CPU > 70% or Memory > 80%
- Scale down: After 5 minutes below threshold

---

## Cloud Monitoring Queries

### CPU Usage Query
```sql
fetch k8s_container
| metric 'kubernetes.io/container/cpu/core_usage_time'
| filter resource.namespace_name == 'production'
| filter resource.pod_name =~ 'mcp-server-.*'
| group_by 5m, [value_core_usage_time_mean: mean(value.core_usage_time)]
| every 5m
```

### Memory Usage Query
```sql
fetch k8s_container
| metric 'kubernetes.io/container/memory/used_bytes'
| filter resource.namespace_name == 'production'
| filter resource.pod_name =~ 'mcp-server-.*'
| group_by 5m, [value_used_bytes_mean: mean(value.used_bytes)]
| every 5m
```

### Request Rate Query
```sql
fetch k8s_pod
| metric 'kubernetes.io/pod/network/received_bytes_count'
| filter resource.namespace_name == 'production'
| filter resource.pod_name =~ 'mcp-server-.*'
| group_by 1m, [value_received_bytes_count_aggregate: aggregate(value.received_bytes_count)]
| every 1m
```

---

## Alerting Configuration

### Create Alert Policies

#### 1. High CPU Alert
```bash
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="MCP Server High CPU" \
  --condition-display-name="CPU > 80%" \
  --condition-threshold-value=0.8 \
  --condition-threshold-duration=300s \
  --condition-filter='resource.type="k8s_container" AND resource.namespace_name="production" AND resource.pod_name=starts_with("mcp-server")' \
  --condition-aggregation-alignment-period=60s \
  --condition-aggregation-per-series-aligner=ALIGN_MEAN \
  --condition-comparison=COMPARISON_GT \
  --project=nubemsgenesis-mcp
```

#### 2. High Memory Alert
```bash
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="MCP Server High Memory" \
  --condition-display-name="Memory > 85%" \
  --condition-threshold-value=0.85 \
  --condition-threshold-duration=300s \
  --project=nubemsgenesis-mcp
```

#### 3. Pod Crash Alert
```bash
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="MCP Server Pod Crashes" \
  --condition-display-name="Pod restart count > 3" \
  --condition-threshold-value=3 \
  --condition-threshold-duration=600s \
  --project=nubemsgenesis-mcp
```

#### 4. Health Check Alert
```bash
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="MCP Server Health Check Failed" \
  --condition-display-name="Health check failures" \
  --condition-threshold-value=3 \
  --condition-threshold-duration=180s \
  --project=nubemsgenesis-mcp
```

### Notification Channels

#### Email Notification
```bash
gcloud alpha monitoring channels create \
  --display-name="DevOps Email" \
  --type=email \
  --channel-labels=email_address=devops@nubemsystems.com \
  --project=nubemsgenesis-mcp
```

#### Slack Notification (requires webhook)
```bash
gcloud alpha monitoring channels create \
  --display-name="Slack Alerts" \
  --type=slack \
  --channel-labels=url=https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  --project=nubemsgenesis-mcp
```

---

## Log Analysis

### View Application Logs
```bash
# All MCP server logs
kubectl logs -l app=mcp-server -n production --tail=100

# Logs from specific pod
kubectl logs mcp-server-7d8b9c5f6-abcde -n production

# Follow logs in real-time
kubectl logs -l app=mcp-server -n production -f

# Logs from previous container (after crash)
kubectl logs mcp-server-7d8b9c5f6-abcde -n production --previous
```

### Filter Logs by Severity
```bash
# Error logs only
gcloud logging read "resource.type=k8s_container
  AND resource.labels.namespace_name=production
  AND resource.labels.pod_name=~'mcp-server-.*'
  AND severity>=ERROR" \
  --limit=50 \
  --project=nubemsgenesis-mcp

# Warning and above
gcloud logging read "resource.type=k8s_container
  AND resource.labels.namespace_name=production
  AND severity>=WARNING" \
  --limit=50 \
  --project=nubemsgenesis-mcp
```

### Search Logs for Patterns
```bash
# Search for specific error
kubectl logs -l app=mcp-server -n production | grep "ERROR"

# Search for authentication issues
kubectl logs -l app=mcp-server -n production | grep -i "auth"

# Count error occurrences
kubectl logs -l app=mcp-server -n production | grep -c "ERROR"
```

---

## Dashboard Creation

### Create Custom Dashboard

1. **Via Cloud Console:**
   - Navigate to: https://console.cloud.google.com/monitoring/dashboards
   - Click "Create Dashboard"
   - Add charts for key metrics

2. **Via JSON Configuration:**

```json
{
  "displayName": "MCP Server Dashboard",
  "mosaicLayout": {
    "columns": 12,
    "tiles": [
      {
        "width": 6,
        "height": 4,
        "widget": {
          "title": "CPU Usage",
          "xyChart": {
            "dataSets": [{
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type=\"k8s_container\" AND resource.namespace_name=\"production\" AND resource.pod_name=starts_with(\"mcp-server\")",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_MEAN"
                  }
                }
              }
            }]
          }
        }
      }
    ]
  }
}
```

### Key Dashboard Widgets

1. **CPU Usage Over Time**
   - Resource: k8s_container
   - Metric: kubernetes.io/container/cpu/core_usage_time
   - Filter: namespace=production, pod=mcp-server-*

2. **Memory Usage Over Time**
   - Resource: k8s_container
   - Metric: kubernetes.io/container/memory/used_bytes
   - Filter: namespace=production, pod=mcp-server-*

3. **Request Rate**
   - Resource: k8s_pod
   - Metric: kubernetes.io/pod/network/received_bytes_count
   - Aggregation: Rate per minute

4. **Pod Count**
   - Resource: k8s_pod
   - Metric: kubernetes.io/pod/status/ready
   - Filter: namespace=production, app=mcp-server

5. **Error Rate**
   - Custom metric from logs
   - Count of ERROR severity logs
   - Rate per minute

---

## Performance Testing

### Load Testing with Apache Bench
```bash
# Install ab (if not available)
brew install apache-bench  # macOS
sudo apt-get install apache2-utils  # Linux

# Basic load test (100 requests, 10 concurrent)
ab -n 100 -c 10 http://34.170.167.74/health

# Extended load test (1000 requests, 50 concurrent)
ab -n 1000 -c 50 -k http://34.170.167.74/health

# With authentication header
ab -n 100 -c 10 -H "X-API-Key: YOUR_KEY" http://34.170.167.74/personas
```

### Load Testing with wrk
```bash
# Install wrk
brew install wrk  # macOS
sudo apt-get install wrk  # Linux

# 30 second test, 10 connections, 2 threads
wrk -t2 -c10 -d30s http://34.170.167.74/health

# With custom script for POST requests
wrk -t4 -c20 -d60s -s post.lua http://34.170.167.74/mcp
```

### Monitoring During Load Test
```bash
# Terminal 1: Run load test
ab -n 1000 -c 50 http://34.170.167.74/health

# Terminal 2: Watch pods scale
kubectl get pods -n production -w

# Terminal 3: Watch resource usage
watch kubectl top pods -n production

# Terminal 4: Watch HPA
watch kubectl get hpa -n production
```

---

## Troubleshooting

### Pod Issues
```bash
# Describe pod for events
kubectl describe pod <pod-name> -n production

# Check pod logs
kubectl logs <pod-name> -n production --tail=100

# Get pod events
kubectl get events --field-selector involvedObject.name=<pod-name> -n production

# Exec into pod for debugging
kubectl exec -it <pod-name> -n production -- /bin/bash
```

### Service Issues
```bash
# Check service endpoints
kubectl get endpoints mcp-server -n production

# Describe service
kubectl describe service mcp-server -n production

# Test service from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://mcp-server.production.svc.cluster.local/health
```

### Network Issues
```bash
# Check network policies
kubectl get networkpolicies -n production

# Test connectivity
kubectl run -it --rm debug --image=busybox --restart=Never -- \
  wget -O- http://mcp-server.production.svc.cluster.local/health

# Check DNS resolution
kubectl run -it --rm debug --image=busybox --restart=Never -- \
  nslookup mcp-server.production.svc.cluster.local
```

---

## Best Practices

### 1. Regular Health Checks
- Monitor `/health` endpoint every 30 seconds
- Set up external uptime monitoring (e.g., UptimeRobot)
- Configure proper liveness and readiness probes

### 2. Log Retention
- Keep logs for at least 30 days
- Archive important logs to Cloud Storage
- Use log-based metrics for trends

### 3. Alert Fatigue Prevention
- Set appropriate thresholds
- Use alert grouping
- Implement escalation policies
- Regular alert policy review

### 4. Capacity Planning
- Review metrics weekly
- Track growth trends
- Plan for 2x current capacity
- Test scaling limits quarterly

### 5. Incident Response
- Document runbooks
- Set up on-call rotation
- Regular incident drills
- Post-mortem for all incidents

---

## Useful Commands Reference

```bash
# Quick health check
kubectl get pods -n production && curl -s http://34.170.167.74/health | jq

# Full system status
kubectl get all -n production

# Resource usage summary
kubectl top pods -n production && kubectl top nodes

# Recent events
kubectl get events -n production --sort-by='.lastTimestamp' | tail -20

# Scale manually (for testing)
kubectl scale deployment/mcp-server -n production --replicas=5

# Restart deployment (rolling restart)
kubectl rollout restart deployment/mcp-server -n production

# Check rollout status
kubectl rollout status deployment/mcp-server -n production

# View deployment history
kubectl rollout history deployment/mcp-server -n production
```

---

## Next Steps

1. **Set up notification channels** (email, Slack)
2. **Create alert policies** for critical metrics
3. **Build custom dashboard** with key widgets
4. **Configure log exports** to BigQuery for analysis
5. **Set up external monitoring** for redundancy
6. **Document runbooks** for common incidents
7. **Schedule regular reviews** of metrics and alerts

---

## Resources

- [GKE Observability](https://cloud.google.com/kubernetes-engine/docs/how-to/monitoring)
- [Cloud Monitoring Documentation](https://cloud.google.com/monitoring/docs)
- [Cloud Logging Documentation](https://cloud.google.com/logging/docs)
- [Alert Policy Reference](https://cloud.google.com/monitoring/alerts)
- [Dashboard Samples](https://cloud.google.com/monitoring/dashboards)
