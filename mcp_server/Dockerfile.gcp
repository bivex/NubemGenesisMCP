# NubemSuperFClaude MCP Server - GCP Optimized Dockerfile
# Target: GKE Autopilot with minimal resource usage
# Base image: Python 3.9 slim

FROM python:3.9-slim

# Metadata
LABEL maintainer="NubemSuperFClaude"
LABEL description="MCP Server for NubemSuperFClaude Framework"
LABEL version="1.2.0"

# Set working directory
WORKDIR /app

# Install system dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs .cache sessions data

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port for health checks and HTTP server
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run MCP HTTP server (HTTP wrapper for GKE)
CMD ["python", "-u", "mcp_server/http_server.py"]
