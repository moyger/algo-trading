# Dynamic Grid Trading System - Operations Runbook

## System Overview

Production-ready dynamic grid trading system for Bybit with comprehensive risk controls, state persistence, and emergency systems.

**Key Components:**
- Bybit Exchange Adapter (API v5)
- State Management & Persistence  
- Observability & Monitoring
- Paper Trading Engine
- Kill Switch & Capital Guardrails
- Precision Filters & Order Validation

---

## Pre-Deployment Checklist

### Environment Setup
- [ ] Python 3.8+ with required dependencies
- [ ] Bybit API credentials configured (production/testnet)
- [ ] Redis instance for state storage (optional)
- [ ] Prometheus/Grafana for monitoring
- [ ] Log aggregation system configured
- [ ] Network connectivity to Bybit endpoints verified

### Configuration Validation
- [ ] `symbols.yaml` contains valid trading pairs
- [ ] Capital limits appropriate for account size
- [ ] Grid parameters within exchange constraints
- [ ] Kill switch thresholds configured
- [ ] Logging levels appropriate for production

### Security Verification
- [ ] API keys use minimum required permissions
- [ ] No hardcoded credentials in configuration
- [ ] State files have restricted permissions (600)
- [ ] Kill switch endpoints secured with authentication

---

## Startup Procedures

### 1. Environment Preparation
```bash
# Set environment variables
export TRADING_MODE=production  # or testnet
export BYBIT_API_KEY=your_key
export BYBIT_SECRET=your_secret
export LOG_LEVEL=INFO

# Verify connectivity
python -c "import ccxt; exchange = ccxt.bybit(); print(exchange.fetch_status())"
```

### 2. State Recovery Check
```bash
# Check for existing state files
ls -la data/state/
ls -la data/backups/

# Verify state integrity
python src/multi_bot/state_manager.py --verify-state
```

### 3. System Startup
```bash
# Start with paper trading first (recommended)
export TRADING_MODE=paper
python src/multi_bot/main.py --config symbols.yaml --validate-only

# Production startup
export TRADING_MODE=production  
python src/multi_bot/main.py --config symbols.yaml
```

