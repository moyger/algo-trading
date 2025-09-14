"""
State Management System for Grid Trading Bot

This module provides comprehensive state persistence and recovery
for production-ready grid trading operations, ensuring zero-loss
recovery from crashes, restarts, or network interruptions.
"""

import json
import os
import time
import logging
import threading
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import tempfile
from enum import Enum

logger = logging.getLogger(__name__)


class StateVersion(Enum):
    """State file format versions"""
    V1 = "1.0"
    CURRENT = V1


@dataclass
class OrderState:
    """Persistent order state information"""
    order_id: str
    client_order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    position_side: str  # 'long' or 'short' for hedge mode
    order_type: str  # 'limit', 'market', etc.
    price: float
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    status: str  # 'new', 'filled', 'canceled', etc.
    reduce_only: bool
    time_in_force: str
    created_time: float
    updated_time: float
    grid_level: Optional[int] = None  # Grid level for this order
    is_tp_order: bool = False  # Is take-profit order
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrderState':
        return cls(**data)
    
    @property
    def is_active(self) -> bool:
        """Check if order is still active"""
        return self.status in ['new', 'partially_filled']
    
    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled"""
        return self.status == 'filled'


@dataclass
class PositionState:
    """Persistent position state information"""
    symbol: str
    side: str  # 'long' or 'short'
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    margin: float
    leverage: int
    created_time: float
    updated_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PositionState':
        return cls(**data)


@dataclass
class GridState:
    """Persistent grid configuration state"""
    symbol: str
    base_price: float
    grid_spacing: float
    grid_levels: int
    base_quantity: float
    leverage: int
    anchor_price: Optional[float]
    anchor_type: Optional[str]
    anchor_timestamp: Optional[float]
    regime: Optional[str]
    regime_confidence: Optional[float]
    volatility_multiplier: float
    last_update: float
    active_levels: List[int]  # Currently active grid levels
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GridState':
        return cls(**data)


@dataclass
class LockdownState:
    """Lockdown mode state (existing from binance_multi_bot)"""
    long: Dict[str, Any]
    short: Dict[str, Any]
    updated_at: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LockdownState':
        return cls(**data)


@dataclass
class TradingState:
    """Complete trading state for a symbol"""
    version: str
    symbol: str
    exchange: str
    trading_mode: str  # 'production', 'testnet', 'paper'
    timestamp: float
    checksum: str
    
    # Core state components
    orders: Dict[str, OrderState]
    positions: Dict[str, PositionState]  # Key: side ('long'/'short')
    grid: GridState
    lockdown: LockdownState
    
    # Operational metrics
    emergency_triggers_today: int
    last_emergency_time: float
    day_fuse_active: bool
    grid_pause_until: float
    last_ticker_time: float
    last_sync_sequence: Optional[int]  # For WebSocket sequence tracking
    
    # Performance tracking
    total_trades: int
    total_profit: float
    total_fees: float
    session_start_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        
        # Convert nested dataclasses
        data['orders'] = {k: v.to_dict() if hasattr(v, 'to_dict') else v 
                         for k, v in self.orders.items()}
        data['positions'] = {k: v.to_dict() if hasattr(v, 'to_dict') else v 
                            for k, v in self.positions.items()}
        data['grid'] = self.grid.to_dict() if self.grid else None
        data['lockdown'] = self.lockdown.to_dict() if self.lockdown else None
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradingState':
        """Create from dictionary"""
        # Convert nested dictionaries back to dataclasses
        orders = {k: OrderState.from_dict(v) for k, v in data.get('orders', {}).items()}
        positions = {k: PositionState.from_dict(v) for k, v in data.get('positions', {}).items()}
        grid = GridState.from_dict(data['grid']) if data.get('grid') else None
        lockdown = LockdownState.from_dict(data['lockdown']) if data.get('lockdown') else None
        
        return cls(
            version=data['version'],
            symbol=data['symbol'],
            exchange=data['exchange'],
            trading_mode=data['trading_mode'],
            timestamp=data['timestamp'],
            checksum=data['checksum'],
            orders=orders,
            positions=positions,
            grid=grid,
            lockdown=lockdown,
            emergency_triggers_today=data.get('emergency_triggers_today', 0),
            last_emergency_time=data.get('last_emergency_time', 0),
            day_fuse_active=data.get('day_fuse_active', False),
            grid_pause_until=data.get('grid_pause_until', 0),
            last_ticker_time=data.get('last_ticker_time', 0),
            last_sync_sequence=data.get('last_sync_sequence'),
            total_trades=data.get('total_trades', 0),
            total_profit=data.get('total_profit', 0.0),
            total_fees=data.get('total_fees', 0.0),
            session_start_time=data.get('session_start_time', time.time())
        )
    
    def calculate_checksum(self) -> str:
        """Calculate state checksum for integrity verification"""
        # Create checksum from critical state data
        critical_data = {
            'orders': len(self.orders),
            'positions': {k: v.size for k, v in self.positions.items()},
            'grid_spacing': self.grid.grid_spacing if self.grid else 0,
            'timestamp': self.timestamp
        }
        
        data_str = json.dumps(critical_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]
    
    def verify_checksum(self) -> bool:
        """Verify state integrity"""
        return self.calculate_checksum() == self.checksum
    
    def update_checksum(self):
        """Update checksum after state changes"""
        self.checksum = self.calculate_checksum()


class StateManager:
    """
    Production-ready state manager with atomic operations,
    integrity checks, and recovery mechanisms
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.getenv("STATE_DIR", "./state"))
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread safety
        self._lock = threading.RLock()
        
        # In-memory state cache
        self._state_cache: Dict[str, TradingState] = {}
        
        # Backup configuration
        self.backup_count = 5  # Keep 5 backup files
        self.auto_backup_interval = 300  # Backup every 5 minutes
        self._last_backup = {}
        
        logger.info(f"StateManager initialized with directory: {self.base_dir}")
    
    def _get_state_path(self, symbol: str) -> Path:
        """Get state file path for symbol"""
        safe_symbol = symbol.replace("/", "_").replace(":", "_")
        return self.base_dir / f"trading_state_{safe_symbol}.json"
    
    def _get_backup_path(self, symbol: str, backup_num: int) -> Path:
        """Get backup file path"""
        safe_symbol = symbol.replace("/", "_").replace(":", "_")
        return self.base_dir / f"trading_state_{safe_symbol}.backup.{backup_num}"
    
    def _atomic_write(self, path: Path, data: str):
        """Write data atomically to prevent corruption"""
        # Write to temporary file first
        temp_path = path.with_suffix(path.suffix + ".tmp")
        
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            
            # Atomic move to final location
            if os.name == 'nt':  # Windows
                if path.exists():
                    path.unlink()
            os.replace(temp_path, path)
            
        except Exception as e:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise e
    
    def _create_backup(self, symbol: str, state: TradingState):
        """Create backup of current state"""
        try:
            # Rotate existing backups
            for i in range(self.backup_count - 1, 0, -1):
                old_backup = self._get_backup_path(symbol, i)
                new_backup = self._get_backup_path(symbol, i + 1)
                
                if old_backup.exists():
                    if new_backup.exists():
                        new_backup.unlink()
                    old_backup.rename(new_backup)
            
            # Create new backup
            backup_path = self._get_backup_path(symbol, 1)
            data = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
            self._atomic_write(backup_path, data)
            
            self._last_backup[symbol] = time.time()
            
        except Exception as e:
            logger.warning(f"Failed to create backup for {symbol}: {e}")
    
    def save_state(self, state: TradingState, create_backup: bool = True):
        """
        Save trading state with atomic write and optional backup
        
        Args:
            state: Trading state to save
            create_backup: Whether to create backup copy
        """
        with self._lock:
            try:
                # Update metadata
                state.timestamp = time.time()
                state.update_checksum()
                
                # Convert to JSON
                data = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
                
                # Write atomically
                state_path = self._get_state_path(state.symbol)
                self._atomic_write(state_path, data)
                
                # Update cache
                self._state_cache[state.symbol] = state
                
                # Create backup if needed
                if create_backup:
                    should_backup = (
                        symbol not in self._last_backup or
                        time.time() - self._last_backup.get(state.symbol, 0) > self.auto_backup_interval
                    )
                    if should_backup:
                        self._create_backup(state.symbol, state)
                
                logger.debug(f"State saved for {state.symbol} with checksum {state.checksum}")
                
            except Exception as e:
                logger.error(f"Failed to save state for {state.symbol}: {e}")
                raise
    
    def load_state(self, symbol: str, exchange: str = "bybit") -> Optional[TradingState]:
        """
        Load trading state with integrity verification
        
        Args:
            symbol: Trading symbol
            exchange: Exchange name
            
        Returns:
            TradingState or None if not found/invalid
        """
        with self._lock:
            # Check cache first
            if symbol in self._state_cache:
                cached_state = self._state_cache[symbol]
                if cached_state.verify_checksum():
                    return cached_state
                else:
                    logger.warning(f"Cached state for {symbol} failed checksum")
                    del self._state_cache[symbol]
            
            state_path = self._get_state_path(symbol)
            
            if not state_path.exists():
                logger.info(f"No state file found for {symbol}")
                return None
            
            try:
                # Try to load main state file
                with open(state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                state = TradingState.from_dict(data)
                
                # Verify integrity
                if not state.verify_checksum():
                    logger.error(f"State checksum verification failed for {symbol}")
                    return self._recover_from_backup(symbol, exchange)
                
                # Cache and return
                self._state_cache[symbol] = state
                logger.info(f"State loaded for {symbol} from {state_path}")
                return state
                
            except Exception as e:
                logger.error(f"Failed to load state for {symbol}: {e}")
                return self._recover_from_backup(symbol, exchange)
    
    def _recover_from_backup(self, symbol: str, exchange: str) -> Optional[TradingState]:
        """Attempt recovery from backup files"""
        logger.info(f"Attempting recovery from backups for {symbol}")
        
        for i in range(1, self.backup_count + 1):
            backup_path = self._get_backup_path(symbol, i)
            
            if not backup_path.exists():
                continue
            
            try:
                with open(backup_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                state = TradingState.from_dict(data)
                
                if state.verify_checksum():
                    logger.info(f"Recovered state for {symbol} from backup {i}")
                    
                    # Save recovered state as current
                    self.save_state(state, create_backup=False)
                    return state
                    
            except Exception as e:
                logger.warning(f"Failed to load backup {i} for {symbol}: {e}")
                continue
        
        logger.error(f"All recovery attempts failed for {symbol}")
        return None
    
    def create_initial_state(self, 
                           symbol: str,
                           exchange: str = "bybit",
                           trading_mode: str = "production") -> TradingState:
        """Create initial trading state for a new symbol"""
        
        current_time = time.time()
        
        # Create initial grid state
        initial_grid = GridState(
            symbol=symbol,
            base_price=0.0,  # Will be set when first price is received
            grid_spacing=0.002,  # Default 0.2%
            grid_levels=20,
            base_quantity=0.01,
            leverage=20,
            anchor_price=None,
            anchor_type=None,
            anchor_timestamp=None,
            regime=None,
            regime_confidence=None,
            volatility_multiplier=1.0,
            last_update=current_time,
            active_levels=[]
        )
        
        # Create initial lockdown state
        initial_lockdown = LockdownState(
            long={'active': False, 'tp_price': None, 'lockdown_price': None, 'r': None, 'exited_at': None},
            short={'active': False, 'tp_price': None, 'lockdown_price': None, 'r': None, 'exited_at': None},
            updated_at=current_time
        )
        
        state = TradingState(
            version=StateVersion.CURRENT.value,
            symbol=symbol,
            exchange=exchange,
            trading_mode=trading_mode,
            timestamp=current_time,
            checksum="",
            orders={},
            positions={},
            grid=initial_grid,
            lockdown=initial_lockdown,
            emergency_triggers_today=0,
            last_emergency_time=0,
            day_fuse_active=False,
            grid_pause_until=0,
            last_ticker_time=0,
            last_sync_sequence=None,
            total_trades=0,
            total_profit=0.0,
            total_fees=0.0,
            session_start_time=current_time
        )
        
        state.update_checksum()
        
        logger.info(f"Created initial state for {symbol}")
        return state
    
    def update_orders(self, symbol: str, orders: List[OrderState]):
        """Update orders in state"""
        state = self.load_state(symbol)
        if state is None:
            logger.error(f"Cannot update orders: no state found for {symbol}")
            return
        
        # Update orders
        for order in orders:
            state.orders[order.order_id] = order
        
        # Clean up filled/canceled orders older than 24 hours
        current_time = time.time()
        orders_to_remove = []
        
        for order_id, order in state.orders.items():
            if not order.is_active and (current_time - order.updated_time) > 86400:
                orders_to_remove.append(order_id)
        
        for order_id in orders_to_remove:
            del state.orders[order_id]
        
        self.save_state(state)
    
    def update_positions(self, symbol: str, positions: List[PositionState]):
        """Update positions in state"""
        state = self.load_state(symbol)
        if state is None:
            logger.error(f"Cannot update positions: no state found for {symbol}")
            return
        
        # Update positions
        for position in positions:
            state.positions[position.side] = position
        
        self.save_state(state)
    
    def update_grid(self, symbol: str, grid_state: GridState):
        """Update grid configuration in state"""
        state = self.load_state(symbol)
        if state is None:
            logger.error(f"Cannot update grid: no state found for {symbol}")
            return
        
        state.grid = grid_state
        self.save_state(state)
    
    def record_trade(self, symbol: str, profit: float, fees: float):
        """Record a completed trade"""
        state = self.load_state(symbol)
        if state is None:
            return
        
        state.total_trades += 1
        state.total_profit += profit
        state.total_fees += fees
        
        self.save_state(state)
    
    def get_recovery_info(self, symbol: str) -> Dict[str, Any]:
        """Get information needed for bootstrap recovery"""
        state = self.load_state(symbol)
        if state is None:
            return {}
        
        active_orders = [order for order in state.orders.values() if order.is_active]
        active_positions = [pos for pos in state.positions.values() if pos.size != 0]
        
        return {
            'symbol': symbol,
            'last_sync_time': state.last_ticker_time,
            'active_orders': [order.to_dict() for order in active_orders],
            'active_positions': [pos.to_dict() for pos in active_positions],
            'grid_config': state.grid.to_dict() if state.grid else None,
            'lockdown_active': (
                state.lockdown.long.get('active', False) or 
                state.lockdown.short.get('active', False)
            ),
            'emergency_state': {
                'triggers_today': state.emergency_triggers_today,
                'day_fuse_active': state.day_fuse_active,
                'pause_until': state.grid_pause_until
            }
        }
    
    def cleanup_old_states(self, days_old: int = 7):
        """Clean up state files older than specified days"""
        cutoff_time = time.time() - (days_old * 86400)
        
        for state_file in self.base_dir.glob("trading_state_*.json"):
            try:
                if state_file.stat().st_mtime < cutoff_time:
                    # Also clean up associated backups
                    symbol = state_file.stem.replace("trading_state_", "")
                    for i in range(1, self.backup_count + 1):
                        backup_path = self._get_backup_path(symbol, i)
                        if backup_path.exists():
                            backup_path.unlink()
                    
                    state_file.unlink()
                    logger.info(f"Cleaned up old state file: {state_file}")
                    
            except Exception as e:
                logger.warning(f"Failed to clean up {state_file}: {e}")


# Usage example and testing
if __name__ == "__main__":
    import sys
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Test state manager
    manager = StateManager("./test_state")
    
    # Create test state
    state = manager.create_initial_state("BTCUSDT", "bybit", "testnet")
    
    # Add some test data
    test_order = OrderState(
        order_id="12345",
        client_order_id="test_order_1",
        symbol="BTCUSDT",
        side="buy",
        position_side="long",
        order_type="limit",
        price=50000.0,
        quantity=0.01,
        filled_quantity=0.0,
        remaining_quantity=0.01,
        status="new",
        reduce_only=False,
        time_in_force="GTC",
        created_time=time.time(),
        updated_time=time.time(),
        grid_level=1
    )
    
    state.orders[test_order.order_id] = test_order
    
    # Save state
    manager.save_state(state)
    
    # Load state back
    loaded_state = manager.load_state("BTCUSDT")
    
    if loaded_state:
        print(f"Successfully loaded state for {loaded_state.symbol}")
        print(f"Orders: {len(loaded_state.orders)}")
        print(f"Checksum verified: {loaded_state.verify_checksum()}")
        
        # Test recovery info
        recovery_info = manager.get_recovery_info("BTCUSDT")
        print(f"Recovery info: {len(recovery_info['active_orders'])} active orders")
    else:
        print("Failed to load state")
    
    print("State manager test completed")