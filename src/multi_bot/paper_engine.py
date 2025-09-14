"""
Paper Trading Engine for Grid Trading Bot

This module provides a comprehensive paper trading simulation that mirrors
real trading behavior without executing actual trades. Perfect for testing
strategies and parameters risk-free.
"""

import time
import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import json
import random
import math

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status enum"""
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class OrderType(Enum):
    """Order type enum"""
    LIMIT = "limit"
    MARKET = "market"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


@dataclass
class PaperOrder:
    """Paper trading order representation"""
    order_id: str
    client_order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    position_side: str  # 'long' or 'short'
    order_type: OrderType
    quantity: float
    price: Optional[float]  # None for market orders
    stop_price: Optional[float]  # For stop orders
    filled_quantity: float = 0.0
    average_price: float = 0.0
    status: OrderStatus = OrderStatus.NEW
    reduce_only: bool = False
    time_in_force: str = "GTC"
    created_time: float = field(default_factory=time.time)
    updated_time: float = field(default_factory=time.time)
    
    @property
    def remaining_quantity(self) -> float:
        return self.quantity - self.filled_quantity
    
    @property
    def is_active(self) -> bool:
        return self.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]
    
    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API compatibility"""
        return {
            'orderId': self.order_id,
            'clientOrderId': self.client_order_id,
            'symbol': self.symbol,
            'side': self.side,
            'positionSide': self.position_side,
            'type': self.order_type.value,
            'origQty': str(self.quantity),
            'price': str(self.price) if self.price else "0",
            'executedQty': str(self.filled_quantity),
            'avgPrice': str(self.average_price),
            'status': self.status.value.upper(),
            'reduceOnly': self.reduce_only,
            'timeInForce': self.time_in_force,
            'time': int(self.created_time * 1000),
            'updateTime': int(self.updated_time * 1000)
        }


@dataclass
class PaperPosition:
    """Paper trading position representation"""
    symbol: str
    side: str  # 'long' or 'short'
    size: float = 0.0
    entry_price: float = 0.0
    mark_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin: float = 0.0
    leverage: int = 1
    updated_time: float = field(default_factory=time.time)
    
    def update_unrealized_pnl(self, current_price: float):
        """Update unrealized P&L based on current price"""
        if self.size == 0:
            self.unrealized_pnl = 0.0
            return
        
        self.mark_price = current_price
        
        if self.side == 'long':
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * abs(self.size)
        
        self.updated_time = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API compatibility"""
        return {
            'symbol': self.symbol,
            'positionSide': self.side.upper(),
            'positionAmt': str(self.size),
            'entryPrice': str(self.entry_price),
            'markPrice': str(self.mark_price),
            'unRealizedProfit': str(self.unrealized_pnl),
            'margin': str(self.margin),
            'leverage': str(self.leverage),
            'updateTime': int(self.updated_time * 1000)
        }


@dataclass  
class PaperBalance:
    """Paper trading balance representation"""
    asset: str
    total: float = 10000.0  # Start with $10k
    available: float = 10000.0
    locked: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API compatibility"""
        return {
            'asset': self.asset,
            'balance': str(self.total),
            'withdrawAvailable': str(self.available),
            'crossWalletBalance': str(self.total),
            'crossUnPnl': "0",
            'availableBalance': str(self.available),
            'maxWithdrawAmount': str(self.available),
            'marginAvailable': True
        }


