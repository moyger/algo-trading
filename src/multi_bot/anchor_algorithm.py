import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass
from collections import deque
import logging
import time
import math
from enum import Enum

logger = logging.getLogger(__name__)

class AnchorType(Enum):
    PRICE_BASED = "price_based"
    VOLATILITY_BASED = "volatility_based"
    VOLUME_WEIGHTED = "volume_weighted"
    REGIME_ADAPTIVE = "regime_adaptive"
    MOMENTUM_BASED = "momentum_based"

class AnchorResetTrigger(Enum):
    TIME_BASED = "time_based"
    PRICE_DEVIATION = "price_deviation"
    VOLATILITY_SPIKE = "volatility_spike"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    REGIME_CHANGE = "regime_change"

@dataclass
class AnchorPoint:
    price: float
    timestamp: float
    anchor_type: AnchorType
    confidence: float
    weight: float
    volatility_estimate: float
    performance_score: float = 0.0
    reset_count: int = 0
    
@dataclass
class AnchorMetrics:
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    avg_trade_duration: float
    volatility: float
    reset_frequency: float

class DynamicAnchorSystem:
    """
    Dynamic Grid Trading (DGT) Anchor Algorithm
    
    Based on the arXiv paper methodology, this system implements:
    1. Dynamic anchor positioning to overcome zero-expectation limitations
    2. Multi-criteria anchor reset mechanisms
    3. Performance-optimized grid repositioning
    4. Risk-managed anchor adaptation
    """
    
    def __init__(self,
                 symbol: str,
                 lookback_period: int = 50,
                 anchor_reset_threshold: float = 0.05,  # 5% deviation
                 min_reset_interval: int = 3600,        # 1 hour minimum
                 max_anchor_age: int = 86400,           # 24 hours maximum
                 performance_window: int = 20,
                 volatility_multiplier: float = 2.0):
        
        self.symbol = symbol
        self.lookback_period = lookback_period
        self.anchor_reset_threshold = anchor_reset_threshold
        self.min_reset_interval = min_reset_interval
        self.max_anchor_age = max_anchor_age
        self.performance_window = performance_window
        self.volatility_multiplier = volatility_multiplier
        
        # Price and performance history
        self.price_history = deque(maxlen=lookback_period * 2)
        self.volume_history = deque(maxlen=lookback_period)
        self.return_history = deque(maxlen=performance_window)
        
        # Current anchor points
        self.primary_anchor: Optional[AnchorPoint] = None
        self.secondary_anchor: Optional[AnchorPoint] = None
        self.anchor_history: List[AnchorPoint] = []
        
        # Performance tracking
        self.cumulative_return = 0.0
        self.trades_executed = 0
        self.successful_trades = 0
        self.last_reset_time = 0
        self.total_resets = 0
        
        # Statistical measures
        self.current_volatility = 0.0
        self.momentum_score = 0.0
        self.regime_stability = 1.0
        
    def update_market_data(self, price: float, volume: float = None, timestamp: float = None):
        """Update market data and evaluate anchor positioning"""
        if timestamp is None:
            timestamp = time.time()
            
        self.price_history.append((price, timestamp))
        if volume:
            self.volume_history.append(volume)
        
        # Calculate current statistics
        self._update_statistics()
        
        # Initialize first anchor if needed
        if self.primary_anchor is None:
            self._initialize_primary_anchor(price, timestamp)
        
        # Evaluate anchor reset conditions
        if self._should_reset_anchor(price, timestamp):
            self._reset_anchor(price, timestamp)
    
    def _update_statistics(self):
        """Update current market statistics"""
        if len(self.price_history) < 2:
            return
        
        prices = [p[0] for p in list(self.price_history)]
        
        # Calculate volatility (rolling standard deviation of returns)
        if len(prices) >= 10:
            returns = np.diff(np.log(prices[-20:]))  # Last 20 periods
            self.current_volatility = np.std(returns) * np.sqrt(len(returns))
        
        # Calculate momentum score (price momentum over lookback period)
        if len(prices) >= self.lookback_period:
            short_ma = np.mean(prices[-10:])
            long_ma = np.mean(prices[-self.lookback_period:])
            self.momentum_score = (short_ma - long_ma) / long_ma
        
        # Calculate regime stability (consistency of price direction)
        if len(prices) >= 20:
            recent_returns = np.diff(prices[-20:])
            direction_changes = np.sum(np.diff(np.sign(recent_returns)) != 0)
            self.regime_stability = max(0.1, 1.0 - (direction_changes / 18.0))
    
    def _initialize_primary_anchor(self, price: float, timestamp: float):
        """Initialize the primary anchor point"""
        anchor = AnchorPoint(
            price=price,
            timestamp=timestamp,
            anchor_type=AnchorType.PRICE_BASED,
            confidence=1.0,
            weight=1.0,
            volatility_estimate=self.current_volatility or 0.02
        )
        
        self.primary_anchor = anchor
        self.anchor_history.append(anchor)
        
        logger.info(f"Initialized primary anchor at price {price:.6f}")
    
    def _should_reset_anchor(self, current_price: float, timestamp: float) -> bool:
        """
        Determine if anchor should be reset based on DGT methodology
        
        Reset conditions based on the paper's "dynamic repositioning":
        1. Price deviation exceeds threshold
        2. Volatility regime change
        3. Performance degradation
        4. Time-based reset (prevent stale anchors)
        """
        if not self.primary_anchor:
            return False
        
        # Time-based reset (maximum anchor age)
        anchor_age = timestamp - self.primary_anchor.timestamp
        if anchor_age > self.max_anchor_age:
            logger.info(f"Anchor reset: Maximum age exceeded ({anchor_age:.0f}s)")
            return True
        
        # Minimum reset interval protection
        time_since_reset = timestamp - self.last_reset_time
        if time_since_reset < self.min_reset_interval:
            return False
        
        # Price deviation reset
        price_deviation = abs(current_price - self.primary_anchor.price) / self.primary_anchor.price
        if price_deviation > self.anchor_reset_threshold:
            logger.info(f"Anchor reset: Price deviation {price_deviation:.3%} > threshold {self.anchor_reset_threshold:.3%}")
            return True
        
        # Volatility spike reset
        if self.current_volatility > self.primary_anchor.volatility_estimate * self.volatility_multiplier:
            logger.info(f"Anchor reset: Volatility spike {self.current_volatility:.4f} > {self.primary_anchor.volatility_estimate * self.volatility_multiplier:.4f}")
            return True
        
        # Performance degradation reset
        if self._is_performance_degrading():
            logger.info("Anchor reset: Performance degradation detected")
            return True
        
        return False
    
    def _is_performance_degrading(self) -> bool:
        """Check if recent performance suggests anchor reset needed"""
        if len(self.return_history) < self.performance_window // 2:
            return False
        
        recent_returns = list(self.return_history)[-10:]  # Last 10 trades
        if not recent_returns:
            return False
        
        # Check if recent performance is significantly worse
        recent_avg = np.mean(recent_returns)
        overall_avg = np.mean(list(self.return_history))
        
        # Reset if recent performance is more than 2 standard deviations worse
        if len(self.return_history) >= 10:
            std_dev = np.std(list(self.return_history))
            if recent_avg < overall_avg - 2 * std_dev:
                return True
        
        return False
    
    def _reset_anchor(self, price: float, timestamp: float):
        """Reset anchor using optimal positioning strategy"""
        
        # Store previous anchor performance
        if self.primary_anchor:
            self.primary_anchor.performance_score = self._calculate_anchor_performance()
            self.primary_anchor.reset_count += 1
        
        # Calculate optimal anchor type based on current market conditions
        anchor_type = self._determine_optimal_anchor_type()
        
        # Calculate optimal anchor price using the selected strategy
        optimal_price = self._calculate_optimal_anchor_price(price, anchor_type)
        
        # Create new anchor
        new_anchor = AnchorPoint(
            price=optimal_price,
            timestamp=timestamp,
            anchor_type=anchor_type,
            confidence=self._calculate_anchor_confidence(),
            weight=self._calculate_anchor_weight(),
            volatility_estimate=max(self.current_volatility, 0.01)
        )
        
        # Update anchors
        self.secondary_anchor = self.primary_anchor  # Keep previous as secondary
        self.primary_anchor = new_anchor
        self.anchor_history.append(new_anchor)
        
        # Update tracking
        self.last_reset_time = timestamp
        self.total_resets += 1
        
        logger.info(f"Anchor reset #{self.total_resets}: {anchor_type.value} anchor at {optimal_price:.6f} "
                   f"(current: {price:.6f}, deviation: {abs(price-optimal_price)/price:.3%})")
    
    def _determine_optimal_anchor_type(self) -> AnchorType:
        """Determine the optimal anchor type based on current market conditions"""
        
        # High volatility -> volatility-based anchor
        if self.current_volatility > 0.04:  # 4% volatility threshold
            return AnchorType.VOLATILITY_BASED
        
        # Strong momentum -> momentum-based anchor
        if abs(self.momentum_score) > 0.02:  # 2% momentum threshold
            return AnchorType.MOMENTUM_BASED
        
        # Regime instability -> regime-adaptive anchor
        if self.regime_stability < 0.5:
            return AnchorType.REGIME_ADAPTIVE
        
        # High volume available -> volume-weighted anchor
        if len(self.volume_history) >= 10:
            recent_volume = np.mean(list(self.volume_history)[-5:])
            avg_volume = np.mean(list(self.volume_history))
            if recent_volume > avg_volume * 1.5:
                return AnchorType.VOLUME_WEIGHTED
        
        # Default to price-based anchor
        return AnchorType.PRICE_BASED
    
    def _calculate_optimal_anchor_price(self, current_price: float, anchor_type: AnchorType) -> float:
        """
        Calculate optimal anchor price based on DGT methodology
        
        This implements the core "dynamic repositioning" logic from the paper
        """
        
        if len(self.price_history) < 10:
            return current_price
        
        prices = [p[0] for p in list(self.price_history)]
        
        if anchor_type == AnchorType.PRICE_BASED:
            # Simple moving average anchor
            return np.mean(prices[-20:]) if len(prices) >= 20 else current_price
        
        elif anchor_type == AnchorType.VOLATILITY_BASED:
            # Volatility-adjusted anchor (mean reversion point)
            lookback = min(30, len(prices))
            price_mean = np.mean(prices[-lookback:])
            price_std = np.std(prices[-lookback:])
            
            # Position anchor at mean +/- 0.5 standard deviations based on current position
            if current_price > price_mean:
                return price_mean - 0.5 * price_std
            else:
                return price_mean + 0.5 * price_std
        
        elif anchor_type == AnchorType.MOMENTUM_BASED:
            # Momentum-aware anchor positioning
            if self.momentum_score > 0:  # Upward momentum
                # Place anchor below current price to catch pullbacks
                return current_price * (1 - self.current_volatility * 0.5)
            else:  # Downward momentum
                # Place anchor above current price to catch bounces
                return current_price * (1 + self.current_volatility * 0.5)
        
        elif anchor_type == AnchorType.VOLUME_WEIGHTED:
            # Volume-weighted average price anchor
            if len(self.volume_history) >= len(prices):
                recent_prices = prices[-10:]
                recent_volumes = list(self.volume_history)[-10:]
                
                total_volume = sum(recent_volumes)
                if total_volume > 0:
                    vwap = sum(p * v for p, v in zip(recent_prices, recent_volumes)) / total_volume
                    return vwap
            
            return current_price
        
        elif anchor_type == AnchorType.REGIME_ADAPTIVE:
            # Regime-adaptive anchor (adaptive to market regime changes)
            # Use exponential moving average with adaptive smoothing
            alpha = max(0.1, self.regime_stability)
            if self.primary_anchor:
                ema = alpha * current_price + (1 - alpha) * self.primary_anchor.price
                return ema
            else:
                return current_price
        
        return current_price
    
    def _calculate_anchor_confidence(self) -> float:
        """Calculate confidence score for the new anchor"""
        confidence_factors = []
        
        # Regime stability factor
        confidence_factors.append(self.regime_stability)
        
        # Data sufficiency factor
        data_factor = min(1.0, len(self.price_history) / self.lookback_period)
        confidence_factors.append(data_factor)
        
        # Volatility stability factor (lower volatility = higher confidence)
        vol_factor = max(0.1, 1.0 - min(1.0, self.current_volatility / 0.1))
        confidence_factors.append(vol_factor)
        
        # Historical performance factor
        if self.anchor_history:
            perf_scores = [a.performance_score for a in self.anchor_history if a.performance_score > 0]
            if perf_scores:
                avg_perf = np.mean(perf_scores)
                perf_factor = max(0.1, min(1.0, avg_perf))
                confidence_factors.append(perf_factor)
        
        return np.mean(confidence_factors)
    
    def _calculate_anchor_weight(self) -> float:
        """Calculate weight for the anchor in grid calculations"""
        base_weight = 1.0
        
        # Increase weight for high-confidence anchors
        confidence_bonus = (self._calculate_anchor_confidence() - 0.5) * 0.5
        
        # Increase weight for stable regimes
        stability_bonus = (self.regime_stability - 0.5) * 0.3
        
        return max(0.1, base_weight + confidence_bonus + stability_bonus)
    
    def _calculate_anchor_performance(self) -> float:
        """Calculate performance score for current anchor"""
        if not self.primary_anchor or len(self.return_history) < 5:
            return 0.0
        
        # Get returns since anchor was set
        anchor_age = time.time() - self.primary_anchor.timestamp
        anchor_age_trades = min(len(self.return_history), int(anchor_age / 300))  # Assume 5min avg trade
        
        if anchor_age_trades <= 0:
            return 0.0
        
        recent_returns = list(self.return_history)[-anchor_age_trades:]
        
        # Calculate risk-adjusted return (simplified Sharpe)
        avg_return = np.mean(recent_returns)
        std_return = np.std(recent_returns)
        
        if std_return > 0:
            return avg_return / std_return
        else:
            return avg_return if avg_return > 0 else 0.0
    
    def get_anchor_grid_levels(self, 
                              current_price: float, 
                              base_grid_spacing: float,
                              num_levels: int = 20) -> Tuple[List[float], List[float]]:
        """
        Generate grid levels anchored to the current anchor system
        
        This is the core DGT implementation that uses anchors to position grids
        """
        
        if not self.primary_anchor:
            # Fallback to current price if no anchor
            anchor_price = current_price
        else:
            anchor_price = self.primary_anchor.price
        
        # Adjust grid spacing based on anchor confidence and volatility
        adjusted_spacing = self._get_adjusted_grid_spacing(base_grid_spacing)
        
        # Generate buy levels (below anchor)
        buy_levels = []
        for i in range(1, num_levels // 2 + 1):
            level_price = anchor_price * (1 - adjusted_spacing * i)
            buy_levels.append(level_price)
        
        # Generate sell levels (above anchor)  
        sell_levels = []
        for i in range(1, num_levels // 2 + 1):
            level_price = anchor_price * (1 + adjusted_spacing * i)
            sell_levels.append(level_price)
        
        return buy_levels, sell_levels
    
    def _get_adjusted_grid_spacing(self, base_spacing: float) -> float:
        """Adjust grid spacing based on anchor characteristics"""
        
        if not self.primary_anchor:
            return base_spacing
        
        # Base adjustment factors
        adjustments = []
        
        # Confidence adjustment (higher confidence = tighter spacing)
        confidence_adj = 0.8 + 0.4 * self.primary_anchor.confidence
        adjustments.append(confidence_adj)
        
        # Volatility adjustment (higher volatility = wider spacing)
        vol_adj = max(0.5, min(2.0, 1.0 + self.current_volatility * 5.0))
        adjustments.append(vol_adj)
        
        # Momentum adjustment
        momentum_adj = 1.0 + abs(self.momentum_score) * 2.0
        adjustments.append(momentum_adj)
        
        # Regime stability adjustment
        regime_adj = 0.7 + 0.6 * self.regime_stability
        adjustments.append(regime_adj)
        
        # Calculate final adjustment
        final_adjustment = np.mean(adjustments)
        
        return base_spacing * final_adjustment
    
    def record_trade_result(self, entry_price: float, exit_price: float, 
                           trade_type: str, timestamp: float = None):
        """Record trade result for performance tracking"""
        
        if timestamp is None:
            timestamp = time.time()
        
        # Calculate return
        if trade_type.lower() == 'buy':
            trade_return = (exit_price - entry_price) / entry_price
        else:  # sell
            trade_return = (entry_price - exit_price) / entry_price
        
        self.return_history.append(trade_return)
        self.cumulative_return += trade_return
        self.trades_executed += 1
        
        if trade_return > 0:
            self.successful_trades += 1
    
    def get_anchor_metrics(self) -> AnchorMetrics:
        """Get comprehensive anchor system metrics"""
        
        if not self.return_history:
            return AnchorMetrics(0, 0, 0, 0, 0, 0, 0)
        
        returns = np.array(list(self.return_history))
        
        # Calculate metrics
        total_return = self.cumulative_return
        sharpe_ratio = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        max_drawdown = self._calculate_max_drawdown()
        win_rate = self.successful_trades / self.trades_executed if self.trades_executed > 0 else 0
        
        # Calculate average trade duration (estimate)
        if self.anchor_history:
            total_time = time.time() - self.anchor_history[0].timestamp
            avg_trade_duration = total_time / max(1, self.trades_executed)
        else:
            avg_trade_duration = 0
        
        volatility = np.std(returns) if len(returns) > 1 else 0
        
        # Reset frequency (resets per day)
        if self.anchor_history:
            total_time = time.time() - self.anchor_history[0].timestamp
            reset_frequency = self.total_resets / max(1, total_time / 86400)  # per day
        else:
            reset_frequency = 0
        
        return AnchorMetrics(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            avg_trade_duration=avg_trade_duration,
            volatility=volatility,
            reset_frequency=reset_frequency
        )
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from cumulative returns"""
        if not self.return_history:
            return 0.0
        
        cumulative = np.cumsum(list(self.return_history))
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        
        return np.max(drawdown) if len(drawdown) > 0 else 0.0
    
    def get_current_anchor_info(self) -> Dict:
        """Get current anchor information for monitoring"""
        
        if not self.primary_anchor:
            return {"status": "no_anchor"}
        
        current_time = time.time()
        
        return {
            "anchor_price": self.primary_anchor.price,
            "anchor_type": self.primary_anchor.anchor_type.value,
            "confidence": self.primary_anchor.confidence,
            "weight": self.primary_anchor.weight,
            "age_seconds": current_time - self.primary_anchor.timestamp,
            "performance_score": self.primary_anchor.performance_score,
            "reset_count": self.total_resets,
            "current_volatility": self.current_volatility,
            "momentum_score": self.momentum_score,
            "regime_stability": self.regime_stability
        }
    
    def force_anchor_reset(self, price: float, reason: str = "manual", timestamp: float = None):
        """Force an anchor reset (for testing or manual intervention)"""
        if timestamp is None:
            timestamp = time.time()
        
        logger.info(f"Forcing anchor reset: {reason}")
        self._reset_anchor(price, timestamp)
    
    def optimize_anchor_parameters(self, lookback_days: int = 30):
        """
        Optimize anchor parameters based on historical performance
        This implements the "market outperformance" aspect from the DGT paper
        """
        
        if len(self.anchor_history) < 3:
            return
        
        # Analyze historical anchor performance
        anchor_performances = []
        for anchor in self.anchor_history[-lookback_days:]:
            if anchor.performance_score > 0:
                anchor_performances.append({
                    'type': anchor.anchor_type,
                    'performance': anchor.performance_score,
                    'volatility': anchor.volatility_estimate,
                    'confidence': anchor.confidence
                })
        
        if not anchor_performances:
            return
        
        # Find best performing anchor types
        type_performance = {}
        for perf in anchor_performances:
            anchor_type = perf['type']
            if anchor_type not in type_performance:
                type_performance[anchor_type] = []
            type_performance[anchor_type].append(perf['performance'])
        
        # Update parameters based on best performers
        best_type = max(type_performance.keys(), 
                       key=lambda t: np.mean(type_performance[t]))
        
        best_avg_performance = np.mean(type_performance[best_type])
        
        # Adjust reset threshold based on performance
        if best_avg_performance > 1.0:  # Good performance
            self.anchor_reset_threshold *= 1.1  # Allow larger deviations
        elif best_avg_performance < 0.5:  # Poor performance  
            self.anchor_reset_threshold *= 0.9  # Reset more aggressively
        
        # Bound the threshold
        self.anchor_reset_threshold = max(0.02, min(0.10, self.anchor_reset_threshold))
        
        logger.info(f"Optimized anchor parameters: best_type={best_type.value}, "
                   f"performance={best_avg_performance:.3f}, "
                   f"new_threshold={self.anchor_reset_threshold:.3%}")