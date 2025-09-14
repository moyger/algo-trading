# Docker Usage Guide

## Quick Start

### 1. Configure Environment Variables

Copy and edit the environment configuration file:

```bash
cp env.example .env
```

Edit the `.env` file to set necessary configurations:

```bash
# Exchange configuration
EXCHANGE=gate  # or binance
CONTRACT_TYPE=USDT  # Contract type (only required for Binance)

# API configuration
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here

# Trading configuration
COIN_NAME=X
GRID_SPACING=0.004
INITIAL_QUANTITY=1
LEVERAGE=20

# Telegram notification configuration (optional)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
ENABLE_NOTIFICATIONS=true
NOTIFICATION_INTERVAL=3600
```

### 2. Build and Run

#### Using Docker Compose (Recommended)

```bash
# Build image
docker-compose -f docker/docker-compose.yml build

# Run container
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f
```

#### Using Deploy Script (Simplified)

```bash
# Build and start
./scripts/deploy.sh build
./scripts/deploy.sh start

# Or directly start multi-currency mode
./scripts/deploy.sh multi-start

# View logs
./scripts/deploy.sh logs
```

## Container Management

### Basic Operations

```bash
# Start container
docker-compose -f docker/docker-compose.yml up -d

# Stop container
docker-compose -f docker/docker-compose.yml down

# Restart container
docker-compose -f docker/docker-compose.yml restart

# View container status
docker-compose -f docker/docker-compose.yml ps
```

### Log Management

```bash
# Real-time logs
docker-compose -f docker/docker-compose.yml logs -f

# View specific service logs
docker-compose -f docker/docker-compose.yml logs -f grid-trader

# View last 100 lines
docker-compose -f docker/docker-compose.yml logs --tail=100

# View logs for specific time range
docker-compose -f docker/docker-compose.yml logs --since="2024-01-15T10:00:00"
```

### Container Shell Access

```bash
# Enter running container
docker exec -it grid-trader bash

# Run one-time command
docker exec grid-trader python3 health_check.py

# Check Python environment
docker exec grid-trader python3 --version
```

## Docker Configuration

### docker-compose.yml Structure

```yaml
version: '3.8'

services:
  grid-trader:
    build: 
      context: ..
      dockerfile: docker/Dockerfile
    container_name: grid-trader
    restart: unless-stopped
    
    environment:
      - PYTHONUNBUFFERED=1
    
    env_file:
      - ../.env
    
    volumes:
      - ../log:/app/log
      - ../symbols.yaml:/app/symbols.yaml:ro
    
    ports:
      - "8000:8000"  # Health check port
    
    healthcheck:
      test: ["CMD", "python3", "health_check.py"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
```

### Dockerfile Explanation

```dockerfile
# Use Python 3.9 slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Create non-root user for security
RUN groupadd -r trader && useradd -r -g trader trader
RUN chown -R trader:trader /app

# Create log directory
RUN mkdir -p log && chown trader:trader log

# Switch to non-root user
USER trader

# Expose health check port
EXPOSE 8000

# Default command
CMD ["python3", "src/multi_bot/multi_bot.py"]
```

## Volume Management

### Persistent Data

```bash
# Create named volumes for data persistence
docker volume create grid-trader-logs
docker volume create grid-trader-data

# Use volumes in docker-compose.yml
volumes:
  - grid-trader-logs:/app/log
  - grid-trader-data:/app/data
```

### Bind Mounts

```bash
# Mount local directories
volumes:
  - ./log:/app/log                    # Log files
  - ./symbols.yaml:/app/symbols.yaml:ro  # Configuration (read-only)
  - ./data:/app/data                  # State data
```

## Environment-Specific Configuration

### Development Environment

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  grid-trader:
    build: 
      context: ..
      dockerfile: docker/Dockerfile.dev
    
    environment:
      - LOG_LEVEL=DEBUG
      - TRADING_MODE=testnet
    
    volumes:
      - ../src:/app/src:ro  # Mount source code for development
    
    ports:
      - "8000:8000"  # Health check
      - "5678:5678"  # Debug port
```

### Production Environment

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  grid-trader:
    image: grid-trader:latest
    
    environment:
      - LOG_LEVEL=INFO
      - TRADING_MODE=production
    
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"
    
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
        max_attempts: 3
```

## Health Monitoring

### Health Check Configuration