class MarketDataSimulator:
    """Simulates realistic market data for paper trading"""
    
    def __init__(self, symbol: str, initial_price: float = 50000.0):
        self.symbol = symbol
        self.current_price = initial_price
        self.bid_price = initial_price * 0.9995
        self.ask_price = initial_price * 1.0005
        
        # Market simulation parameters
        self.volatility = 0.002  # 0.2% typical volatility
        self.trend_strength = 0.0  # No trend by default
        self.tick_size = 0.01 if 'BTC' in symbol else 0.001
        
        # Price history for realistic movements
        self.price_history = deque([initial_price], maxlen=1000)
        self.last_update = time.time()
    
    def update_price(self, external_price: Optional[float] = None) -> Tuple[float, float, float]:
        """
        Update simulated price
        
        Returns:
            (bid_price, ask_price, mark_price)
        """
        current_time = time.time()
        time_delta = current_time - self.last_update
        
        if external_price:
            # Use external price data if provided
            self.current_price = external_price
        else:
            # Simulate price movement using random walk with optional trend
            random_change = random.normalvariate(0, self.volatility * math.sqrt(time_delta))
            trend_change = self.trend_strength * time_delta
            
            price_change = (random_change + trend_change) * self.current_price
            self.current_price += price_change
        
        # Update bid/ask spread (typical 0.01% spread)
        spread = self.current_price * 0.0001
        self.bid_price = self.current_price - spread / 2
        self.ask_price = self.current_price + spread / 2
        
        # Round to tick size
        self.current_price = round(self.current_price / self.tick_size) * self.tick_size
        self.bid_price = round(self.bid_price / self.tick_size) * self.tick_size
        self.ask_price = round(self.ask_price / self.tick_size) * self.tick_size
        
        self.price_history.append(self.current_price)
        self.last_update = current_time
        
        return self.bid_price, self.ask_price, self.current_price
    
    def set_trend(self, trend_strength: float):
        """Set market trend (-1.0 to 1.0, where positive is uptrend)"""
        self.trend_strength = trend_strength
    
    def set_volatility(self, volatility: float):
        """Set market volatility (0.0 to 1.0)"""
        self.volatility = max(0.0001, min(1.0, volatility))
    
    def simulate_gap(self, gap_percent: float):
        """Simulate price gap (for testing)"""
        gap_amount = self.current_price * gap_percent
        self.current_price += gap_amount
        logger.info(f"Simulated {gap_percent:.2%} price gap to {self.current_price}")


