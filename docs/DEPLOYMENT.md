# Dynamic Grid Trading System - Deployment Guide

## Quick Start Deployment

### Prerequisites
```bash
# System requirements
Python 3.8+
Redis (optional, for distributed state)
16GB RAM minimum
SSD storage for state persistence
Stable internet connection (< 50ms latency to Bybit)
```

### 1. Environment Setup
```bash
# Clone and setup
git clone <your-repo>
cd dynamic-grid

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration
```bash
# Copy example configurations
cp symbols.yaml.example symbols.yaml
cp .env.example .env

# Edit configuration files
nano symbols.yaml  # Trading pairs and parameters
nano .env          # API credentials and settings
```

### 3. Initial Validation
```bash
# Test connectivity and credentials
export TRADING_MODE=testnet
python src/multi_bot/main.py --validate-only

# Run paper trading test
export TRADING_MODE=paper
python src/multi_bot/main.py --config symbols.yaml --duration 300
```

### 4. Production Deployment
```bash
# Final production startup
export TRADING_MODE=production
export LOG_LEVEL=INFO
python src/multi_bot/main.py --config symbols.yaml
```

---

## Detailed Configuration

### API Configuration (.env)
```bash
# Bybit API credentials
BYBIT_API_KEY=your_production_key
BYBIT_SECRET=your_production_secret

# Trading mode: production, testnet, paper
TRADING_MODE=production

# Logging configuration
LOG_LEVEL=INFO
LOG_FILE_PATH=logs/grid_trading.log
LOG_MAX_SIZE=100MB
LOG_BACKUP_COUNT=10

# State persistence
STATE_DIR=data/state
BACKUP_DIR=data/backups
BACKUP_RETENTION_HOURS=168  # 7 days

# Monitoring endpoints
METRICS_PORT=8000
HEALTH_PORT=8001
KILL_SWITCH_TOKEN=secure_random_token_here

# Redis (optional)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=optional_password
```

### Trading Configuration (symbols.yaml)
```yaml
# Global settings
global:
  capital_limits:
    max_notional_exposure: 50000    # Maximum $ exposure
    daily_loss_limit: 1000          # Daily stop loss
    min_balance_threshold: 1000     # Minimum account balance
    max_orders_per_symbol: 50       # Order count limit
    max_position_size_ratio: 0.1    # 10% of balance max position
  
  grid_defaults:
    spacing_percentage: 0.002       # 0.2% grid spacing
    num_levels: 20                  # Grid levels per side
    base_quantity_ratio: 0.01       # 1% of balance per order
    rebalance_threshold: 0.05       # 5% price move triggers rebalance
  
  risk_management:
    kill_switch_enabled: true
    max_drawdown_percent: 5.0       # 5% daily drawdown limit
    volatility_adjustment: true     # Enable ATR-based sizing
    position_timeout_hours: 24      # Close stale positions
  
  observability:
    structured_logging: true
    metrics_enabled: true
    health_checks: true
    alert_endpoints:
      - "https://hooks.slack.com/your-webhook"
      - "smtp://alerts@yourcompany.com"

# Symbol-specific configurations
symbols:
  BTCUSDT:
    enabled: true
    grid:
      spacing_percentage: 0.001     # Tighter spread for BTC
      num_levels: 25
      base_quantity: 0.01           # Fixed quantity override
    risk:
      max_position_size: 0.5        # 50% of capital max
      volatility_multiplier: 1.2    # Higher vol adjustment
  
  ETHUSDT:
    enabled: true
    grid:
      spacing_percentage: 0.002
      num_levels: 20
      base_quantity_ratio: 0.015    # 1.5% of balance
    risk:
      max_position_size: 0.3
      volatility_multiplier: 1.0
  
  SOLUSDT:
    enabled: false                  # Disabled for now
    grid:
      spacing_percentage: 0.003
      num_levels: 15
    risk:
      max_position_size: 0.1
      volatility_multiplier: 0.8
```

---

## Infrastructure Requirements

### Server Specifications

**Minimum Requirements:**
- CPU: 4 cores, 2.5GHz+
- RAM: 16GB
- Storage: 100GB SSD
- Network: 1Gbps with < 50ms latency to Singapore

**Recommended Production:**
- CPU: 8 cores, 3.0GHz+ 
- RAM: 32GB
- Storage: 500GB NVMe SSD
- Network: 10Gbps with < 20ms latency
- Redundant internet connections

### Network Configuration
```bash
# Bybit endpoints to whitelist
stream.bybit.com           # WebSocket
api.bybit.com             # REST API  
api-testnet.bybit.com     # Testnet API

