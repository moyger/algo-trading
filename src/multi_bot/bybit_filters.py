"""
Bybit Precision Filters and Order Validation

This module provides comprehensive validation for Bybit orders,
ensuring all orders comply with exchange-specific precision requirements
and filter limits before submission.
"""

import math
import logging
from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RoundingMode(Enum):
    """Order rounding modes for different scenarios"""
    DOWN = ROUND_DOWN      # For sell quantities, max prices
    UP = ROUND_UP          # For buy quantities, min prices  
    HALF_UP = ROUND_HALF_UP  # For neutral rounding


@dataclass
class PriceFilter:
    """Bybit price filter constraints"""
    min_price: float
    max_price: float
    tick_size: float
    
    def validate(self, price: float) -> Tuple[bool, Optional[str]]:
        """Validate price against filter constraints"""
        if price < self.min_price:
            return False, f"Price {price} below minimum {self.min_price}"
        if price > self.max_price:
            return False, f"Price {price} above maximum {self.max_price}"
        
        # Check tick size alignment
        decimal_price = Decimal(str(price))
        decimal_tick = Decimal(str(self.tick_size))
        
        if decimal_price % decimal_tick != 0:
            return False, f"Price {price} not aligned with tick size {self.tick_size}"
            
        return True, None
    
    def round(self, price: float, mode: RoundingMode = RoundingMode.HALF_UP) -> float:
        """Round price to valid tick size"""
        decimal_price = Decimal(str(price))
        decimal_tick = Decimal(str(self.tick_size))
        
        # Calculate number of ticks
        num_ticks = decimal_price / decimal_tick
        
        # Round to nearest tick
        rounded_ticks = num_ticks.quantize(Decimal('1'), rounding=mode.value)
        
        # Convert back to price
        rounded_price = float(rounded_ticks * decimal_tick)
        
        # Ensure within bounds
        return max(self.min_price, min(self.max_price, rounded_price))


@dataclass
class LotSizeFilter:
    """Bybit lot size (quantity) filter constraints"""
    min_order_qty: float
    max_order_qty: float
    qty_step: float
    post_only_max_order_qty: Optional[float] = None
    max_mkt_order_qty: Optional[float] = None
    
    def validate(self, qty: float, is_market: bool = False, is_post_only: bool = False) -> Tuple[bool, Optional[str]]:
        """Validate quantity against filter constraints"""
        if qty < self.min_order_qty:
            return False, f"Quantity {qty} below minimum {self.min_order_qty}"
            
        # Check appropriate max based on order type
        if is_market and self.max_mkt_order_qty:
            if qty > self.max_mkt_order_qty:
                return False, f"Market order quantity {qty} above maximum {self.max_mkt_order_qty}"
        elif is_post_only and self.post_only_max_order_qty:
            if qty > self.post_only_max_order_qty:
                return False, f"Post-only quantity {qty} above maximum {self.post_only_max_order_qty}"
        else:
            if qty > self.max_order_qty:
                return False, f"Quantity {qty} above maximum {self.max_order_qty}"
        
        # Check qty step alignment
        decimal_qty = Decimal(str(qty))
        decimal_step = Decimal(str(self.qty_step))
        
        if decimal_qty % decimal_step != 0:
            return False, f"Quantity {qty} not aligned with step size {self.qty_step}"
            
        return True, None
    
    def round(self, qty: float, mode: RoundingMode = RoundingMode.DOWN) -> float:
        """Round quantity to valid step size"""
        decimal_qty = Decimal(str(qty))
        decimal_step = Decimal(str(self.qty_step))
        
        # Calculate number of steps
        num_steps = decimal_qty / decimal_step
        
        # Round to nearest step
        rounded_steps = num_steps.quantize(Decimal('1'), rounding=mode.value)
        
        # Convert back to quantity
        rounded_qty = float(rounded_steps * decimal_step)
        
        # Ensure within bounds
        return max(self.min_order_qty, min(self.max_order_qty, rounded_qty))


@dataclass
class MarketFilter:
    """Bybit market filter constraints"""
    min_notional_value: float = 5.0  # Default $5 for Bybit
    
    def validate(self, price: float, qty: float) -> Tuple[bool, Optional[str]]:
        """Validate notional value"""
        notional = price * qty
        if notional < self.min_notional_value:
            return False, f"Notional value {notional:.2f} below minimum {self.min_notional_value}"
        return True, None
    
    def calculate_min_qty(self, price: float) -> float:
        """Calculate minimum quantity for given price"""
        return self.min_notional_value / price


