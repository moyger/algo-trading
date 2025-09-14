# Multi-Currency Grid Trading Bot - Complete Operating Instructions

## Overview

This project is a multi-currency version of the Binance perpetual contract grid trading bot, supporting simultaneous grid trading strategies for multiple currencies. All grid strategy logic is completely consistent with the single-currency version, with added support for multi-currency parallel operation.

## File Structure

```
grid/
├── src/multi_bot/binance_multi_bot.py # BinanceGridBot class implementation
├── src/single_bot/binance_bot.py      # Single currency entry file
├── src/multi_bot/multi_bot.py         # Multi-currency entry file
├── symbols.yaml            # Multi-currency configuration file
├── symbols.json            # JSON format configuration file
├── scripts/deploy.sh       # Deployment script
├── docker/docker-compose.yml # Docker configuration
├── health_check.py         # Health check script
├── scripts/start.sh        # Startup script
├── .env                    # Environment variable configuration
└── log/                    # Log directory
    ├── multi_grid_BN.log   # Main log
    ├── status_summary.log  # Status summary log
    └── grid_BN_*.log       # Individual currency logs
```

## Quick Start

### 1. Environment Setup

```bash
# Install dependencies
pip install ccxt websockets python-dotenv pyyaml aiohttp

# Configure environment variables
cp .env.example .env
# Edit .env file to set API keys and other information
```

### 2. Configuration File Setup

Create `symbols.yaml` file:

```yaml
symbols:
  - name: BTCUSDT
    grid_spacing: 0.004
    initial_quantity: 0.001
    leverage: 20
    contract_type: USDT
    
  - name: ETHUSDT
    grid_spacing: 0.005
    initial_quantity: 0.01
    leverage: 20
    contract_type: USDT
```

### 3. Startup Methods

#### Method 1: Direct Execution
```bash
# Start single currency mode
python3 src/single_bot/binance_bot.py

# Start multi-currency mode
python3 src/multi_bot/multi_bot.py

# Or use startup script
./scripts/start.sh single    # Single currency
./scripts/start.sh multi     # Multi-currency
```

#### Method 2: Docker Execution
```bash
# Build image
./scripts/deploy.sh build

# Start single currency mode
./scripts/deploy.sh start

# Start multi-currency mode
./scripts/deploy.sh multi-start
```

## Detailed Configuration Instructions

### Environment Variable Configuration (.env)

```bash
# Required configuration
API_KEY=your_binance_api_key
API_SECRET=your_binance_api_secret

# Optional configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
ENABLE_NOTIFICATIONS=true
NOTIFICATION_INTERVAL=3600
```

### Multi-Currency Configuration (symbols.yaml)

```yaml
symbols:
  - name: BTCUSDT              # Trading pair name
    grid_spacing: 0.004        # Grid spacing (0.001-0.01)
    initial_quantity: 0.001    # Initial trading quantity
    leverage: 20               # Leverage multiplier (1-100)
    contract_type: USDT        # Contract type (USDT/USDC)
    
  - name: ETHUSDT
    grid_spacing: 0.005
    initial_quantity: 0.01
    leverage: 20
    contract_type: USDT
```

### Configuration Parameter Description

| Parameter | Description | Recommended Range | Example |
|-----------|-------------|-------------------|---------|
| `name` | Trading pair name | Binance supported perpetual contracts | BTCUSDT, ETHUSDT |
| `grid_spacing` | Grid spacing | 0.001-0.01 | 0.004 (0.4%) |
| `initial_quantity` | Initial quantity | Adjust based on currency price | BTC: 0.001, ETH: 0.01 |
| `leverage` | Leverage multiplier | 1-100 | 20 |
| `contract_type` | Contract type | USDT/USDC | USDT |

## Log Management

### Log File Description

- `log/multi_grid_BN.log`: Main control log
- `log/status_summary.log`: Status summary log
- `log/grid_BN_BTCUSDT.log`: BTC currency log
- `log/grid_BN_ETHUSDT.log`: ETH currency log

### View Logs

```bash
# View main log
tail -f log/multi_grid_BN.log

# View status summary
tail -f log/status_summary.log

# View specific currency log
tail -f log/grid_BN_BTCUSDT.log

# Use deployment script to view
./scripts/deploy.sh multi-logs    # View summary log
./scripts/deploy.sh bot-logs      # View currency logs
```

### Log Rotation

- Automatic date-based splitting: New file created at midnight daily
- Retention period: Last 7 days of log files
- File naming: `grid_BN_BTCUSDT.log.2024-01-15`

## Health Check

### Manual Check
```bash
python3 health_check.py
```

### Docker Health Check
```bash
# View container health status
docker inspect grid-trader --format='{{.State.Health.Status}}'

# View health check logs
docker inspect grid-trader --format='{{.State.Health.Log}}'
```

### Health Check Items

1. **Status Summary Log**: Check for normal updates
2. **Main Log File**: Check file size and errors
3. **Currency Log Files**: Check operation status of each currency
4. **Process Status**: Check if main process is alive

## Deployment Script Usage

### Basic Commands

