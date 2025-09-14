# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
```bash
# Run dynamic grid tests
python tests/test_dynamic_grid.py

# Run regime filter tests  
python tests/test_regime_filters.py

# Run DGT anchor algorithm integration tests
python tests/test_anchor_integration.py

# Run all tests from project root
python -m pytest tests/ -v

# Test single components
python tests/test_dynamic_grid.py    # ATR, volatility, grid generation validation
python tests/test_regime_filters.py # EMA, RSI, ADX, regime classification validation
python tests/test_anchor_integration.py # DGT anchor algorithm integration validation
```

### Docker Development
```bash
# Build and deploy
./scripts/deploy.sh build    # Build Docker image
./scripts/deploy.sh start    # Start single currency mode
./scripts/deploy.sh multi-start  # Start multi-currency mode
./scripts/deploy.sh logs     # View logs
./scripts/deploy.sh stop     # Stop services

# Local development
python src/multi_bot/multi_bot.py     # Multi-currency mode
python src/single_bot/binance_bot.py  # Single currency mode
```

### Configuration Management
```bash
# Setup environment
cp config/env.example .env
cp config/symbols.yaml.example config/symbols.yaml

# Validate configuration
python -c "import yaml; print(yaml.safe_load(open('config/symbols.yaml')))"
```

## Architecture Overview

### Core Trading System
The system implements **bidirectional grid trading** with advanced risk management across two operational modes:

**Single Currency Mode**: `src/single_bot/` - Individual currency grid trading
**Multi-Currency Mode**: `src/multi_bot/` - Concurrent multi-symbol trading

### Key Architectural Components

#### 1. Grid Trading Engine (`src/multi_bot/binance_multi_bot.py`)
- **Bidirectional Position Management**: Simultaneous long/short positions with independent risk thresholds
- **WebSocket-Driven Execution**: Real-time price feeds and order updates via persistent WebSocket connections  
- **Grid Loop Architecture**: Main trading loop (`_grid_loop()`) orchestrates position monitoring, order placement, and risk checks

#### 2. Dynamic Grid System (`src/multi_bot/dynamic_grid.py`)
- **ATR-Based Volatility Detection**: 14-period Average True Range calculations for market condition assessment
- **Adaptive Grid Parameters**: Volatility-driven adjustment of grid spacing (0.7x to 1.8x) and level count (10-30)  
- **Bollinger Bands Integration**: 20-period bands for market positioning and overbought/oversold detection
- **Regime Filter Integration**: Multi-indicator regime detection for enhanced grid parameter optimization

#### 2.1. Regime Filter System (`src/multi_bot/regime_filters.py`)
- **Multi-Indicator Analysis**: EMA crossovers, RSI momentum, ADX trend strength, Bollinger Bands, and volume analysis
- **Market Regime Classification**: 9 distinct regime types (strong/weak trends, ranging conditions, volatile/quiet periods)
- **Signal Confluence**: Confidence-based regime detection using multiple technical indicator agreement
- **Grid Parameter Adjustment**: Regime-specific multipliers for spacing (0.6x to 1.8x) and levels (0.6x to 1.4x)
- **Position Bias Recommendations**: Long/short/neutral bias based on regime analysis

#### 2.2. DGT Anchor Algorithm System (`src/multi_bot/anchor_algorithm.py`)
- **Research-Based Positioning**: Implements Dynamic Grid Trading (DGT) methodology from arXiv paper research
- **Performance-Driven Anchoring**: Optimal anchor point selection based on historical trade performance analysis
- **Adaptive Reset Mechanisms**: Intelligent anchor repositioning using volatility, performance degradation, and time-based triggers
- **Multiple Anchor Types**: Price-based, volatility-based, volume-weighted, regime-adaptive, and momentum-based anchoring strategies
- **Mathematical Optimization**: Minimizes expected loss through optimal anchor placement using historical performance data
- **Performance Tracking**: Comprehensive trade result recording and anchor effectiveness measurement

#### 3. Risk Management Systems
**Emergency Position Reduction**: Triggered when positions exceed 80% of threshold, executes batched reductions with smart order routing
**Lockdown Mode (装死模式)**: Single-direction position freeze when exceeding 100% threshold, maintains only take-profit orders
**Daily Circuit Breaker**: Halts new positions after 3 emergency triggers per day

