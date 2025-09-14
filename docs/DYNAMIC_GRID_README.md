# Dynamic Grid Trading (DGT) System

An enhanced grid trading system that automatically adapts to market volatility using ATR (Average True Range) and Bollinger Bands indicators, inspired by colin4k/atr_grid_bot.

## Overview

Dynamic Grid Trading improves upon traditional grid trading by:
- **Volatility-based spacing**: Grid intervals adjust based on real-time ATR calculations
- **Adaptive grid levels**: Number of grid orders varies with market conditions
- **Bollinger Band integration**: Additional volatility confirmation and positioning
- **Market condition detection**: Automatic identification of trending vs ranging markets
- **Real-time adjustments**: Grid parameters update based on changing market volatility

## Core Concepts

### Classic Grid Trading Limitations
- Fixed grid spacing regardless of market conditions
- Susceptible to whipsaw losses during high volatility
- Inefficient during low volatility periods
- No adaptation to changing market regimes

### Dynamic Grid Enhancements
- **Low Volatility (< 2%)**: Tighter grids (30 levels, 0.7x spacing) to capture small moves
- **Normal Volatility (2-3.5%)**: Standard grids (20 levels, 1.0x spacing)
- **High Volatility (3.5-5%)**: Wider grids (15 levels, 1.3x spacing) to reduce whipsaw
- **Very High Volatility (> 5%)**: Maximum protection (10 levels, 1.8x spacing)

## Key Features

### 1. ATR-Based Volatility Detection
```python
# ATR calculation over 14-period window
true_range = max(
    high - low,
    abs(high - prev_close),
    abs(low - prev_close)
)
atr = average(true_range, period=14)
volatility_ratio = atr / current_price
```

### 2. Dynamic Grid Parameters
- **Grid Spacing**: Adjusts from 0.7x to 1.8x base spacing
- **Grid Levels**: Ranges from 10 to 30 levels
- **Position Bias**: Supports long, short, or neutral positioning

### 3. Bollinger Band Confirmation
- 20-period moving average with 2 standard deviations
- Identifies overbought/oversold conditions
- Provides additional volatility bandwidth measurement

### 4. Real-time Adaptation
- Monitors price data every 15 minutes
- Adjusts grid parameters when volatility changes > 15%
- Cancels out-of-range orders automatically
- Maintains optimal grid positioning

## Implementation

### Core Files
- `src/multi_bot/dynamic_grid.py` - Main DGT calculator
- `src/multi_bot/binance_multi_bot.py` - Enhanced with DGT integration
- `config/dynamic_grid_example.yaml` - Configuration template
- `tests/test_dynamic_grid.py` - Validation test suite

### Configuration Example
```yaml
symbols:
  - name: BTCUSDT
    # Base Configuration
    grid_spacing: 0.002         # 0.2% base spacing
    initial_quantity: 3
    leverage: 20
    
    # Dynamic Grid Settings
    dynamic_grid_enabled: true
    atr_period: 14              # ATR calculation period
    bollinger_period: 20        # Bollinger Bands period
    min_grid_levels: 10         # Minimum grid count
    max_grid_levels: 30         # Maximum grid count
    volatility_multiplier: 1.5  # Overall sensitivity
```

### Usage
```python
from dynamic_grid import DynamicGridCalculator

# Initialize calculator
dg = DynamicGridCalculator(
    symbol="BTCUSDT",
    atr_period=14,
    base_grid_spacing=0.002
)

# Update with market data
dg.update_price_data(high, low, close)

# Get dynamic parameters
params = dg.calculate_dynamic_grid_params()
print(f"Spacing: {params['grid_spacing']:.4f}")
print(f"Levels: {params['grid_levels']}")

# Generate grid orders
grids = dg.generate_grid_levels(
    current_price=45000,
    total_investment=1000,
    position_bias='neutral'
)
```

## Volatility-Based Logic

### ATR Grid Spacing Strategy
Based on colin4k/atr_grid_bot analysis:

| Volatility Ratio | Grid Levels | Spacing Multiplier | Market Condition |
|-------------------|-------------|-------------------|------------------|
| < 1%              | 30          | 0.7x              | Very Low Vol     |
| 1% - 2%           | 25          | 0.85x             | Low Vol          |
| 2% - 3.5%         | 20          | 1.0x              | Normal Vol       |
| 3.5% - 5%         | 15          | 1.3x              | High Vol         |
| > 5%              | 10          | 1.8x              | Very High Vol    |

### Example Scenarios

**CPI News Release (High Volatility)**
- ATR spikes from 800 to 2500 (BTC)
- Volatility ratio: 2500/50000 = 5%
- Grid adjusts to: 10 levels, 1.8x spacing
- Reduces whipsaw risk during volatile moves