### 4. Post-Startup Validation
- [ ] WebSocket connections established
- [ ] State files created successfully
- [ ] Metrics endpoint responding (http://localhost:8000/metrics)
- [ ] Health check passing (http://localhost:8001/health)
- [ ] Kill switch endpoint accessible
- [ ] Log files being written

---

## Monitoring & Alerting

### Key Metrics to Monitor

**Trading Performance:**
- `grid_orders_placed_total` - Order placement rate
- `grid_fills_total` - Fill execution rate
- `grid_pnl_realized` - Realized P&L
- `grid_position_value` - Current position size

**System Health:**
- `api_requests_total` - API call volume
- `api_errors_total` - API error rate
- `websocket_disconnections_total` - Connection stability
- `state_save_duration_seconds` - State persistence latency

**Risk Metrics:**
- `capital_utilization_ratio` - Capital usage percentage
- `daily_loss_amount` - Daily drawdown tracking
- `open_orders_count` - Order book size
- `kill_switch_triggers_total` - Emergency activations

### Critical Alerts

**Immediate Response Required:**
- Kill switch activation
- WebSocket disconnection > 30 seconds
- API error rate > 10%
- Daily loss limit > 80% of threshold
- State save failures
- Health check failures

**Warning Level:**
- Fill rate < expected (market conditions)
- Capital utilization > 90%
- Order placement errors
- High API latency (> 500ms)

### Monitoring Dashboards

**Primary Dashboard:**
- P&L trends (1h, 24h, 7d)
- Active positions and orders
- API performance metrics
- System resource usage

**Risk Dashboard:**
- Capital utilization over time
- Daily loss tracking
- Kill switch status
- Emergency trigger history

---

## Emergency Procedures

### Kill Switch Activation

**Manual Activation:**
```bash
# HTTP endpoint
curl -X POST http://localhost:8001/kill-switch/activate \
  -H "Authorization: Bearer $KILL_SWITCH_TOKEN" \
  -d '{"reason": "manual_intervention"}'

# Signal-based
kill -USR1 $(pgrep -f "main.py")

# Configuration file
echo "EMERGENCY_STOP: true" > data/state/kill_switch_active
```

**Post-Activation Actions:**
1. All open orders cancelled within 5 seconds
2. Positions closed (if configured)
3. Trading halted immediately
4. State saved with emergency flag
5. Alerts sent to monitoring systems

### System Recovery

**After Kill Switch:**
```bash
# 1. Investigate root cause
grep "KILL_SWITCH" logs/grid_trading.log

# 2. Clear emergency state
rm -f data/state/kill_switch_active

# 3. Validate system health
python src/multi_bot/main.py --health-check

# 4. Restart in paper mode for verification
export TRADING_MODE=paper
python src/multi_bot/main.py --config symbols.yaml

# 5. Resume production when stable
```

### Data Corruption Recovery

**State File Corruption:**
```bash
# 1. Stop trading immediately
kill $(pgrep -f "main.py")

# 2. Restore from backup
cp data/backups/state_$(date -d "1 hour ago" +%Y%m%d_%H).json data/state/

# 3. Verify backup integrity
python src/multi_bot/state_manager.py --verify-backup

# 4. Restart system
```

---

## Routine Maintenance

### Daily Tasks
- [ ] Review P&L reports and performance metrics
- [ ] Check system logs for errors or warnings
- [ ] Verify state file integrity and backup rotation
- [ ] Monitor API usage and rate limit consumption
- [ ] Review kill switch and alert configurations

### Weekly Tasks
- [ ] Update exchange instrument information
- [ ] Review and adjust grid parameters if needed
- [ ] Analyze trading performance vs market conditions
- [ ] Update system dependencies and security patches
- [ ] Test emergency procedures in testnet environment

### Monthly Tasks
- [ ] Comprehensive performance analysis
- [ ] Review and update risk management parameters
- [ ] Backup configuration and historical state data
- [ ] Security audit of API keys and access controls
- [ ] Disaster recovery procedure testing

---

## Troubleshooting Guide

### Common Issues

**WebSocket Disconnections:**
```bash
# Check network connectivity
ping stream.bybit.com

# Review connection logs
grep "websocket" logs/grid_trading.log | tail -20

# Restart with exponential backoff enabled
export WS_RECONNECT_DELAY=5
```

**Order Placement Failures:**
```bash
# Check account balance and permissions
python -c "
import ccxt
exchange = ccxt.bybit({'apiKey': 'xxx', 'secret': 'xxx'})
print(exchange.fetch_balance())
"

# Review precision filter logs
grep "precision\|filter" logs/grid_trading.log
```

**State Persistence Issues:**
```bash
# Check disk space and permissions
df -h data/
ls -la data/state/

# Verify state manager
python src/multi_bot/state_manager.py --test-write
```

**High Memory Usage:**
```bash
# Monitor process memory
ps aux | grep python

# Review large data structures
python -c "
import gc
gc.collect()
print(f'Objects: {len(gc.get_objects())}')
"
```

### Performance Optimization

**High API Latency:**
- Enable request compression
- Use WebSocket for order placement
- Implement request batching
- Consider geographic proximity to exchange

**Slow State Persistence:**
- Enable compression for large state files
- Use SSD storage for state directory
- Implement async state saving
- Reduce state save frequency during low activity

---

## Configuration Management

### Environment-Specific Settings

**Production:**
```yaml
trading_mode: production
log_level: INFO
state_backup_count: 168  # 7 days hourly
kill_switch_enabled: true
capital_limits:
  max_notional: 50000
  daily_loss_limit: 1000
```

**Testnet:**
```yaml
trading_mode: testnet
log_level: DEBUG
state_backup_count: 24   # 1 day hourly
kill_switch_enabled: true
capital_limits:
  max_notional: 5000
  daily_loss_limit: 100
```

**Paper Trading:**
```yaml
trading_mode: paper
log_level: DEBUG
state_backup_count: 12   # 12 hours
kill_switch_enabled: false
paper_engine:
  starting_balance: 10000
  maker_fee_rate: 0.0001
  taker_fee_rate: 0.0006
```

### Security Configuration

**API Key Permissions (Minimum Required):**
- Read account information
- Place orders
- Cancel orders
- Read positions
- Read order history

**Network Security:**
- Whitelist IP addresses in Bybit dashboard
- Use HTTPS for all API communications
- Implement request signing verification
- Monitor for unusual API activity

---

## Disaster Recovery

### Data Backup Strategy

**Local Backups:**
- Hourly state snapshots (7 days retention)
- Daily configuration backups (30 days retention)
- Weekly full system backups (12 weeks retention)

**Remote Backups:**
- Daily encrypted backup to cloud storage
- Cross-region replication for critical data
- Automated backup integrity verification

### Recovery Procedures

**Complete System Failure:**
1. Deploy system to backup infrastructure
2. Restore latest state from backup
3. Verify account balances and positions
4. Resume trading with reduced risk parameters
5. Gradually scale back to normal operation

**Exchange Connectivity Loss:**
1. Kill switch automatically activated
2. All pending orders cancelled locally
3. Wait for connectivity restoration
4. Manual verification of account state
5. Controlled restart with position reconciliation

### Business Continuity

**Maximum Downtime Targets:**
- System restart: < 2 minutes
- Backup recovery: < 10 minutes
- Full disaster recovery: < 30 minutes

**Data Loss Tolerance:**
- State data: < 1 hour (hourly backups)
- Trading history: < 24 hours (daily backups)
- Configuration: Zero tolerance (version controlled)

---

## Support and Escalation

### Internal Support
1. **Level 1**: System alerts and automated responses
2. **Level 2**: On-call engineer for manual intervention
3. **Level 3**: Development team for code-level issues

### External Dependencies
- **Bybit Support**: API issues, market data problems
- **Infrastructure Provider**: Network connectivity, server issues
- **Security Team**: Authentication problems, suspicious activity

### Contact Information
- **Emergency Hotline**: [Your emergency contact]
- **System Administrator**: [Primary contact]
- **Development Team**: [Technical escalation]
- **Risk Management**: [Trading issues]

---

## Appendix

### File Locations
```
/Users/karlomarceloestrada/Documents/@Projects/dynamic-grid/
├── src/multi_bot/
│   ├── bybit_multi_bot.py      # Exchange adapter
│   ├── bybit_filters.py        # Precision filters
│   ├── state_manager.py        # State persistence
│   ├── observability.py        # Monitoring
│   ├── paper_engine.py         # Paper trading
│   └── kill_switch.py          # Emergency controls
├── data/
│   ├── state/                  # Current state files
│   └── backups/                # State backups
├── logs/                       # Log files
└── symbols.yaml                # Trading configuration
```

### Log File Formats
```json
{
  "timestamp": 1640995200.123,
  "level": "INFO",
  "event_type": "ORDER_PLACED",
  "component": "GridTrader", 
  "message": "Order placed successfully",
  "symbol": "BTCUSDT",
  "order_id": "12345",
  "price": 50000.0,
  "quantity": 0.01,
  "trace_id": "abc123"
}
```

### API Endpoints
- **Health Check**: `http://localhost:8001/health`
- **Metrics**: `http://localhost:8000/metrics` 
- **Kill Switch**: `http://localhost:8001/kill-switch/`
- **System Status**: `http://localhost:8001/status`