class PaperTradingEngine:
    """
    Complete paper trading engine with realistic order execution,
    position management, and balance tracking
    """
    
    def __init__(self, initial_balance: float = 10000.0, base_asset: str = "USDT"):
        self.base_asset = base_asset
        self.initial_balance = initial_balance
        
        # Trading state
        self.orders: Dict[str, PaperOrder] = {}
        self.positions: Dict[str, Dict[str, PaperPosition]] = {}  # symbol -> {side: position}
        self.balances: Dict[str, PaperBalance] = {
            base_asset: PaperBalance(base_asset, initial_balance, initial_balance)
        }
        
        # Market simulators per symbol
        self.market_simulators: Dict[str, MarketDataSimulator] = {}
        
        # Execution settings
        self.slippage_bps = 5  # 5 basis points average slippage
        self.fill_probability = 0.95  # 95% chance orders fill at expected price
        self.partial_fill_probability = 0.1  # 10% chance of partial fills
        self.reject_probability = 0.001  # 0.1% chance of order rejection
        
        # Fee structure (Bybit-like)
        self.maker_fee_rate = 0.0002  # 0.02%
        self.taker_fee_rate = 0.0006  # 0.06%
        
        # Order ID counter
        self._order_counter = 1
        self._client_order_counter = 1
        
        # Execution engine
        self._execution_task = None
        self._running = False
        
        # Statistics
        self.total_trades = 0
        self.total_fees_paid = 0.0
        self.total_realized_pnl = 0.0
        self.session_start_time = time.time()
        
        logger.info(f"Paper trading engine initialized with {initial_balance} {base_asset}")
    
    def get_market_simulator(self, symbol: str) -> MarketDataSimulator:
        """Get or create market simulator for symbol"""
        if symbol not in self.market_simulators:
            # Set initial prices based on symbol
            initial_prices = {
                'BTCUSDT': 50000.0,
                'ETHUSDT': 3000.0,
                'BNBUSDT': 300.0,
                'SOLUSDT': 100.0,
                'ADAUSDT': 1.0
            }
            initial_price = initial_prices.get(symbol, 100.0)
            
            self.market_simulators[symbol] = MarketDataSimulator(symbol, initial_price)
            
            # Initialize positions for symbol
            self.positions[symbol] = {
                'long': PaperPosition(symbol, 'long'),
                'short': PaperPosition(symbol, 'short')
            }
        
        return self.market_simulators[symbol]
    
    def update_market_price(self, symbol: str, price: Optional[float] = None):
        """Update market price (externally or via simulation)"""
        simulator = self.get_market_simulator(symbol)
        bid, ask, mark = simulator.update_price(price)
        
        # Update position P&L
        if symbol in self.positions:
            for position in self.positions[symbol].values():
                position.update_unrealized_pnl(mark)
    
    async def place_order(self, 
                         symbol: str,
                         side: str,
                         position_side: str,
                         order_type: str,
                         quantity: float,
                         price: Optional[float] = None,
                         client_order_id: Optional[str] = None,
                         reduce_only: bool = False,
                         time_in_force: str = "GTC") -> Dict[str, Any]:
        """
        Place paper order with realistic validation and execution
        
        Returns:
            Order confirmation dict or raises exception
        """
        
        # Generate IDs
        order_id = str(self._order_counter)
        self._order_counter += 1
        
        if not client_order_id:
            client_order_id = f"paper_{self._client_order_counter}"
            self._client_order_counter += 1
        
        # Convert order type
        try:
            order_type_enum = OrderType(order_type.lower())
        except ValueError:
            raise ValueError(f"Unsupported order type: {order_type}")
        
        # Validate order
        await self._validate_order(symbol, side, quantity, price, reduce_only)
        
        # Check for immediate rejection (simulate exchange errors)
        if random.random() < self.reject_probability:
            raise Exception("Order rejected by exchange (simulated)")
        
        # Create order
        order = PaperOrder(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            position_side=position_side,
            order_type=order_type_enum,
            quantity=quantity,
            price=price,
            reduce_only=reduce_only,
            time_in_force=time_in_force
        )
        
        self.orders[order_id] = order
        
        logger.info(f"Paper order placed: {order_id} {side} {quantity} {symbol} @ {price}")
        
        # Start execution engine if not running
        if not self._running:
            await self.start_execution_engine()
        
        return order.to_dict()
    
    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Cancel paper order"""
        if order_id not in self.orders:
            raise Exception(f"Order not found: {order_id}")
        
        order = self.orders[order_id]
        
        if not order.is_active:
            raise Exception(f"Order {order_id} is not active")
        
        order.status = OrderStatus.CANCELED
        order.updated_time = time.time()
        
        logger.info(f"Paper order canceled: {order_id}")
        
        return order.to_dict()
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Cancel all active orders for symbol (or all symbols)"""
        canceled_orders = []
        
        for order in self.orders.values():
            if order.is_active and (symbol is None or order.symbol == symbol):
                order.status = OrderStatus.CANCELED
                order.updated_time = time.time()
                canceled_orders.append(order.to_dict())
        
        logger.info(f"Canceled {len(canceled_orders)} paper orders for {symbol or 'all symbols'}")
        
        return canceled_orders
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all open orders"""
        orders = []
        for order in self.orders.values():
            if order.is_active and (symbol is None or order.symbol == symbol):
                orders.append(order.to_dict())
        return orders
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all positions"""
        positions = []
        
        for sym, symbol_positions in self.positions.items():
            if symbol is None or sym == symbol:
                for position in symbol_positions.values():
                    if position.size != 0:  # Only return non-zero positions
                        positions.append(position.to_dict())
        
        return positions
    
    async def get_balance(self) -> List[Dict[str, Any]]:
        """Get account balance"""
        return [balance.to_dict() for balance in self.balances.values()]
    
    async def _validate_order(self, symbol: str, side: str, quantity: float, price: Optional[float], reduce_only: bool):
        """Validate order parameters"""
        # Check balance for non-reduce-only orders
        if not reduce_only:
            required_margin = quantity * (price or self.get_market_simulator(symbol).current_price)
            available = self.balances[self.base_asset].available
            
            if required_margin > available:
                raise Exception(f"Insufficient balance: required {required_margin}, available {available}")
        
        # Check position for reduce-only orders
        if reduce_only:
            position_side = 'long' if side == 'sell' else 'short'
            if symbol in self.positions:
                position = self.positions[symbol][position_side]
                if abs(position.size) < quantity:
                    raise Exception(f"Insufficient position size for reduce-only order")
    
    async def start_execution_engine(self):
        """Start the order execution engine"""
        if self._running:
            return
        
        self._running = True
        self._execution_task = asyncio.create_task(self._execution_loop())
        logger.info("Paper trading execution engine started")
    
    async def stop_execution_engine(self):
        """Stop the order execution engine"""
        self._running = False
        if self._execution_task:
            self._execution_task.cancel()
            try:
                await self._execution_task
            except asyncio.CancelledError:
                pass
        logger.info("Paper trading execution engine stopped")
    
    async def _execution_loop(self):
        """Main execution loop that checks for order fills"""
        while self._running:
            try:
                await self._process_orders()
                await asyncio.sleep(0.1)  # Check every 100ms
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in execution loop: {e}")
                await asyncio.sleep(1)
    
    async def _process_orders(self):
        """Process all active orders for potential fills"""
        active_orders = [order for order in self.orders.values() if order.is_active]
        
        for order in active_orders:
            try:
                await self._try_fill_order(order)
            except Exception as e:
                logger.error(f"Error processing order {order.order_id}: {e}")
    
    async def _try_fill_order(self, order: PaperOrder):
        """Try to fill an individual order"""
        simulator = self.get_market_simulator(order.symbol)
        bid, ask, mark = simulator.update_price()
        
        should_fill = False
        fill_price = None
        
        if order.order_type == OrderType.MARKET:
            # Market orders fill immediately
            should_fill = True
            fill_price = ask if order.side == 'buy' else bid
            
        elif order.order_type == OrderType.LIMIT:
            # Limit orders fill when price crosses
            if order.side == 'buy' and order.price >= ask:
                should_fill = True
                fill_price = min(order.price, ask)
            elif order.side == 'sell' and order.price <= bid:
                should_fill = True
                fill_price = max(order.price, bid)
        
        if should_fill and random.random() < self.fill_probability:
            # Determine fill quantity (sometimes partial)
            if random.random() < self.partial_fill_probability and order.order_type == OrderType.LIMIT:
                fill_qty = order.remaining_quantity * random.uniform(0.3, 0.9)
            else:
                fill_qty = order.remaining_quantity
            
            # Add realistic slippage
            slippage = random.normalvariate(0, self.slippage_bps / 10000)
            if order.side == 'buy':
                fill_price *= (1 + abs(slippage))
            else:
                fill_price *= (1 - abs(slippage))
            
            await self._execute_fill(order, fill_qty, fill_price)
    
    async def _execute_fill(self, order: PaperOrder, fill_qty: float, fill_price: float):
        """Execute order fill and update positions/balances"""
        
        # Calculate fees
        fee_rate = self.maker_fee_rate if order.order_type == OrderType.LIMIT else self.taker_fee_rate
        fee = fill_qty * fill_price * fee_rate
        
        # Update order
        order.filled_quantity += fill_qty
        order.average_price = ((order.average_price * (order.filled_quantity - fill_qty)) + 
                              (fill_price * fill_qty)) / order.filled_quantity
        order.updated_time = time.time()
        
        if order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        
        # Update position
        position_side = order.position_side.lower()
        position = self.positions[order.symbol][position_side]
        
        if order.reduce_only:
            # Reduce position
            if order.side == 'buy' and position.side == 'short':
                # Closing short position
                close_qty = min(fill_qty, abs(position.size))
                realized_pnl = (position.entry_price - fill_price) * close_qty
                position.size += close_qty
                position.realized_pnl += realized_pnl
                self.total_realized_pnl += realized_pnl
                
            elif order.side == 'sell' and position.side == 'long':
                # Closing long position
                close_qty = min(fill_qty, position.size)
                realized_pnl = (fill_price - position.entry_price) * close_qty
                position.size -= close_qty
                position.realized_pnl += realized_pnl
                self.total_realized_pnl += realized_pnl
                
        else:
            # Open or add to position
            old_size = position.size
            old_entry = position.entry_price
            
            if order.side == 'buy' and position_side == 'long':
                # Add to long position
                new_size = old_size + fill_qty
                position.entry_price = ((old_entry * old_size) + (fill_price * fill_qty)) / new_size
                position.size = new_size
                
            elif order.side == 'sell' and position_side == 'short':
                # Add to short position  
                new_size = old_size + fill_qty
                if old_size == 0:
                    position.entry_price = fill_price
                else:
                    position.entry_price = ((old_entry * old_size) + (fill_price * fill_qty)) / new_size
                position.size = -new_size  # Short positions are negative
        
        # Update balance
        self.balances[self.base_asset].total -= fee
        self.balances[self.base_asset].available -= fee
        self.total_fees_paid += fee
        self.total_trades += 1
        
        logger.info(f"Paper fill: {order.order_id} {fill_qty} @ {fill_price:.2f} (fee: {fee:.4f})")
    
    def get_trading_statistics(self) -> Dict[str, Any]:
        """Get comprehensive trading statistics"""
        total_unrealized_pnl = 0
        total_positions = 0
        
        for symbol_positions in self.positions.values():
            for position in symbol_positions.values():
                if position.size != 0:
                    total_unrealized_pnl += position.unrealized_pnl
                    total_positions += 1
        
        current_balance = self.balances[self.base_asset].total
        total_pnl = self.total_realized_pnl + total_unrealized_pnl
        session_duration = time.time() - self.session_start_time
        
        return {
            'session_duration_hours': session_duration / 3600,
            'initial_balance': self.initial_balance,
            'current_balance': current_balance,
            'total_realized_pnl': self.total_realized_pnl,
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_pnl': total_pnl,
            'total_fees_paid': self.total_fees_paid,
            'total_trades': self.total_trades,
            'active_positions': total_positions,
            'active_orders': len([o for o in self.orders.values() if o.is_active]),
            'return_percentage': (total_pnl / self.initial_balance) * 100,
            'net_balance': current_balance + total_unrealized_pnl
        }
    
    def export_trade_history(self) -> List[Dict[str, Any]]:
        """Export complete trade history for analysis"""
        trades = []
        
        for order in self.orders.values():
            if order.is_filled:
                trades.append({
                    'timestamp': order.updated_time,
                    'symbol': order.symbol,
                    'side': order.side,
                    'position_side': order.position_side,
                    'quantity': order.filled_quantity,
                    'price': order.average_price,
                    'order_type': order.order_type.value,
                    'reduce_only': order.reduce_only
                })
        
        return sorted(trades, key=lambda x: x['timestamp'])