**Quiet Trading Session (Low Volatility)**  
- ATR drops from 800 to 400 (BTC)
- Volatility ratio: 400/50000 = 0.8%
- Grid adjusts to: 30 levels, 0.7x spacing
- Captures smaller price movements efficiently

## Performance Benefits

### Backtesting Results (Conceptual)
- **Higher Sharpe Ratio**: Better risk-adjusted returns vs static grids
- **Reduced Drawdowns**: Adaptive spacing limits losses during volatility spikes
- **Improved Capture**: Tighter grids during low volatility capture more moves
- **Lower Slippage**: Dynamic adjustment reduces cancelled/repriced orders

### Risk Management
- Position threshold monitoring with ATR-based scaling
- Emergency reduction system with volatility triggers
- Lockdown mode during extreme market conditions
- Daily fuse circuit breakers for risk control

## Testing

Run the test suite to validate functionality:

```bash
python tests/test_dynamic_grid.py
```

Tests cover:
- ATR calculation accuracy
- Bollinger Bands computation  
- Dynamic parameter adjustment
- Grid level generation
- Market condition detection
- Grid adjustment strategies

## Integration with Existing System

The Dynamic Grid system integrates seamlessly with the existing grid bot:

### Key Integration Points
1. **Grid Spacing Updates**: `_apply_dynamic_grid_spacing()` method
2. **Price Updates**: Modified `_update_mid_price()` with dynamic spacing
3. **Volatility Monitoring**: Added to main `_grid_loop()` cycle
4. **Telegram Notifications**: Grid adjustment alerts
5. **Configuration**: Extended YAML configuration support

### Backward Compatibility
- Dynamic grid can be disabled via `dynamic_grid_enabled: false`
- Falls back to original static grid behavior
- Existing configurations remain valid

## Advanced Features

### Market Condition Detection
- Automatically identifies: sideways, trending, volatile, quiet markets
- Adjusts grid bias based on Bollinger Band positioning
- Provides market state context for logging and notifications

### Grid Adjustment Strategy  
- Time-based checks (every hour by default)
- Volatility change thresholds (>15% change triggers adjustment)
- Smart order cancellation (only out-of-range orders)
- Gradual parameter transitions to avoid disruption

### Monitoring & Alerts
- Real-time volatility metrics logging
- Telegram notifications for grid adjustments
- Market condition status updates
- ATR and Bollinger Band status reporting

## Configuration Reference

### Dynamic Grid Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dynamic_grid_enabled` | true | Enable/disable dynamic adjustments |
| `atr_period` | 14 | ATR calculation window |
| `bollinger_period` | 20 | Bollinger Bands period |
| `bollinger_std` | 2.0 | Bollinger standard deviation |
| `min_grid_levels` | 10 | Minimum grid count |
| `max_grid_levels` | 30 | Maximum grid count |
| `volatility_multiplier` | 1.5 | Global volatility sensitivity |
| `grid_adjustment_interval` | 3600 | Check interval (seconds) |

### Market-Specific Tuning

**BTC/ETH (Large Cap)**
- `atr_period: 14-21` - Standard periods
- `volatility_multiplier: 1.2-1.5` - Moderate sensitivity

**Altcoins (High Volatility)**  
- `atr_period: 7-14` - Shorter periods for responsiveness
- `volatility_multiplier: 1.5-2.5` - Higher sensitivity

**Stablecoins/Low Vol**
- `atr_period: 21-30` - Longer periods for stability
- `volatility_multiplier: 0.8-1.2` - Lower sensitivity

## Future Enhancements

- **Machine Learning Integration**: Pattern recognition for volatility prediction
- **Cross-Asset Correlation**: Multi-symbol volatility analysis
- **Options Integration**: Implied volatility incorporation
- **Backtesting Framework**: Historical performance validation
- **Risk Parity**: Dynamic position sizing based on volatility
- **Regime Detection**: Bull/bear market adaptation

---

## Summary

The Dynamic Grid Trading system represents a significant evolution of traditional grid trading, providing:

1. **Intelligent Adaptation**: ATR-based volatility detection
2. **Risk Reduction**: Wider grids during volatile periods
3. **Profit Optimization**: Tighter grids during quiet periods  
4. **Real-time Adjustment**: Continuous parameter optimization
5. **Market Awareness**: Bollinger Band confirmation and positioning

This system automates the "buy low, sell high" grid strategy while dynamically adapting to market conditions, potentially delivering superior risk-adjusted returns compared to static grid approaches.

**Key Advantage**: Reduces death-by-whipsaw risk while maintaining profit capture efficiency across varying market volatility regimes.