@dataclass
class SymbolFilters:
    """Complete filter set for a Bybit symbol"""
    symbol: str
    price_filter: PriceFilter
    lot_size_filter: LotSizeFilter
    market_filter: MarketFilter
    max_leverage: int = 200
    max_orders: int = 500
    max_conditional_orders: int = 10
    
    # Cached precision values for quick access
    price_precision: int = field(init=False)
    qty_precision: int = field(init=False)
    
    def __post_init__(self):
        """Calculate precision values after initialization"""
        # Calculate price precision from tick size
        tick_str = str(self.price_filter.tick_size)
        if '.' in tick_str:
            self.price_precision = len(tick_str.split('.')[1])
        else:
            self.price_precision = 0
            
        # Calculate quantity precision from qty step
        step_str = str(self.lot_size_filter.qty_step)
        if '.' in step_str:
            self.qty_precision = len(step_str.split('.')[1])
        else:
            self.qty_precision = 0
    
    def validate_order(self, 
                      price: float, 
                      qty: float, 
                      is_market: bool = False,
                      is_post_only: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Comprehensive order validation
        
        Returns:
            (is_valid, error_message)
        """
        # Validate price (skip for market orders)
        if not is_market:
            valid, error = self.price_filter.validate(price)
            if not valid:
                return False, error
        
        # Validate quantity
        valid, error = self.lot_size_filter.validate(qty, is_market, is_post_only)
        if not valid:
            return False, error
        
        # Validate notional value
        valid, error = self.market_filter.validate(price, qty)
        if not valid:
            return False, error
            
        return True, None
    
    def round_order(self, 
                   price: float, 
                   qty: float,
                   side: str = 'buy') -> Tuple[float, float]:
        """
        Round order parameters to valid precision
        
        Args:
            price: Order price
            qty: Order quantity
            side: 'buy' or 'sell'
            
        Returns:
            (rounded_price, rounded_quantity)
        """
        # Round price based on side
        if side == 'buy':
            # For buy orders, round price down (more favorable)
            rounded_price = self.price_filter.round(price, RoundingMode.DOWN)
        else:
            # For sell orders, round price up (more favorable)
            rounded_price = self.price_filter.round(price, RoundingMode.UP)
        
        # Round quantity (always down to avoid exceeding balance)
        rounded_qty = self.lot_size_filter.round(qty, RoundingMode.DOWN)
        
        # Ensure minimum notional value
        min_qty = self.market_filter.calculate_min_qty(rounded_price)
        if rounded_qty < min_qty:
            # Round up to meet minimum notional
            rounded_qty = self.lot_size_filter.round(min_qty, RoundingMode.UP)
        
        return rounded_price, rounded_qty
    
    def format_price(self, price: float) -> str:
        """Format price with correct precision for API"""
        return f"{price:.{self.price_precision}f}"
    
    def format_qty(self, qty: float) -> str:
        """Format quantity with correct precision for API"""
        return f"{qty:.{self.qty_precision}f}"


class FilterManager:
    """Manager for multiple symbol filters"""
    
    def __init__(self):
        self.filters: Dict[str, SymbolFilters] = {}
        self._cache_ttl = 3600  # Cache for 1 hour
        self._last_update: Dict[str, float] = {}
    
    def add_symbol(self, symbol_filters: SymbolFilters):
        """Add or update filters for a symbol"""
        self.filters[symbol_filters.symbol] = symbol_filters
        self._last_update[symbol_filters.symbol] = time.time()
        logger.info(f"Added filters for {symbol_filters.symbol}")
    
    def get_filters(self, symbol: str) -> Optional[SymbolFilters]:
        """Get filters for a symbol"""
        return self.filters.get(symbol)
    
    def needs_update(self, symbol: str) -> bool:
        """Check if filters need updating"""
        if symbol not in self._last_update:
            return True
        
        import time
        return (time.time() - self._last_update[symbol]) > self._cache_ttl
    
    @classmethod
    def from_market_info(cls, market_info: Dict[str, Any]) -> SymbolFilters:
        """
        Create SymbolFilters from Bybit market info response
        
        Args:
            market_info: Market info from Bybit API or ccxt
        """
        # Extract filter information
        if 'priceFilter' in market_info:
            # Direct Bybit API response format
            price_filter = PriceFilter(
                min_price=float(market_info['priceFilter']['minPrice']),
                max_price=float(market_info['priceFilter']['maxPrice']),
                tick_size=float(market_info['priceFilter']['tickSize'])
            )
            
            lot_size_filter = LotSizeFilter(
                min_order_qty=float(market_info['lotSizeFilter']['minOrderQty']),
                max_order_qty=float(market_info['lotSizeFilter']['maxOrderQty']),
                qty_step=float(market_info['lotSizeFilter']['qtyStep']),
                post_only_max_order_qty=float(market_info['lotSizeFilter'].get('postOnlyMaxOrderQty', 0)) or None,
                max_mkt_order_qty=float(market_info['lotSizeFilter'].get('maxMktOrderQty', 0)) or None
            )
            
            min_notional = float(market_info['lotSizeFilter'].get('minNotionalValue', 5))
            
        else:
            # CCXT format
            limits = market_info.get('limits', {})
            precision = market_info.get('precision', {})
            
            # Price filter from limits and precision
            price_filter = PriceFilter(
                min_price=limits.get('price', {}).get('min', 0.00001),
                max_price=limits.get('price', {}).get('max', 999999),
                tick_size=10 ** (-precision.get('price', 2)) if isinstance(precision.get('price'), int) else precision.get('price', 0.01)
            )
            
            # Lot size filter from limits and precision
            lot_size_filter = LotSizeFilter(
                min_order_qty=limits.get('amount', {}).get('min', 0.001),
                max_order_qty=limits.get('amount', {}).get('max', 10000),
                qty_step=10 ** (-precision.get('amount', 3)) if isinstance(precision.get('amount'), int) else precision.get('amount', 0.001),
                post_only_max_order_qty=None,
                max_mkt_order_qty=limits.get('market', {}).get('max')
            )
            
            min_notional = limits.get('cost', {}).get('min', 5.0)
        
        market_filter = MarketFilter(min_notional_value=min_notional)
        
        return SymbolFilters(
            symbol=market_info.get('symbol', 'UNKNOWN'),
            price_filter=price_filter,
            lot_size_filter=lot_size_filter,
            market_filter=market_filter,
            max_leverage=market_info.get('limits', {}).get('leverage', {}).get('max', 200)
        )


def validate_grid_parameters(filters: SymbolFilters, 
                            grid_spacing: float,
                            base_quantity: float,
                            current_price: float,
                            num_levels: int) -> Tuple[bool, Optional[str]]:
    """
    Validate grid trading parameters against Bybit filters
    
    Args:
        filters: Symbol filters
        grid_spacing: Grid spacing percentage
        base_quantity: Base order quantity
        current_price: Current market price
        num_levels: Number of grid levels
        
    Returns:
        (is_valid, error_message)
    """
    # Check minimum grid spacing
    min_price_diff = filters.price_filter.tick_size * 2
    actual_spacing = current_price * grid_spacing
    
    if actual_spacing < min_price_diff:
        return False, f"Grid spacing {actual_spacing:.8f} less than minimum {min_price_diff:.8f}"
    
    # Check quantity validity
    valid, error = filters.lot_size_filter.validate(base_quantity)
    if not valid:
        return False, f"Base quantity invalid: {error}"
    
    # Check notional value for base orders
    valid, error = filters.market_filter.validate(current_price, base_quantity)
    if not valid:
        return False, f"Base order notional invalid: {error}"
    
    # Check total orders don't exceed limit
    total_orders = num_levels * 2  # Buy and sell sides
    if total_orders > filters.max_orders:
        return False, f"Total orders {total_orders} exceeds maximum {filters.max_orders}"
    
    return True, None


# Example usage for testing
if __name__ == "__main__":
    import time
    
    # Create sample filters for BTCUSDT
    btc_filters = SymbolFilters(
        symbol="BTCUSDT",
        price_filter=PriceFilter(
            min_price=0.10,
            max_price=199999.80,
            tick_size=0.10
        ),
        lot_size_filter=LotSizeFilter(
            min_order_qty=0.001,
            max_order_qty=100.0,
            qty_step=0.001,
            post_only_max_order_qty=100.0,
            max_mkt_order_qty=50.0
        ),
        market_filter=MarketFilter(min_notional_value=5.0)
    )
    
    # Test order validation
    price = 50000.15  # Invalid - not aligned with tick size
    qty = 0.0005     # Invalid - below minimum
    
    valid, error = btc_filters.validate_order(price, qty)
    print(f"Order valid: {valid}, Error: {error}")
    
    # Round order to valid values
    rounded_price, rounded_qty = btc_filters.round_order(price, qty, 'buy')
    print(f"Rounded: Price={rounded_price}, Qty={rounded_qty}")
    
    # Validate rounded order
    valid, error = btc_filters.validate_order(rounded_price, rounded_qty)
    print(f"Rounded order valid: {valid}")
    
    # Test grid parameters
    valid, error = validate_grid_parameters(
        btc_filters,
        grid_spacing=0.002,  # 0.2%
        base_quantity=0.01,
        current_price=50000,
        num_levels=20
    )
    print(f"Grid parameters valid: {valid}, Error: {error}")