# Example usage and testing
if __name__ == "__main__":
    async def test_paper_engine():
        # Initialize paper engine
        engine = PaperTradingEngine(initial_balance=10000.0)
        
        # Start execution engine
        await engine.start_execution_engine()
        
        # Test basic order placement
        symbol = "BTCUSDT"
        
        # Place some test orders
        buy_order = await engine.place_order(
            symbol=symbol,
            side='buy',
            position_side='long',
            order_type='limit',
            quantity=0.01,
            price=49000.0
        )
        print(f"Placed buy order: {buy_order['orderId']}")
        
        # Update market price to trigger fills
        for i in range(10):
            # Simulate price movement
            price = 49500 - (i * 100)  # Price moving down to trigger fill
            engine.update_market_price(symbol, price)
            await asyncio.sleep(0.1)
        
        # Check orders and positions
        open_orders = await engine.get_open_orders(symbol)
        positions = await engine.get_positions(symbol)
        
        print(f"Open orders: {len(open_orders)}")
        print(f"Positions: {len(positions)}")
        
        # Show statistics
        stats = engine.get_trading_statistics()
        print(f"Trading statistics: {json.dumps(stats, indent=2)}")
        
        await engine.stop_execution_engine()
    
    # Run test
    asyncio.run(test_paper_engine())