# Required ports
443/TCP                   # HTTPS API calls
80/TCP                    # HTTP redirects
8000/TCP                  # Metrics endpoint (internal)
8001/TCP                  # Health/kill switch (internal)
```

### Security Hardening
```bash
# File permissions
chmod 600 .env                    # Protect credentials
chmod 600 data/state/*           # Protect state files
chmod 755 src/multi_bot/         # Executable access
chown -R trader:trader .         # Proper ownership

# Firewall configuration (UFW example)
ufw default deny incoming
ufw default allow outgoing
ufw allow from 10.0.0.0/8 to any port 8000    # Metrics
ufw allow from 10.0.0.0/8 to any port 8001    # Health
ufw enable
```

---

## Docker Deployment

### Dockerfile
```dockerfile
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r trader && useradd -r -g trader trader

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY symbols.yaml.example ./symbols.yaml

# Create data directories
RUN mkdir -p data/state data/backups logs && \
    chown -R trader:trader /app

# Switch to non-root user
USER trader

# Expose ports
EXPOSE 8000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
  CMD curl -f http://localhost:8001/health || exit 1

# Default command
CMD ["python", "src/multi_bot/main.py", "--config", "symbols.yaml"]
```

### Docker Compose
```yaml
version: '3.8'

services:
  grid-trader:
    build: .
    container_name: dynamic-grid-trader
    restart: unless-stopped
    
    environment:
      - TRADING_MODE=production
      - LOG_LEVEL=INFO
      - PYTHONUNBUFFERED=1
    
    env_file:
      - .env
    
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./symbols.yaml:/app/symbols.yaml:ro
    
    ports:
      - "8000:8000"  # Metrics
      - "8001:8001"  # Health/Control
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"

  redis:
    image: redis:7-alpine
    container_name: grid-redis
    restart: unless-stopped
    
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    
    volumes:
      - redis-data:/data
    
    ports:
      - "6379:6379"

  prometheus:
    image: prom/prometheus:latest
    container_name: grid-prometheus
    restart: unless-stopped
    
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    
    ports:
      - "9090:9090"

volumes:
  redis-data:
  prometheus-data:
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dynamic-grid-trader
  labels:
    app: dynamic-grid-trader
spec:
  replicas: 1  # Single instance for state consistency
  selector:
    matchLabels:
      app: dynamic-grid-trader
  
  template:
    metadata:
      labels:
        app: dynamic-grid-trader
    spec:
      containers:
      - name: grid-trader
        image: your-registry/dynamic-grid:latest
        
        env:
        - name: TRADING_MODE
          value: "production"
        - name: LOG_LEVEL
          value: "INFO"
        
        envFrom:
        - secretRef:
            name: bybit-credentials
        - configMapRef:
            name: grid-config
        
        ports:
        - containerPort: 8000
          name: metrics
        - containerPort: 8001
          name: health
        
        volumeMounts:
        - name: state-storage
          mountPath: /app/data
        - name: config
          mountPath: /app/symbols.yaml
          subPath: symbols.yaml
        
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        
        livenessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 60
          periodSeconds: 30
        
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 30
          periodSeconds: 10

      volumes:
      - name: state-storage
        persistentVolumeClaim:
          claimName: grid-state-pvc
      - name: config
        configMap:
          name: grid-symbols-config

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grid-state-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: fast-ssd
```

---

## Monitoring Setup

### Prometheus Configuration
```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

scrape_configs:
  - job_name: 'dynamic-grid'
    static_configs:
      - targets: ['grid-trader:8000']
    scrape_interval: 10s
    metrics_path: /metrics

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### Grafana Dashboards
```json
{
  "dashboard": {
    "title": "Dynamic Grid Trading",
    "panels": [
      {
        "title": "P&L Over Time",
        "type": "graph",
        "targets": [
          {
            "expr": "grid_pnl_realized",
            "legendFormat": "Realized P&L"
          },
          {
            "expr": "grid_pnl_unrealized", 
            "legendFormat": "Unrealized P&L"
          }
        ]
      },
      {
        "title": "Active Orders",
        "type": "stat",
        "targets": [
          {
            "expr": "grid_orders_active",
            "legendFormat": "Open Orders"
          }
        ]
      },
      {
        "title": "API Performance",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(api_requests_total[5m])",
            "legendFormat": "Requests/sec"
          },
          {
            "expr": "rate(api_errors_total[5m])",
            "legendFormat": "Errors/sec"
          }
        ]
      }
    ]
  }
}
```

---

## Testing Procedures

### Pre-Production Testing

**1. Unit Tests**
```bash
# Run comprehensive test suite
python -m pytest tests/ -v --cov=src/multi_bot --cov-report=html

# Test specific components
python -m pytest tests/test_bybit_filters.py -v
python -m pytest tests/test_state_manager.py -v
python -m pytest tests/test_kill_switch.py -v
```

**2. Integration Testing**
```bash
# Testnet integration (24 hours minimum)
export TRADING_MODE=testnet
export TEST_DURATION=86400
python src/multi_bot/main.py --config symbols.yaml --test-mode

# Paper trading validation (72 hours recommended)
export TRADING_MODE=paper
python src/multi_bot/main.py --config symbols.yaml --duration 259200
```

**3. Stress Testing**
```bash
# High-frequency trading simulation
export GRID_LEVELS=50
export GRID_SPACING=0.0005
export TRADING_MODE=paper
python src/multi_bot/main.py --config symbols.yaml --stress-test

# Kill switch response time test
python tests/test_kill_switch_response.py
```

### Production Validation Checklist

**System Health:**
- [ ] All WebSocket connections stable
- [ ] State persistence working correctly
- [ ] Metrics being collected
- [ ] Alerts configured and tested
- [ ] Kill switch responds < 2 seconds
- [ ] Backup rotation functioning

**Trading Functionality:**
- [ ] Orders being placed within precision limits
- [ ] Grid rebalancing working correctly
- [ ] P&L calculations accurate
- [ ] Position management functioning
- [ ] Risk limits being enforced

**Performance:**
- [ ] Order placement latency < 100ms
- [ ] Memory usage stable < 2GB
- [ ] CPU usage < 50% average
- [ ] Network utilization optimal
- [ ] No memory leaks detected

---

## Rollback Procedures

### Emergency Rollback
```bash
# 1. Immediate stop
curl -X POST http://localhost:8001/kill-switch/activate

# 2. Stop all processes
pkill -f "main.py"

# 3. Restore previous version
git checkout HEAD~1
pip install -r requirements.txt

# 4. Restore state backup
cp data/backups/state_backup_safe.json data/state/

# 5. Restart previous version
export TRADING_MODE=production
python src/multi_bot/main.py --config symbols.yaml
```

### Planned Rollback
```bash
# 1. Graceful shutdown
curl -X POST http://localhost:8001/shutdown?graceful=true

# 2. Wait for all orders to complete
sleep 60

# 3. Backup current state
cp data/state/ data/rollback_backup_$(date +%s)

# 4. Deploy previous version
git checkout stable-branch
pip install -r requirements.txt

# 5. Restart with validation
python src/multi_bot/main.py --validate-only
python src/multi_bot/main.py --config symbols.yaml
```

---

## Performance Tuning

### Python Optimization
```bash
# Use faster JSON library
pip install orjson

# Enable Python optimizations
export PYTHONOPTIMIZE=1

# Use uvloop for async operations
pip install uvloop
```

### System Tuning
```bash
# Increase file descriptor limits
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# Optimize network buffer sizes
echo 'net.core.rmem_max = 67108864' >> /etc/sysctl.conf
echo 'net.core.wmem_max = 67108864' >> /etc/sysctl.conf
sysctl -p

# Set CPU governor for performance
echo performance > /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

### Database Optimization (Redis)
```bash
# Redis memory optimization
redis-cli CONFIG SET maxmemory 2gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Persistence tuning
redis-cli CONFIG SET save "900 1 300 10 60 10000"
redis-cli CONFIG SET stop-writes-on-bgsave-error no
```

---

This completes the production deployment guide for the dynamic grid trading system. The system is now ready for production use with comprehensive monitoring, safety controls, and operational procedures.