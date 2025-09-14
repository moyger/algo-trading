# Single to Multi-Currency Version Migration Guide

## Overview

This guide will help you upgrade from the original single-currency grid trading bot to the multi-currency version. The multi-currency version is fully backward compatible, keeping all existing single-currency functionality unchanged.

## Pre-Migration Preparation

### 1. Backup Existing Configuration

```bash
# Backup existing configuration
cp .env .env.backup
cp src/single_bot/binance_bot.py src/single_bot/binance_bot.py.backup

# Backup logs (optional)
cp -r log log.backup
```

### 2. Check Existing Environment

```bash
# Check Python version
python3 --version

# Check dependency packages
pip list | grep -E "(ccxt|websockets|yaml|aiohttp)"

# Check existing configuration
cat .env
```

## Migration Steps

### Step 1: Install New Dependencies

```bash
# Install additional dependencies needed for multi-currency version
pip install pyyaml

# Verify installation
python3 -c "import yaml; print('YAML support installed')"
```

### Step 2: Create Multi-Currency Configuration File

Create `symbols.yaml` file:

```yaml
symbols:
  # Original single currency configuration
  - name: XRPUSDT              # Replace with your current trading symbol
    grid_spacing: 0.004        # Replace with your current GRID_SPACING value
    initial_quantity: 1        # Replace with your current INITIAL_QUANTITY value
    leverage: 20               # Replace with your current LEVERAGE value
    contract_type: USDT        # Replace with your current CONTRACT_TYPE value
    
  # Optional: Add new currencies
  - name: BTCUSDT
    grid_spacing: 0.004
    initial_quantity: 0.001
    leverage: 20
    contract_type: USDT
```

### Step 3: Configuration Mapping

Map your existing `.env` configuration to `symbols.yaml`:

| Original .env Variable | symbols.yaml Field | Example |
|------------------------|-------------------|---------|
| `COIN_NAME=XRP` | `name: XRPUSDT` | XRPUSDT |
| `GRID_SPACING=0.004` | `grid_spacing: 0.004` | 0.004 |
| `INITIAL_QUANTITY=1` | `initial_quantity: 1` | 1 |
| `LEVERAGE=20` | `leverage: 20` | 20 |
| `CONTRACT_TYPE=USDT` | `contract_type: USDT` | USDT |

### Step 4: Test Multi-Currency Version

```bash
# Test using startup script
./scripts/start.sh multi

# Or test directly
python3 src/multi_bot/multi_bot.py

# Or test using Docker
./scripts/deploy.sh multi-start
```

### Step 5: Verify Migration Success

```bash
# Check main log
tail -f log/multi_grid_BN.log

# Check status summary
tail -f log/status_summary.log

# Check original currency log
tail -f log/grid_BN_XRPUSDT.log  # Replace XRPUSDT with your symbol
```

## Migration Verification Checklist

### ✅ Configuration Verification
- [ ] API_KEY and API_SECRET from .env still work
- [ ] Original trading symbol correctly configured in symbols.yaml
- [ ] Grid parameters match original settings
- [ ] Telegram notifications still work (if configured)

### ✅ Functionality Verification
- [ ] Multi-currency version starts successfully
- [ ] Original trading logic works as expected
- [ ] Log files generate properly
- [ ] Status summary updates correctly
- [ ] Health check passes

### ✅ Performance Verification
- [ ] Memory usage reasonable
- [ ] CPU usage similar to original
- [ ] Network connections normal
- [ ] Response speed unchanged

## Rollback Procedure

If migration encounters issues, you can easily rollback:

### Method 1: Use Single Currency Mode
```bash
# Stop multi-currency version
./scripts/deploy.sh stop

# Start single currency mode
./scripts/deploy.sh start
```

### Method 2: Complete Rollback
```bash
# Stop current service
./scripts/deploy.sh stop

# Restore backup configuration
cp .env.backup .env
cp src/single_bot/binance_bot.py.backup src/single_bot/binance_bot.py

# Start original version
python3 src/single_bot/binance_bot.py
```

## Advanced Configuration

### Multiple Currencies Configuration

If you want to trade multiple currencies simultaneously:

```yaml
symbols:
  - name: XRPUSDT
    grid_spacing: 0.004
    initial_quantity: 1
    leverage: 20
    contract_type: USDT
    
  - name: BTCUSDT
    grid_spacing: 0.003
    initial_quantity: 0.001
    leverage: 15
    contract_type: USDT
    
  - name: ETHUSDT
    grid_spacing: 0.005
    initial_quantity: 0.01
    leverage: 20
    contract_type: USDT
```

### Resource Configuration Adjustments

For multiple currencies, you might need to adjust resource configurations:

```bash
# Monitor resource usage
docker stats grid-trader

# If needed, increase Docker resource limits in docker-compose.yml
memory: 512m      # Increase from 256m
cpu_shares: 1024  # Increase from 512
```

## Troubleshooting Common Issues

### Issue 1: Configuration File Not Found
**Error**: `Configuration file symbols.yaml does not exist`
**Solution**: 
```bash
# Create configuration file
cp symbols.yaml.example symbols.yaml
# Edit configuration file
nano symbols.yaml
```

### Issue 2: YAML Format Error
**Error**: `YAML parsing error`
**Solution**: 
```bash
# Validate YAML format
python3 -c "import yaml; yaml.safe_load(open('symbols.yaml'))"
```

### Issue 3: Incompatible Dependencies
**Error**: `Module not found: yaml`
**Solution**:
```bash
# Install missing dependencies
pip install pyyaml aiohttp
```

### Issue 4: Log Permission Error
**Error**: `Permission denied: log/multi_grid_BN.log`
**Solution**:
```bash
# Fix permissions
sudo chown -R $USER:$USER log/
chmod 755 log/
```

## Performance Comparison

### Single Currency Version
- Memory usage: ~150MB
- CPU usage: ~10%
- Log files: 1 main file
- Management: Single process

### Multi-Currency Version
- Memory usage: ~200MB (per additional currency +50MB)
- CPU usage: ~15% (per additional currency +5%)
- Log files: 1 main + 1 per currency + status summary
- Management: Main process + sub-threads

## Best Practices

### 1. Gradual Migration
- Start with single currency in multi-currency version
- Verify everything works correctly
- Gradually add more currencies

### 2. Configuration Management
- Use version control for symbols.yaml
- Document configuration changes
- Keep backup configurations

### 3. Monitoring
- Set up log rotation
- Monitor resource usage
- Configure health checks

### 4. Testing
- Test in testnet first
- Use small amounts initially
- Validate all features work

## Support

If you encounter issues during migration:

1. Check logs: `log/multi_grid_BN.log`
2. Run health check: `python3 health_check.py`
3. Verify configuration: Check symbols.yaml format
4. Check resources: Monitor memory/CPU usage

---

**Note**: Migration is reversible. You can always return to single-currency mode if needed. The multi-currency version maintains full compatibility with the original functionality.