```yaml
healthcheck:
  test: ["CMD", "python3", "health_check.py"]
  interval: 30s      # Check every 30 seconds
  timeout: 10s       # Timeout after 10 seconds
  retries: 3         # Retry 3 times
  start_period: 60s  # Wait 60s before first check
```

### Health Check Commands

```bash
# Check container health status
docker inspect grid-trader --format='{{.State.Health.Status}}'

# View health check logs
docker inspect grid-trader --format='{{json .State.Health}}'

# Manual health check
docker exec grid-trader python3 health_check.py
```

## Performance Monitoring

### Resource Monitoring

```bash
# Monitor real-time resource usage
docker stats grid-trader

# Monitor all containers
docker stats

# View resource limits
docker inspect grid-trader | grep -A 10 "Resources"
```

### Performance Tuning

```yaml
# Optimize for production
deploy:
  resources:
    limits:
      memory: 1G        # Adjust based on currency count
      cpus: '1.0'       # Adjust based on workload
    reservations:
      memory: 512M      # Minimum guaranteed memory
      cpus: '0.5'       # Minimum guaranteed CPU
```

## Troubleshooting

### Common Issues

**Issue 1: Container won't start**
```bash
# Check container logs
docker-compose -f docker/docker-compose.yml logs grid-trader

# Check if ports are already in use
netstat -tulpn | grep 8000

# Rebuild image
docker-compose -f docker/docker-compose.yml build --no-cache
```

**Issue 2: Permission errors**
```bash
# Check log directory permissions
ls -la log/

# Fix permissions
sudo chown -R $USER:$USER log/
chmod 755 log/
```

**Issue 3: Configuration not loaded**
```bash
# Verify environment file
docker exec grid-trader env | grep API_KEY

# Check mounted volumes
docker inspect grid-trader | grep -A 20 "Mounts"
```

**Issue 4: Health check failing**
```bash
# Run health check manually
docker exec grid-trader python3 health_check.py

# Check Python environment
docker exec grid-trader python3 -c "import sys; print(sys.path)"
```

### Debug Mode

```bash
# Run container with debug output
docker-compose -f docker/docker-compose.yml up --no-daemon

# Access container shell
docker exec -it grid-trader bash

# Run with debug logging
docker exec grid-trader python3 src/multi_bot/multi_bot.py --debug
```

## Multi-Container Setup

### Load Balancer Configuration

```yaml
version: '3.8'

services:
  grid-trader-1:
    build: .
    environment:
      - INSTANCE_ID=1
      - SYMBOLS=BTCUSDT,ETHUSDT
  
  grid-trader-2:
    build: .
    environment:
      - INSTANCE_ID=2
      - SYMBOLS=ADAUSDT,SOLUSDT
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - grid-trader-1
      - grid-trader-2
```

### Database Integration

```yaml
services:
  grid-trader:
    depends_on:
      - redis
      - postgres
  
  redis:
    image: redis:alpine
    volumes:
      - redis-data:/data
  
  postgres:
    image: postgres:13
    environment:
      POSTGRES_DB: grid_trading
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  redis-data:
  postgres-data:
```

## Security Best Practices

### Container Security

```yaml
# Run as non-root user
user: "1000:1000"

# Read-only root filesystem
read_only: true

# No new privileges
security_opt:
  - no-new-privileges:true

# Limited capabilities
cap_drop:
  - ALL
cap_add:
  - NET_BIND_SERVICE
```

### Secrets Management

```yaml
# Use Docker secrets
secrets:
  api_key:
    file: ./secrets/api_key.txt
  api_secret:
    file: ./secrets/api_secret.txt

services:
  grid-trader:
    secrets:
      - api_key
      - api_secret
```

## Backup and Recovery

### Data Backup

```bash
# Backup volumes
docker run --rm -v grid-trader-logs:/data -v $(pwd):/backup alpine tar czf /backup/logs-backup-$(date +%Y%m%d).tar.gz /data

# Backup container configuration
docker inspect grid-trader > grid-trader-config-$(date +%Y%m%d).json
```

### Disaster Recovery

```bash
# Save container as image
docker commit grid-trader grid-trader-backup:$(date +%Y%m%d)

# Export container
docker save grid-trader-backup:$(date +%Y%m%d) | gzip > grid-trader-backup.tar.gz

# Restore from backup
docker load < grid-trader-backup.tar.gz
```

---

**Note**: This Docker setup provides a production-ready containerized environment for the grid trading system with proper security, monitoring, and maintenance capabilities.