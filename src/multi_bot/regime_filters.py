import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import deque
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class MarketRegime(Enum):
    STRONG_UPTREND = "strong_uptrend"
    WEAK_UPTREND = "weak_uptrend"
    RANGING_HIGH = "ranging_high"
    RANGING_NEUTRAL = "ranging_neutral"
    RANGING_LOW = "ranging_low"
    WEAK_DOWNTREND = "weak_downtrend"
    STRONG_DOWNTREND = "strong_downtrend"
    VOLATILE = "volatile"
    QUIET = "quiet"

@dataclass
class RegimeMetrics:
    regime: MarketRegime
    trend_strength: float  # ADX value
    momentum: float        # RSI value
    trend_direction: float # EMA slope
    volatility: float      # BB bandwidth
    volume_strength: float # Volume relative to average
    confidence: float      # Overall confidence (0-1)
    signals: Dict[str, float]  # Individual indicator signals

class RegimeFilterSystem:
    """
    Advanced regime detection system combining multiple technical indicators
    Inspired by eshan-292's adaptive approach with additional indicators
    """
    
    def __init__(self,
                 ema_fast_period: int = 12,
                 ema_slow_period: int = 26,
                 rsi_period: int = 14,
                 adx_period: int = 14,
                 bb_period: int = 20,
                 bb_std: float = 2.0,
                 volume_period: int = 20,
                 max_history: int = 100):
        
        # Configuration parameters
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.rsi_period = rsi_period
        self.adx_period = adx_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.volume_period = volume_period
        
        # Price and volume history
        max_length = max(ema_slow_period, rsi_period, adx_period, bb_period, volume_period) + 10
        self.prices = deque(maxlen=max_length)
        self.highs = deque(maxlen=max_length)
        self.lows = deque(maxlen=max_length)
        self.closes = deque(maxlen=max_length)
        self.volumes = deque(maxlen=max_length)
        
        # Calculated indicators
        self.ema_fast = deque(maxlen=max_history)
        self.ema_slow = deque(maxlen=max_history)
        self.rsi_values = deque(maxlen=max_history)
        self.adx_values = deque(maxlen=max_history)
        self.bb_upper = deque(maxlen=max_history)
        self.bb_middle = deque(maxlen=max_history)
        self.bb_lower = deque(maxlen=max_history)
        self.volume_sma = deque(maxlen=max_history)
        
        # Current regime state
        self.current_regime = MarketRegime.RANGING_NEUTRAL
        self.regime_confidence = 0.5
        self.last_update_time = 0
        
        # Thresholds (inspired by eshan-292's adaptive approach)
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.adx_trend_threshold = 25
        self.adx_strong_threshold = 40
        self.volume_threshold = 1.2  # 20% above average
        
    def update_market_data(self, high: float, low: float, close: float, volume: float = None):
        """Update with new market data"""
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        if volume:
            self.volumes.append(volume)
        
        # Calculate all indicators if we have enough data
        if len(self.closes) >= self.ema_slow_period:
            self._calculate_emas()
            
        if len(self.closes) >= self.rsi_period:
            self._calculate_rsi()
            
        if len(self.closes) >= self.adx_period:
            self._calculate_adx()
            
        if len(self.closes) >= self.bb_period:
            self._calculate_bollinger_bands()
            
        if len(self.volumes) >= self.volume_period:
            self._calculate_volume_indicators()
    
    def _calculate_emas(self):
        """Calculate Exponential Moving Averages"""
        if len(self.closes) < self.ema_slow_period:
            return
            
        # Fast EMA
        if len(self.ema_fast) == 0:
            # Initialize with SMA
            fast_sma = np.mean(list(self.closes)[-self.ema_fast_period:])
            self.ema_fast.append(fast_sma)
        else:
            alpha_fast = 2 / (self.ema_fast_period + 1)
            ema_fast = alpha_fast * self.closes[-1] + (1 - alpha_fast) * self.ema_fast[-1]
            self.ema_fast.append(ema_fast)
        
        # Slow EMA
        if len(self.ema_slow) == 0:
            # Initialize with SMA
            slow_sma = np.mean(list(self.closes)[-self.ema_slow_period:])
            self.ema_slow.append(slow_sma)
        else:
            alpha_slow = 2 / (self.ema_slow_period + 1)
            ema_slow = alpha_slow * self.closes[-1] + (1 - alpha_slow) * self.ema_slow[-1]
            self.ema_slow.append(ema_slow)
    
    def _calculate_rsi(self):
        """Calculate Relative Strength Index"""
        if len(self.closes) < self.rsi_period + 1:
            return
        
        closes_list = list(self.closes)
        deltas = np.diff(closes_list[-self.rsi_period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        self.rsi_values.append(rsi)
    
    def _calculate_adx(self):
        """Calculate Average Directional Index (ADX)"""
        if len(self.closes) < self.adx_period + 1:
            return
        
        highs = np.array(list(self.highs)[-self.adx_period-1:])
        lows = np.array(list(self.lows)[-self.adx_period-1:])
        closes = np.array(list(self.closes)[-self.adx_period-1:])
        
        # True Range
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        
        # Directional Movement
        dm_plus = np.where(highs[1:] - highs[:-1] > lows[:-1] - lows[1:], 
                          np.maximum(highs[1:] - highs[:-1], 0), 0)
        dm_minus = np.where(lows[:-1] - lows[1:] > highs[1:] - highs[:-1], 
                           np.maximum(lows[:-1] - lows[1:], 0), 0)
        
        # Smoothed averages
        atr = np.mean(true_range)
        di_plus = 100 * np.mean(dm_plus) / atr if atr > 0 else 0
        di_minus = 100 * np.mean(dm_minus) / atr if atr > 0 else 0
        
        # ADX calculation
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) > 0 else 0
        
        if len(self.adx_values) == 0:
            adx = dx
        else:
            # Smoothed ADX
            adx = (self.adx_values[-1] * (self.adx_period - 1) + dx) / self.adx_period
        
        self.adx_values.append(adx)
    
    def _calculate_bollinger_bands(self):
        """Calculate Bollinger Bands"""
        if len(self.closes) < self.bb_period:
            return
        
        closes_list = list(self.closes)[-self.bb_period:]
        sma = np.mean(closes_list)
        std = np.std(closes_list)
        
        upper = sma + (self.bb_std * std)
        lower = sma - (self.bb_std * std)
        
        self.bb_upper.append(upper)
        self.bb_middle.append(sma)
        self.bb_lower.append(lower)
    
    def _calculate_volume_indicators(self):
        """Calculate volume-based indicators"""
        if len(self.volumes) < self.volume_period:
            return
        
        volume_sma = np.mean(list(self.volumes)[-self.volume_period:])
        self.volume_sma.append(volume_sma)
    
    def get_ema_signal(self) -> Tuple[float, str]:
        """Get EMA crossover signal and trend direction"""
        if len(self.ema_fast) < 2 or len(self.ema_slow) < 2:
            return 0.0, "insufficient_data"
        
        current_diff = self.ema_fast[-1] - self.ema_slow[-1]
        prev_diff = self.ema_fast[-2] - self.ema_slow[-2]
        
        # Crossover detection
        if prev_diff <= 0 and current_diff > 0:
            return 1.0, "bullish_crossover"  # Golden cross
        elif prev_diff >= 0 and current_diff < 0:
            return -1.0, "bearish_crossover"  # Death cross
        
        # Trend strength based on EMA distance
        if len(self.closes) > 0:
            ema_distance = current_diff / self.closes[-1]  # Normalized distance
            trend_strength = np.tanh(ema_distance * 100)  # Scale to [-1, 1]
            
            if trend_strength > 0.1:
                return trend_strength, "uptrend"
            elif trend_strength < -0.1:
                return trend_strength, "downtrend"
            else:
                return trend_strength, "sideways"
        
        return 0.0, "neutral"
    
    def get_rsi_signal(self) -> Tuple[float, str]:
        """Get RSI momentum signal"""
        if len(self.rsi_values) == 0:
            return 0.0, "insufficient_data"
        
        rsi = self.rsi_values[-1]
        
        if rsi >= self.rsi_overbought:
            return -1.0, "overbought"
        elif rsi <= self.rsi_oversold:
            return 1.0, "oversold"
        elif rsi > 60:
            return 0.5, "bullish"
        elif rsi < 40:
            return -0.5, "bearish"
        else:
            return 0.0, "neutral"
    
    def get_adx_signal(self) -> Tuple[float, str]:
        """Get ADX trend strength signal"""
        if len(self.adx_values) == 0:
            return 0.0, "insufficient_data"
        
        adx = self.adx_values[-1]
        
        if adx >= self.adx_strong_threshold:
            return 1.0, "strong_trend"
        elif adx >= self.adx_trend_threshold:
            return 0.6, "moderate_trend"
        else:
            return 0.0, "ranging"
    
    def get_bollinger_signal(self) -> Tuple[float, str]:
        """Get Bollinger Bands position and volatility signal"""
        if len(self.bb_upper) == 0 or len(self.closes) == 0:
            return 0.0, "insufficient_data"
        
        current_price = self.closes[-1]
        upper = self.bb_upper[-1]
        middle = self.bb_middle[-1]
        lower = self.bb_lower[-1]
        
        # Position within bands
        if current_price >= upper:
            position_signal = -0.8  # Near upper band - potential sell
            position_desc = "above_upper_band"
        elif current_price <= lower:
            position_signal = 0.8   # Near lower band - potential buy
            position_desc = "below_lower_band"
        else:
            # Normalize position within bands
            band_position = (current_price - lower) / (upper - lower)
            position_signal = (band_position - 0.5) * 2  # Scale to [-1, 1]
            if band_position > 0.7:
                position_desc = "near_upper_band"
            elif band_position < 0.3:
                position_desc = "near_lower_band"
            else:
                position_desc = "middle_band"
        
        # Bandwidth for volatility assessment
        bandwidth = (upper - lower) / middle
        
        return position_signal, f"{position_desc}_bw_{bandwidth:.4f}"
    
    def get_volume_signal(self) -> Tuple[float, str]:
        """Get volume strength signal"""
        if len(self.volumes) == 0 or len(self.volume_sma) == 0:
            return 0.0, "insufficient_data"
        
        current_volume = self.volumes[-1]
        avg_volume = self.volume_sma[-1]
        
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        if volume_ratio >= 2.0:
            return 1.0, "very_high_volume"
        elif volume_ratio >= self.volume_threshold:
            return 0.6, "high_volume"
        elif volume_ratio >= 0.8:
            return 0.0, "normal_volume"
        else:
            return -0.4, "low_volume"
    
    def classify_market_regime(self) -> RegimeMetrics:
        """
        Classify current market regime using multiple indicators
        Based on confluence approach from eshan-292 methodology
        """
        
        # Get individual signals
        ema_signal, ema_desc = self.get_ema_signal()
        rsi_signal, rsi_desc = self.get_rsi_signal()
        adx_signal, adx_desc = self.get_adx_signal()
        bb_signal, bb_desc = self.get_bollinger_signal()
        vol_signal, vol_desc = self.get_volume_signal()
        
        # Extract values for metrics
        trend_strength = self.adx_values[-1] if self.adx_values else 0
        momentum = self.rsi_values[-1] if self.rsi_values else 50
        trend_direction = ema_signal
        
        # Calculate volatility from Bollinger Bands
        if self.bb_upper and self.bb_middle:
            volatility = (self.bb_upper[-1] - self.bb_lower[-1]) / self.bb_middle[-1]
        else:
            volatility = 0.02  # Default 2%
        
        volume_strength = max(-1, min(1, (vol_signal + 1) / 2))  # Normalize to [0,1]
        
        # Regime classification logic
        regime = self._determine_regime(ema_signal, rsi_signal, adx_signal, bb_signal, vol_signal)
        
        # Calculate confidence based on signal agreement
        signals = [ema_signal, rsi_signal, adx_signal, bb_signal, vol_signal]
        valid_signals = [s for s in signals if s != 0.0]
        
        if len(valid_signals) > 0:
            signal_std = np.std(valid_signals)
            confidence = max(0.1, min(1.0, 1.0 - signal_std))
        else:
            confidence = 0.1
        
        # Store current regime
        self.current_regime = regime
        self.regime_confidence = confidence
        
        return RegimeMetrics(
            regime=regime,
            trend_strength=trend_strength,
            momentum=momentum,
            trend_direction=trend_direction,
            volatility=volatility,
            volume_strength=volume_strength,
            confidence=confidence,
            signals={
                'ema': ema_signal,
                'rsi': rsi_signal, 
                'adx': adx_signal,
                'bb': bb_signal,
                'volume': vol_signal
            }
        )
    
    def _determine_regime(self, ema_signal: float, rsi_signal: float, adx_signal: float, 
                         bb_signal: float, vol_signal: float) -> MarketRegime:
        """Determine market regime based on signal confluence"""
        
        # Strong trending conditions
        if adx_signal >= 0.8:  # Strong trend
            if ema_signal > 0.3 and rsi_signal >= 0:  # Bullish momentum
                return MarketRegime.STRONG_UPTREND
            elif ema_signal < -0.3 and rsi_signal <= 0:  # Bearish momentum
                return MarketRegime.STRONG_DOWNTREND
        
        # Moderate trending conditions
        elif adx_signal >= 0.4:  # Moderate trend
            if ema_signal > 0.1:
                return MarketRegime.WEAK_UPTREND
            elif ema_signal < -0.1:
                return MarketRegime.WEAK_DOWNTREND
        
        # Ranging conditions
        else:
            # High volatility ranging
            if self.bb_upper and self.bb_middle:
                bb_width = (self.bb_upper[-1] - self.bb_lower[-1]) / self.bb_middle[-1]
                if bb_width > 0.06:  # High volatility
                    return MarketRegime.VOLATILE
                elif bb_width < 0.02:  # Low volatility
                    return MarketRegime.QUIET
            
            # Position-based ranging classification
            if bb_signal > 0.3:
                return MarketRegime.RANGING_LOW    # Near lower BB
            elif bb_signal < -0.3:
                return MarketRegime.RANGING_HIGH   # Near upper BB
            else:
                return MarketRegime.RANGING_NEUTRAL
        
        return MarketRegime.RANGING_NEUTRAL
    
    def get_regime_grid_adjustments(self) -> Dict[str, float]:
        """
        Get grid trading adjustments based on current market regime
        Returns multipliers for grid spacing and level count
        """
        if not hasattr(self, 'current_regime'):
            return {'spacing_multiplier': 1.0, 'levels_multiplier': 1.0, 'bias': 'neutral'}
        
        regime = self.current_regime
        confidence = self.regime_confidence
        
        adjustments = {
            MarketRegime.STRONG_UPTREND: {
                'spacing_multiplier': 1.4 * confidence,
                'levels_multiplier': 0.7,
                'bias': 'long'
            },
            MarketRegime.WEAK_UPTREND: {
                'spacing_multiplier': 1.2 * confidence,
                'levels_multiplier': 0.85,
                'bias': 'long'
            },
            MarketRegime.STRONG_DOWNTREND: {
                'spacing_multiplier': 1.4 * confidence,
                'levels_multiplier': 0.7,
                'bias': 'short'
            },
            MarketRegime.WEAK_DOWNTREND: {
                'spacing_multiplier': 1.2 * confidence,
                'levels_multiplier': 0.85,
                'bias': 'short'
            },
            MarketRegime.RANGING_HIGH: {
                'spacing_multiplier': 0.8,
                'levels_multiplier': 1.2,
                'bias': 'short'
            },
            MarketRegime.RANGING_LOW: {
                'spacing_multiplier': 0.8,
                'levels_multiplier': 1.2,
                'bias': 'long'
            },
            MarketRegime.RANGING_NEUTRAL: {
                'spacing_multiplier': 1.0,
                'levels_multiplier': 1.0,
                'bias': 'neutral'
            },
            MarketRegime.VOLATILE: {
                'spacing_multiplier': 1.8,
                'levels_multiplier': 0.6,
                'bias': 'neutral'
            },
            MarketRegime.QUIET: {
                'spacing_multiplier': 0.6,
                'levels_multiplier': 1.4,
                'bias': 'neutral'
            }
        }
        
        return adjustments.get(regime, {
            'spacing_multiplier': 1.0,
            'levels_multiplier': 1.0,
            'bias': 'neutral'
        })
    
    def get_trading_recommendation(self) -> Dict[str, any]:
        """Get comprehensive trading recommendation based on regime analysis"""
        regime_metrics = self.classify_market_regime()
        grid_adjustments = self.get_regime_grid_adjustments()
        
        return {
            'regime': regime_metrics.regime.value,
            'confidence': regime_metrics.confidence,
            'grid_spacing_multiplier': grid_adjustments['spacing_multiplier'],
            'grid_levels_multiplier': grid_adjustments['levels_multiplier'],
            'position_bias': grid_adjustments['bias'],
            'trend_strength': regime_metrics.trend_strength,
            'momentum': regime_metrics.momentum,
            'volatility': regime_metrics.volatility,
            'volume_strength': regime_metrics.volume_strength,
            'individual_signals': regime_metrics.signals,
            'recommendation': self._generate_recommendation(regime_metrics)
        }
    
    def _generate_recommendation(self, metrics: RegimeMetrics) -> str:
        """Generate human-readable trading recommendation"""
        regime = metrics.regime
        confidence = metrics.confidence
        
        recommendations = {
            MarketRegime.STRONG_UPTREND: f"Strong uptrend detected (confidence: {confidence:.1%}). Consider wider grid spacing with long bias.",
            MarketRegime.WEAK_UPTREND: f"Weak uptrend detected (confidence: {confidence:.1%}). Moderate grid adjustments with slight long bias.",
            MarketRegime.STRONG_DOWNTREND: f"Strong downtrend detected (confidence: {confidence:.1%}). Consider wider grid spacing with short bias.",
            MarketRegime.WEAK_DOWNTREND: f"Weak downtrend detected (confidence: {confidence:.1%}). Moderate grid adjustments with slight short bias.",
            MarketRegime.RANGING_HIGH: f"Ranging near resistance (confidence: {confidence:.1%}). Tighter grids with short bias.",
            MarketRegime.RANGING_LOW: f"Ranging near support (confidence: {confidence:.1%}). Tighter grids with long bias.",
            MarketRegime.RANGING_NEUTRAL: f"Neutral ranging market (confidence: {confidence:.1%}). Standard grid parameters optimal.",
            MarketRegime.VOLATILE: f"High volatility detected (confidence: {confidence:.1%}). Wider grids recommended for safety.",
            MarketRegime.QUIET: f"Low volatility period (confidence: {confidence:.1%}). Tighter grids to capture small moves."
        }
        
        return recommendations.get(regime, f"Market regime unclear (confidence: {confidence:.1%}). Use standard parameters.")