```bash
./scripts/deploy.sh build          # Build Docker image
./scripts/deploy.sh start          # Start single currency mode
./scripts/deploy.sh multi-start    # Start multi-currency mode
./scripts/deploy.sh stop           # Stop service
./scripts/deploy.sh restart        # Restart service
./scripts/deploy.sh logs           # View container logs
./scripts/deploy.sh multi-logs     # View summary logs
./scripts/deploy.sh bot-logs       # View currency logs
./scripts/deploy.sh status         # View status
./scripts/deploy.sh cleanup        # Clean up resources
```

### Docker Management

```bash
# View container status
docker-compose -f docker/docker-compose.yml ps

# View resource usage
docker stats grid-trader

# Enter container
docker exec -it grid-trader bash

# View container logs
docker-compose -f docker/docker-compose.yml logs -f
```

## Troubleshooting

### Common Issues

1. **API Key Error**
   ```bash
   # Check environment variables
   docker exec grid-trader env | grep API
   ```

2. **Configuration File Error**
   ```bash
   # Verify YAML format
   python3 -c "import yaml; yaml.safe_load(open('symbols.yaml'))"
   ```

3. **Network Connection Issues**
   ```bash
   # Check network connection
   docker exec grid-trader ping -c 3 fstream.binance.com
   ```

4. **Log File Permissions**
   ```bash
   # Fix permissions
   sudo chown -R $USER:$USER log/
   chmod 755 log/
   ```

### Restart Service

```bash
# Complete restart
./scripts/deploy.sh stop
./scripts/deploy.sh multi-start

# Rebuild
./scripts/deploy.sh build
./scripts/deploy.sh multi-start
```

## Performance Monitoring

### Resource Usage Monitoring

```bash
# View container resource usage
docker stats grid-trader

# View log file sizes
du -sh log/*.log

# View disk usage
df -h
```

### Status Monitoring

```bash
# View active bots
tail -1 log/status_summary.log

# View error logs
grep ERROR log/multi_grid_BN.log

# View startup status
grep "startup successful" log/multi_grid_BN.log
```

## Security Considerations

1. **API Key Security**
   - Do not hardcode API keys in code
   - Use environment variables or .env files
   - Regularly rotate API keys

2. **Permission Control**
   - Limit API key permissions (read-only + trading)
   - Set IP whitelist
   - Enable two-factor authentication

3. **Fund Security**
   - Use testnet for testing
   - Start testing with small amounts
   - Set reasonable stop-loss

## Version Compatibility

### Backward Compatibility

- Single currency version `src/single_bot/binance_bot.py` is fully compatible
- Existing `.env` configuration can be used directly
- Original log format remains unchanged

### Upgrade Path

1. **Upgrade from Single to Multi-Currency**
   ```bash
   # Backup existing configuration
   cp .env .env.backup
   
   # Create multi-currency configuration
   cp symbols.yaml.example symbols.yaml
   # Edit symbols.yaml
   
   # Start multi-currency mode
   ./scripts/deploy.sh multi-start
   ```

2. **Rollback to Single Currency**
   ```bash
   # Stop multi-currency service
   ./scripts/deploy.sh stop
   
   # Start single currency service
   ./scripts/deploy.sh start
   ```

## Testing Recommendations

### Test Environment Setup

1. **Use Test Network**
   - Test on Binance testnet
   - Use small amounts for testing

2. **Test Currency Selection**
   - Recommend testing 2-3 currencies
   - Choose currencies with good liquidity

3. **Test Configuration**
   ```yaml
   symbols:
     - name: BTCUSDT
       grid_spacing: 0.004
       initial_quantity: 0.001
       leverage: 20
     - name: ETHUSDT
       grid_spacing: 0.005
       initial_quantity: 0.01
       leverage: 20
   ```

### Test Verification Steps

1. **Start Test**
   ```bash
   ./scripts/deploy.sh multi-start
   ```

2. **Check Logs**
   ```bash
   # Check main log
   tail -f log/multi_grid_BN.log
   
   # Check status summary
   tail -f log/status_summary.log
   
   # Check currency logs
   tail -f log/grid_BN_BTCUSDT.log
   tail -f log/grid_BN_ETHUSDT.log
   ```

3. **Verify Functions**
   - Confirm both currencies are running
   - Confirm log files are generated normally
   - Confirm Telegram notifications work properly

4. **Health Check**
   ```bash
   python3 health_check.py
   ```

## Technical Support

### Log Analysis

If you encounter issues, please provide the following information:

1. Main log file: `log/multi_grid_BN.log`
2. Status summary log: `log/status_summary.log`
3. Related currency logs: `log/grid_BN_[currency].log`
4. Health check results: `python3 health_check.py`

### Common Errors

1. **"API_KEY and API_SECRET must be set"**
   - Check if .env file exists
   - Confirm API_KEY and API_SECRET are set

2. **"Configuration file does not exist"**
   - Confirm symbols.yaml or symbols.json file exists
   - Check if file format is correct

3. **"Hedge position mode failed"**
   - Manually enable hedge position mode on Binance
   - Confirm API key has sufficient permissions

4. **"WebSocket connection failed"**
   - Check network connection
   - Confirm firewall settings
   - Check API key permissions

---

**Note**: This software is for learning and research purposes only. Please fully understand the risks before use and ensure compliance with relevant laws and regulations.