#### 4. Multi-Bot Orchestration (`src/multi_bot/multi_bot.py`)
- **Concurrent Execution**: ThreadPoolExecutor manages multiple bot instances with isolated event loops
- **Shared Resource Management**: Centralized logging, configuration loading, and status aggregation
- **Graceful Shutdown**: Signal handling for clean bot termination and resource cleanup

### Configuration Architecture
**Environment Variables**: API credentials, exchange settings, basic trading parameters
**YAML Configuration**: Multi-currency symbol definitions, dynamic grid parameters, risk thresholds
**Runtime State Management**: Lockdown state persistence via JSON files in `src/multi_bot/state/`

### Data Flow
1. **WebSocket Streams**: Real-time price/order data → Trading engine
2. **Position Updates**: Exchange API calls → Position state synchronization  
3. **Grid Calculations**: Price data → Dynamic grid calculator → Order parameters
4. **Risk Monitoring**: Position thresholds → Emergency systems → Order modifications
5. **Notification Pipeline**: Trading events → Telegram notifications

### Exchange Integration Layer
**CCXT Abstraction**: Exchange-agnostic API interface with Binance optimization
**WebSocket Handling**: Direct exchange WebSocket connections for minimal latency
**Order Management**: Precision-aware order placement with exchange-specific constraints

## Key Implementation Patterns

### Async/Await Architecture
All trading operations use asyncio for non-blocking execution. Main components:
- `_connect_websocket()`: Persistent connection management
- `_grid_loop()`: Main trading logic with async order placement
- `_handle_ticker_update()`: Real-time price processing

### Thread Safety
Multi-currency mode uses thread-isolated event loops with shared resource locks for state consistency.

### Error Handling
Comprehensive exception handling with automatic retries, fallback mechanisms, and detailed logging for debugging.

### State Persistence
Critical trading state (lockdown mode, emergency counters) persisted to disk using atomic file operations to prevent data corruption.

## Configuration Schema

### Core Trading Parameters
- `grid_spacing`: Base grid interval percentage (e.g., 0.002 = 0.2%)
- `initial_quantity`: Base order size per grid level  
- `leverage`: Futures contract leverage multiplier
- `position_threshold_factor`: Risk threshold multiplier (default: 10)

### Dynamic Grid Parameters  
- `dynamic_grid_enabled`: Enable/disable adaptive grid system
- `atr_period`: ATR calculation window (default: 14)
- `volatility_multiplier`: Grid sensitivity adjustment (default: 1.5)
- `min_grid_levels`/`max_grid_levels`: Grid count bounds (10-30)

### Regime Filter Configuration
- `regime_filter_enabled`: Enable multi-indicator regime detection
- `ema_fast_period`/`ema_slow_period`: EMA crossover periods (12/26)
- `rsi_period`: RSI calculation window (default: 14)
- `adx_period`: ADX trend strength period (default: 14)
- `volume_period`: Volume analysis window (default: 20)
- `regime_update_interval`: Regime check frequency in seconds (300)

### DGT Anchor System Configuration
- `anchor_enabled`: Enable/disable DGT anchor algorithm
- `anchor_lookback_hours`: Historical data window for optimization (24)
- `anchor_performance_threshold`: Minimum improvement to trigger reset (0.02)
- `anchor_reset_cooldown`: Cooldown between resets in seconds (3600)
- `anchor_volatility_threshold`: Volatility threshold for anchor type selection (0.05)

### Risk Management Configuration
- `emg_enter_ratio`: Emergency trigger threshold (default: 0.80)
- `emg_batches`: Position reduction batch count (default: 2)
- `emg_daily_fuse_count`: Daily emergency limit (default: 3)

## Testing Strategy

The test suite (`tests/test_dynamic_grid.py`) validates:
- **ATR Calculation Accuracy**: Historical price data → Expected volatility metrics
- **Dynamic Parameter Logic**: Volatility scenarios → Grid spacing/level adjustments  
- **Grid Generation**: Market conditions → Order placement strategies
- **Market Condition Detection**: Price patterns → Trading regime classification

## Common Development Patterns

### Adding New Indicators
1. Implement calculation in `DynamicGridCalculator` class
2. Update `_calculate_dynamic_grid_params()` logic
3. Add configuration parameters to YAML schema
4. Create validation tests

### Risk System Extensions
1. Implement trigger logic in `_check_risk()` method
2. Add state persistence if needed
3. Create notification handlers
4. Update emergency flow documentation

### Exchange Integration
1. Extend CCXT customization in exchange initialization
2. Add WebSocket stream handlers for new data types
3. Implement exchange-specific precision handling
4. Test with paper trading first