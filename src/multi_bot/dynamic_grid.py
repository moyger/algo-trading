import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging
import time
from collections import deque
from regime_filters import RegimeFilterSystem, MarketRegime
from anchor_algorithm import DynamicAnchorSystem, AnchorType

logger = logging.getLogger(__name__)

@dataclass
class GridLevel:
    price: float
    quantity: float
    side: str  # 'buy' or 'sell'
    order_id: Optional[str] = None
    filled: bool = False
    
class DynamicGridCalculator:
    def __init__(self, 
                 symbol: str,
                 atr_period: int = 14,
                 bollinger_period: int = 20,
                 bollinger_std: float = 2.0,
                 min_grid_levels: int = 10,
                 max_grid_levels: int = 30,
                 base_grid_spacing: float = 0.001,
                 volatility_multiplier: float = 1.5,
                 config: Dict = None):
        
        if config is None:
            config = {}
            
        self.symbol = symbol
        self.atr_period = atr_period
        self.bollinger_period = bollinger_period
        self.bollinger_std = bollinger_std
        self.min_grid_levels = min_grid_levels
        self.max_grid_levels = max_grid_levels
        self.base_grid_spacing = base_grid_spacing
        self.volatility_multiplier = volatility_multiplier
        
        # Price history for indicators
        self.price_history = deque(maxlen=max(atr_period, bollinger_period) + 1)
        self.high_history = deque(maxlen=atr_period + 1)
        self.low_history = deque(maxlen=atr_period + 1)
        self.close_history = deque(maxlen=atr_period + 1)
        
        # Current indicators
        self.current_atr = None
        self.current_volatility_ratio = None
        self.bollinger_bands = None
        self.grid_spacing = base_grid_spacing
        self.grid_levels_count = 20
        
        # Grid state
        self.active_grids: List[GridLevel] = []
        self.last_update_time = 0
        self.update_interval = 3600  # 1 hour default
        
        # Initialize regime filter system
        self.regime_filter = RegimeFilterSystem(
            ema_fast_period=config.get('ema_fast_period', 12),
            ema_slow_period=config.get('ema_slow_period', 26),
            rsi_period=config.get('rsi_period', 14),
            adx_period=config.get('adx_period', 14),
            bb_period=self.bollinger_period,
            bb_std=self.bollinger_std,
            volume_period=config.get('volume_period', 20)
        )
        
        # Regime-based adjustments
        self.regime_enabled = config.get('regime_filter_enabled', True)
        self.last_regime_update = 0
        self.regime_update_interval = config.get('regime_update_interval', 300)  # 5 minutes
        
        # Initialize Dynamic Anchor System (DGT methodology)
        self.anchor_enabled = config.get('anchor_enabled', config.get('anchor_system_enabled', True))
        if self.anchor_enabled:
            lookback_hours = config.get('anchor_lookback_hours', 24)
            lookback_period = int(lookback_hours * 12)  # Convert hours to 5-min periods
            
            self.anchor_system = DynamicAnchorSystem(
                symbol=symbol,
                lookback_period=config.get('anchor_lookback_period', lookback_period),
                anchor_reset_threshold=config.get('anchor_performance_threshold', config.get('anchor_reset_threshold', 0.05)),
                min_reset_interval=config.get('anchor_reset_cooldown', config.get('anchor_min_reset_interval', 3600)),
                max_anchor_age=config.get('anchor_max_age', 86400),
                performance_window=config.get('anchor_performance_window', 20),
                volatility_multiplier=config.get('anchor_volatility_threshold', config.get('anchor_volatility_multiplier', 2.0))
            )
        else:
            self.anchor_system = None
        
        # Anchor-related state
        self.last_anchor_update = 0
        self.anchor_update_interval = config.get('anchor_update_interval', 300)  # 5 minutes
        
    def update_price_data(self, high: float, low: float, close: float, volume: float = None):
        """Update price history with new OHLC data"""
        self.high_history.append(high)
        self.low_history.append(low)
        self.close_history.append(close)
        self.price_history.append(close)
        
        # Update regime filter system
        if self.regime_enabled:
            self.regime_filter.update_market_data(high, low, close, volume)
        
        # Update anchor system (DGT methodology)
        if self.anchor_enabled and self.anchor_system:
            self.anchor_system.update_market_data(close, volume)
        
        # Calculate indicators if we have enough data
        if len(self.close_history) >= self.atr_period:
            self._calculate_atr()
            self._calculate_volatility_ratio()
            
        if len(self.price_history) >= self.bollinger_period:
            self._calculate_bollinger_bands()
            
    def _calculate_atr(self) -> float:
        """Calculate Average True Range"""
        if len(self.close_history) < self.atr_period:
            return None
            
        true_ranges = []
        for i in range(1, self.atr_period + 1):
            if i < len(self.high_history):
                high = self.high_history[-i]
                low = self.low_history[-i]
                prev_close = self.close_history[-i-1] if i < len(self.close_history) - 1 else self.close_history[-i]
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
        
        if true_ranges:
            self.current_atr = np.mean(true_ranges)
            return self.current_atr
        return None
    
    def _calculate_volatility_ratio(self):
        """Calculate volatility ratio (ATR/Price)"""
        if self.current_atr and self.close_history:
            current_price = self.close_history[-1]
            self.current_volatility_ratio = self.current_atr / current_price
            return self.current_volatility_ratio
        return None
    
    def _calculate_bollinger_bands(self):
        """Calculate Bollinger Bands"""
        if len(self.price_history) < self.bollinger_period:
            return None
            
        prices = list(self.price_history)[-self.bollinger_period:]
        sma = np.mean(prices)
        std = np.std(prices)
        
        self.bollinger_bands = {
            'upper': sma + (self.bollinger_std * std),
            'middle': sma,
            'lower': sma - (self.bollinger_std * std),
            'bandwidth': 2 * self.bollinger_std * std / sma if sma > 0 else 0
        }
        return self.bollinger_bands
    
    def calculate_dynamic_grid_params(self) -> Dict:
        """Calculate dynamic grid parameters based on current volatility and market regime"""
        
        # Base parameters
        params = {
            'grid_spacing': self.base_grid_spacing,
            'grid_levels': 20,
            'adjustment_factor': 1.0,
            'position_bias': 'neutral'
        }
        
        # ATR-based volatility adjustments (original logic)
        if self.current_volatility_ratio:
            if self.current_volatility_ratio < 0.01:
                params['grid_levels'] = min(30, self.max_grid_levels)
                params['grid_spacing'] = self.base_grid_spacing * 0.7
                params['adjustment_factor'] = 0.7
            elif self.current_volatility_ratio < 0.02:
                params['grid_levels'] = 25
                params['grid_spacing'] = self.base_grid_spacing * 0.85
                params['adjustment_factor'] = 0.85
            elif self.current_volatility_ratio < 0.035:
                params['grid_levels'] = 20
                params['grid_spacing'] = self.base_grid_spacing
                params['adjustment_factor'] = 1.0
            elif self.current_volatility_ratio < 0.05:
                params['grid_levels'] = 15
                params['grid_spacing'] = self.base_grid_spacing * 1.3
                params['adjustment_factor'] = 1.3
            else:
                params['grid_levels'] = max(10, self.min_grid_levels)
                params['grid_spacing'] = self.base_grid_spacing * 1.8
                params['adjustment_factor'] = 1.8
        
        # Regime-based adjustments (new enhancement)
        if self.regime_enabled:
            regime_adjustments = self.regime_filter.get_regime_grid_adjustments()
            
            # Apply regime multipliers
            params['grid_spacing'] *= regime_adjustments.get('spacing_multiplier', 1.0)
            params['grid_levels'] = int(params['grid_levels'] * regime_adjustments.get('levels_multiplier', 1.0))
            params['position_bias'] = regime_adjustments.get('bias', 'neutral')
            
            # Ensure levels stay within bounds
            params['grid_levels'] = max(self.min_grid_levels, min(self.max_grid_levels, params['grid_levels']))
        
        # Additional adjustment based on Bollinger Band width
        if self.bollinger_bands:
            bb_width = self.bollinger_bands['bandwidth']
            if bb_width > 0.06:  # Wide bands = high volatility
                params['grid_spacing'] *= 1.2
                params['grid_levels'] = max(self.min_grid_levels, params['grid_levels'] - 2)
            elif bb_width < 0.02:  # Narrow bands = low volatility
                params['grid_spacing'] *= 0.9
                params['grid_levels'] = min(self.max_grid_levels, params['grid_levels'] + 2)
        
        # Apply volatility multiplier
        params['grid_spacing'] *= self.volatility_multiplier
        
        # Store calculated values
        self.grid_spacing = params['grid_spacing']
        self.grid_levels_count = params['grid_levels']
        
        # Enhanced logging with regime information
        volatility_ratio = self.current_volatility_ratio or 0
        atr = self.current_atr or 0
        regime_info = ""
        
        if self.regime_enabled:
            current_regime = self.regime_filter.current_regime
            regime_confidence = self.regime_filter.regime_confidence
            regime_info = f", regime={current_regime.value}, confidence={regime_confidence:.2f}"
        
        logger.info(f"Dynamic grid params: spacing={params['grid_spacing']:.4f}, "
                   f"levels={params['grid_levels']}, "
                   f"bias={params['position_bias']}, "
                   f"volatility_ratio={volatility_ratio:.4f}, "
                   f"ATR={atr:.6f}{regime_info}")
        
        return params
    
    def generate_grid_levels(self, 
                           current_price: float,
                           total_investment: float,
                           position_bias: str = 'neutral') -> List[GridLevel]:
        """Generate grid levels based on current market conditions and anchor positioning (DGT)"""
        
        # Get dynamic parameters
        params = self.calculate_dynamic_grid_params()
        grid_spacing = params['grid_spacing']
        grid_levels = params['grid_levels']
        
        grids = []
        
        # Use anchor-based grid generation if enabled
        if self.anchor_enabled and self.anchor_system and self.anchor_system.primary_anchor:
            buy_prices, sell_prices = self.anchor_system.get_anchor_grid_levels(
                current_price, grid_spacing, grid_levels
            )
            
            # Calculate investment per grid
            total_levels = len(buy_prices) + len(sell_prices)
            investment_per_grid = total_investment / max(1, total_levels)
            
            # Create buy grids from anchor-positioned levels
            for price_level in buy_prices:
                if price_level > 0:  # Sanity check
                    quantity = investment_per_grid / price_level
                    grids.append(GridLevel(
                        price=price_level,
                        quantity=quantity,
                        side='buy'
                    ))
            
            # Create sell grids from anchor-positioned levels
            for price_level in sell_prices:
                if price_level > 0:  # Sanity check
                    quantity = investment_per_grid / price_level
                    grids.append(GridLevel(
                        price=price_level,
                        quantity=quantity,
                        side='sell'
                    ))
            
            logger.info(f"Generated {len(grids)} anchor-based grid levels "
                       f"(anchor: {self.anchor_system.primary_anchor.price:.6f}, "
                       f"type: {self.anchor_system.primary_anchor.anchor_type.value})")
        
        else:
            # Fallback to traditional grid generation
            # Calculate grid boundaries
            if position_bias == 'long':
                # More buy grids below price
                buy_levels = int(grid_levels * 0.7)
                sell_levels = grid_levels - buy_levels
            elif position_bias == 'short':
                # More sell grids above price
                sell_levels = int(grid_levels * 0.7)
                buy_levels = grid_levels - sell_levels
            else:
                # Neutral - equal distribution
                buy_levels = grid_levels // 2
                sell_levels = grid_levels - buy_levels
            
            # Investment per grid
            investment_per_grid = total_investment / grid_levels
            
            # Generate buy grids
            for i in range(1, buy_levels + 1):
                price_level = current_price * (1 - grid_spacing * i)
                quantity = investment_per_grid / price_level
                grids.append(GridLevel(
                    price=price_level,
                    quantity=quantity,
                    side='buy'
                ))
            
            # Generate sell grids
            for i in range(1, sell_levels + 1):
                price_level = current_price * (1 + grid_spacing * i)
                quantity = investment_per_grid / price_level
                grids.append(GridLevel(
                    price=price_level,
                    quantity=quantity,
                    side='sell'
                ))
            
            logger.info(f"Generated {len(grids)} traditional grid levels")
        
        # Sort by price
        grids.sort(key=lambda x: x.price)
        
        self.active_grids = grids
        return grids
    
    def should_adjust_grid(self) -> bool:
        """Check if grid should be adjusted based on volatility changes"""
        
        # Time-based check
        current_time = time.time()
        if current_time - self.last_update_time < self.update_interval:
            return False
        
        # Volatility change check
        if self.current_volatility_ratio:
            # Get current grid params
            params = self.calculate_dynamic_grid_params()
            
            # Check if spacing changed significantly (>15%)
            spacing_change = abs(params['grid_spacing'] - self.grid_spacing) / self.grid_spacing
            if spacing_change > 0.15:
                logger.info(f"Grid adjustment needed: spacing change {spacing_change:.2%}")
                return True
            
            # Check if level count changed significantly
            if abs(params['grid_levels'] - self.grid_levels_count) >= 3:
                logger.info(f"Grid adjustment needed: level change from {self.grid_levels_count} to {params['grid_levels']}")
                return True
        
        return False
    
    def get_grid_adjustment_strategy(self, current_price: float) -> Dict:
        """Get strategy for adjusting existing grid"""
        
        if not self.should_adjust_grid():
            return {'action': 'hold', 'reason': 'No adjustment needed'}
        
        # Calculate new parameters
        new_params = self.calculate_dynamic_grid_params()
        
        # Determine adjustment strategy
        strategy = {
            'action': 'adjust',
            'new_spacing': new_params['grid_spacing'],
            'new_levels': new_params['grid_levels'],
            'volatility_ratio': self.current_volatility_ratio,
            'atr': self.current_atr
        }
        
        # Determine which orders to cancel/modify
        orders_to_cancel = []
        orders_to_add = []
        
        for grid in self.active_grids:
            if not grid.filled:
                # Check if grid is too far from current price
                price_distance = abs(grid.price - current_price) / current_price
                max_distance = new_params['grid_spacing'] * new_params['grid_levels']
                
                if price_distance > max_distance:
                    orders_to_cancel.append(grid)
        
        strategy['cancel_orders'] = orders_to_cancel
        strategy['add_orders'] = orders_to_add
        
        self.last_update_time = time.time()
        
        return strategy
    
    def get_market_condition(self) -> str:
        """Analyze current market condition based on indicators"""
        
        conditions = []
        
        # Volatility condition
        if self.current_volatility_ratio:
            if self.current_volatility_ratio < 0.015:
                conditions.append("very_low_volatility")
            elif self.current_volatility_ratio < 0.03:
                conditions.append("low_volatility")
            elif self.current_volatility_ratio < 0.05:
                conditions.append("normal_volatility")
            else:
                conditions.append("high_volatility")
        
        # Bollinger Band position
        if self.bollinger_bands and self.close_history:
            current_price = self.close_history[-1]
            bb = self.bollinger_bands
            
            if current_price > bb['upper']:
                conditions.append("overbought")
            elif current_price < bb['lower']:
                conditions.append("oversold")
            else:
                band_range = bb['upper'] - bb['lower']
                if band_range > 0:
                    position_in_band = (current_price - bb['lower']) / band_range
                    if position_in_band > 0.7:
                        conditions.append("near_upper_band")
                    elif position_in_band < 0.3:
                        conditions.append("near_lower_band")
                    else:
                        conditions.append("mid_range")
                else:
                    conditions.append("mid_range")
        
        return "_".join(conditions) if conditions else "unknown"
    
    def get_volatility_metrics(self) -> Dict:
        """Get current volatility metrics for monitoring"""
        
        metrics = {
            'atr': self.current_atr,
            'volatility_ratio': self.current_volatility_ratio,
            'grid_spacing': self.grid_spacing,
            'grid_levels': self.grid_levels_count,
            'market_condition': self.get_market_condition()
        }
        
        if self.bollinger_bands:
            metrics['bollinger_bandwidth'] = self.bollinger_bands['bandwidth']
            metrics['bollinger_upper'] = self.bollinger_bands['upper']
            metrics['bollinger_lower'] = self.bollinger_bands['lower']
        
        # Add regime filter metrics
        if self.regime_enabled:
            regime_recommendation = self.regime_filter.get_trading_recommendation()
            metrics.update({
                'regime': regime_recommendation['regime'],
                'regime_confidence': regime_recommendation['confidence'],
                'trend_strength': regime_recommendation['trend_strength'],
                'momentum': regime_recommendation['momentum'],
                'regime_volatility': regime_recommendation['volatility'],
                'volume_strength': regime_recommendation['volume_strength'],
                'position_bias': regime_recommendation['position_bias'],
                'regime_recommendation': regime_recommendation['recommendation']
            })
        
        return metrics
    
    def get_regime_analysis(self) -> Dict:
        """Get comprehensive regime analysis"""
        if not self.regime_enabled:
            return {'enabled': False, 'message': 'Regime filtering disabled'}
        
        return self.regime_filter.get_trading_recommendation()
    
    def should_adjust_for_regime(self) -> bool:
        """Check if grid should be adjusted based on regime change"""
        if not self.regime_enabled:
            return False
        
        current_time = time.time()
        if current_time - self.last_regime_update < self.regime_update_interval:
            return False
        
        # Get current regime recommendation
        recommendation = self.regime_filter.get_trading_recommendation()
        
        # Check if regime confidence is high enough to warrant adjustment
        if recommendation['confidence'] > 0.7:
            self.last_regime_update = current_time
            logger.info(f"Regime adjustment triggered: {recommendation['regime']} "
                       f"(confidence: {recommendation['confidence']:.2%})")
            return True
        
        return False
    
    def record_trade_result(self, entry_price: float, exit_price: float, 
                           trade_type: str, timestamp: float = None):
        """Record trade result for anchor system performance tracking"""
        if self.anchor_enabled and self.anchor_system:
            self.anchor_system.record_trade_result(entry_price, exit_price, trade_type, timestamp)
    
    def should_reset_anchor(self) -> bool:
        """Check if anchor should be reset based on DGT conditions"""
        if not self.anchor_enabled or not self.anchor_system or not self.anchor_system.primary_anchor:
            return False
            
        # Let the anchor system determine if reset is needed
        if self.close_history:
            current_price = self.close_history[-1]
            return self.anchor_system._should_reset_anchor(current_price, time.time())
        
        return False
    
    def get_anchor_metrics(self) -> Dict:
        """Get anchor system performance metrics"""
        if not self.anchor_enabled:
            return {'enabled': False}
        
        if not self.anchor_system:
            return {'enabled': False}
            
        anchor_metrics = self.anchor_system.get_anchor_metrics()
        anchor_info = self.anchor_system.get_current_anchor_info()
        
        return {
            'enabled': True,
            'anchor_info': anchor_info,
            'performance_metrics': {
                'total_return': anchor_metrics.total_return,
                'sharpe_ratio': anchor_metrics.sharpe_ratio,
                'max_drawdown': anchor_metrics.max_drawdown,
                'win_rate': anchor_metrics.win_rate,
                'volatility': anchor_metrics.volatility,
                'reset_frequency': anchor_metrics.reset_frequency
            }
        }
    
    def force_anchor_reset(self, reason: str = "manual"):
        """Force anchor reset for testing or manual intervention"""
        if self.anchor_enabled and self.anchor_system and self.close_history:
            current_price = self.close_history[-1]
            self.anchor_system.force_anchor_reset(current_price, reason)
    
    def optimize_anchor_system(self, lookback_days: int = 30):
        """Optimize anchor parameters based on historical performance"""
        if self.anchor_enabled and self.anchor_system:
            self.anchor_system.optimize_anchor_parameters(lookback_days)