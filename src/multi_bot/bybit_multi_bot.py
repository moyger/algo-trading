import asyncio
import websockets
import json
import logging
import hmac
import hashlib
import time
import ccxt
import math
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
import os
from dotenv import load_dotenv
import aiohttp
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import deque
from dynamic_grid import DynamicGridCalculator

# Load environment variables
load_dotenv()

# Telegram notification configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLE_NOTIFICATIONS = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"
NOTIFICATION_INTERVAL = int(os.getenv("NOTIFICATION_INTERVAL", "3600"))

# Bybit-specific configuration
BYBIT_WEBSOCKET_PUBLIC = "wss://stream.bybit.com/v5/public/linear"
BYBIT_WEBSOCKET_PRIVATE = "wss://stream.bybit.com/v5/private"
BYBIT_TESTNET_REST = "https://api-testnet.bybit.com"
BYBIT_TESTNET_WS_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/linear"
BYBIT_TESTNET_WS_PRIVATE = "wss://stream-testnet.bybit.com/v5/private"

# Trading mode configuration
TRADING_MODE = os.getenv("TRADING_MODE", "production")  # production|testnet|paper

# Fixed configuration
ORDER_COOLDOWN_TIME = 60
SYNC_TIME = 3
ORDER_FIRST_TIME = 1
MAX_ORDERS_PER_SYMBOL = 500  # Bybit limit
MAX_CONDITIONAL_ORDERS = 10   # Bybit limit

# Use optimized logging configuration
try:
    from logging_config import setup_binance_multi_bot_logging, ThresholdStateLogger
    logger = setup_binance_multi_bot_logging()
    threshold_logger = ThresholdStateLogger(logger)
except ImportError:
    # Fallback to default logging
    os.makedirs("log", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("log/bybit_multi_bot.log")
        ]
    )
    logger = logging.getLogger()
    threshold_logger = None


@dataclass
class InstrumentInfo:
    """Bybit instrument precision and filter information"""
    symbol: str
    tick_size: float
    qty_step: float
    min_order_qty: float
    max_order_qty: float
    min_notional_value: float
    max_leverage: int
    price_precision: int
    qty_precision: int
    
    def round_price(self, price: float, round_type=ROUND_HALF_UP) -> float:
        """Round price to tick size"""
        return float(Decimal(str(price)).quantize(
            Decimal(str(self.tick_size)), 
            rounding=round_type
        ))
    
    def round_qty(self, qty: float, round_type=ROUND_DOWN) -> float:
        """Round quantity to qty step"""
        return float(Decimal(str(qty)).quantize(
            Decimal(str(self.qty_step)), 
            rounding=round_type
        ))
    
    def validate_order(self, price: float, qty: float) -> Tuple[bool, Optional[str]]:
        """Validate order parameters against filters"""
        # Check quantity limits
        if qty < self.min_order_qty:
            return False, f"Quantity {qty} below minimum {self.min_order_qty}"
        if qty > self.max_order_qty:
            return False, f"Quantity {qty} above maximum {self.max_order_qty}"
        
        # Check notional value
        notional = price * qty
        if notional < self.min_notional_value:
            return False, f"Notional value {notional} below minimum {self.min_notional_value}"
        
        # Check precision
        if price % self.tick_size != 0:
            return False, f"Price {price} not aligned with tick size {self.tick_size}"
        if qty % self.qty_step != 0:
            return False, f"Quantity {qty} not aligned with qty step {self.qty_step}"
        
        return True, None


class CustomBybit(ccxt.bybit):
    """Custom Bybit exchange class with enhanced features"""
    
    def __init__(self, config=None):
        super().__init__(config)
        # Set testnet endpoints if in testnet mode
        if TRADING_MODE == "testnet":
            self.urls['api']['public'] = BYBIT_TESTNET_REST
            self.urls['api']['private'] = BYBIT_TESTNET_REST
    
    def fetch(self, url, method='GET', headers=None, body=None):
        if headers is None:
            headers = {}
        return super().fetch(url, method, headers, body)


class BybitGridBot:
    """
    Bybit Grid Trading Bot with production-ready features
    
    Features:
    - Bybit API v5 integration
    - Precision filter validation
    - State persistence and recovery
    - Dynamic grid with regime filters and anchor algorithm
    - Emergency position management
    - WebSocket order placement support
    """
    
    # State persistence configuration
    _state_lock = None
    
    def __init__(self, symbol: str, api_key: str, api_secret: str, config: Dict[str, Any]):
        """
        Initialize BybitGridBot
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            api_key: Bybit API key
            api_secret: Bybit API secret
            config: Configuration dictionary
        """
        self.symbol = symbol
        self.api_key = api_key
        self.api_secret = api_secret
        self.config = config
        
        # Extract configuration parameters
        self.grid_spacing = config.get('grid_spacing', 0.001)
        self.initial_quantity = config.get('initial_quantity', 3)
        self.leverage = config.get('leverage', 20)
        self.contract_type = config.get('contract_type', 'USDT')
        
        # Calculate thresholds
        self.position_threshold_factor = float(config.get('position_threshold_factor', 10))
        self.position_limit_factor = float(config.get('position_limit_factor', 5))
        self.position_threshold = self.position_threshold_factor * self.initial_quantity / self.grid_spacing * 2 / 100
        self.position_limit = self.position_limit_factor * self.initial_quantity / self.grid_spacing * 2 / 100
        
        # Initialize exchange
        self.exchange = self._init_exchange()
        self.ccxt_symbol = f"{symbol.replace('USDT', '').replace('USDC', '')}/{self.contract_type}:{self.contract_type}"
        
        # Instrument information (will be fetched on init)
        self.instrument_info: Optional[InstrumentInfo] = None
        
        # Initialize state variables
        self.long_initial_quantity = 0
        self.short_initial_quantity = 0
        self.long_position = 0
        self.short_position = 0
        self.last_long_order_time = 0
        self.last_short_order_time = 0
        self.buy_long_orders = 0.0
        self.sell_long_orders = 0.0
        self.sell_short_orders = 0.0
        self.buy_short_orders = 0.0
        self.last_position_update_time = 0
        self.last_orders_update_time = 0
        self.last_ticker_update_time = 0
        self.latest_price = 0
        self.best_bid_price = None
        self.best_ask_price = None
        self.balance = {}
        self.mid_price_long = 0
        self.lower_price_long = 0
        self.upper_price_long = 0
        self.mid_price_short = 0
        self.lower_price_short = 0
        self.upper_price_short = 0
        
        # WebSocket connection state
        self.ws_public = None
        self.ws_private = None
        self.listen_key = None
        
        # Rate limiting
        self.api_call_timestamps = deque(maxlen=1000)
        self.rate_limit_weight = 0
        self.last_rate_limit_reset = time.time()
        
        # Emergency position management
        self.emg_enter_ratio = float(config.get('emg_enter_ratio', 0.80))
        self.emg_exit_ratio = float(config.get('emg_exit_ratio', 0.75))
        self.emg_cooldown_s = int(config.get('emg_cooldown_s', 60))
        self.grid_pause_after_emg_s = int(config.get('grid_pause_after_emg_s', 90))
        self.emg_batches = int(config.get('emg_batches', 2))
        self.emg_batch_sleep_ms = int(config.get('emg_batch_sleep_ms', 300))
        self.emg_slip_cap_bp = int(config.get('emg_slip_cap_bp', 15))
        self.emg_daily_fuse_count = int(config.get('emg_daily_fuse_count', 3))
        
        self._emg_last_ts = 0.0
        self._emg_in_progress = False
        self._emg_trigger_count_today = 0
        self._grid_pause_until_ts = 0.0
        self._day_fuse_on = False
        self._emg_day = time.strftime('%Y-%m-%d')
        
        # Volume tracking
        from collections import deque
        self._vol_prices = deque(maxlen=60)
        
        # Telegram notification state
        self.last_summary_time = 0
        self.startup_notified = False
        self.last_balance = None
        
        # Emergency notification tracking
        self.long_threshold_alerted = False
        self.short_threshold_alerted = False
        self.risk_reduction_alerted = False
        
        # Double profit/loss notification tracking
        self.long_double_profit_alerted = False
        self.short_double_profit_alerted = False
        
        # Async lock (delayed creation)
        self.lock = None
        
        # Running state
        self.running = False
        
        # Lockdown mode state
        self.lockdown_mode = {
            'long': {'active': False, 'tp_price': None, 'lockdown_price': None, 'r': None, 'exited_at': None},
            'short': {'active': False, 'tp_price': None, 'lockdown_price': None, 'r': None, 'exited_at': None}
        }
        
        # Initialize dynamic grid calculator (with regime filters and anchor system)
        dynamic_config = {
            'atr_period': config.get('atr_period', 14),
            'bollinger_period': config.get('bollinger_period', 20),
            'bollinger_std': config.get('bollinger_std', 2.0),
            'min_grid_levels': config.get('min_grid_levels', 10),
            'max_grid_levels': config.get('max_grid_levels', 30),
            'volatility_multiplier': config.get('volatility_multiplier', 1.5),
            # Regime filter configuration
            'regime_filter_enabled': config.get('regime_filter_enabled', True),
            'ema_fast_period': config.get('ema_fast_period', 12),
            'ema_slow_period': config.get('ema_slow_period', 26),
            'rsi_period': config.get('rsi_period', 14),
            'adx_period': config.get('adx_period', 14),
            'volume_period': config.get('volume_period', 20),
            'regime_update_interval': config.get('regime_update_interval', 300),
            # DGT Anchor system configuration
            'anchor_enabled': config.get('anchor_enabled', True),
            'anchor_lookback_hours': config.get('anchor_lookback_hours', 24),
            'anchor_performance_threshold': config.get('anchor_performance_threshold', 0.02),
            'anchor_reset_cooldown': config.get('anchor_reset_cooldown', 3600),
            'anchor_volatility_threshold': config.get('anchor_volatility_threshold', 0.05)
        }
        
        self.dynamic_grid = DynamicGridCalculator(
            symbol=symbol,
            base_grid_spacing=self.grid_spacing,
            config=dynamic_config
        )
        
        # Dynamic grid state
        self.dynamic_grid_enabled = config.get('dynamic_grid_enabled', True)
        self.last_grid_adjustment_time = 0
        self.grid_adjustment_interval = config.get('grid_adjustment_interval', 3600)
        self.price_data_buffer = []
        self.last_kline_update_time = 0
        
        # DGT Anchor system state
        self.anchor_enabled = config.get('anchor_enabled', True)
        self.last_anchor_notification_time = 0
        
        # Order tracking for recovery
        self.open_orders = {}  # order_id -> order_info
        self.grid_levels = []  # Current grid levels
        
    def _init_exchange(self):
        """Initialize Bybit exchange API"""
        exchange = CustomBybit({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "linear",  # USDT perpetual
                "recvWindow": 5000,
                "adjustForTimeDifference": True,
            }
        })
        
        # Load markets
        exchange.load_markets(reload=True)
        
        # Set sandbox mode for testnet
        if TRADING_MODE == "testnet":
            exchange.set_sandbox_mode(True)
            logger.info("Bybit exchange initialized in TESTNET mode")
        elif TRADING_MODE == "paper":
            logger.info("Bybit exchange initialized in PAPER TRADING mode")
        else:
            logger.info("Bybit exchange initialized in PRODUCTION mode")
            
        return exchange
    
    async def initialize(self):
        """Initialize bot components and fetch instrument info"""
        try:
            # Fetch and cache instrument information
            await self._fetch_instrument_info()
            
            # Check and enable hedge mode
            await self._check_and_enable_hedge_mode()
            
            # Set leverage
            await self._set_leverage()
            
            # Restore state from persistence
            await self._restore_state()
            
            # Bootstrap positions and orders
            await self._bootstrap_from_exchange()
            
            # Send startup notification
            if ENABLE_NOTIFICATIONS:
                await self._send_startup_notification()
                
            logger.info(f"BybitGridBot initialized for {self.symbol}")
            
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise
    
    async def _fetch_instrument_info(self):
        """Fetch and cache instrument precision and filter information"""
        try:
            # Use ccxt to fetch market info
            market = self.exchange.market(self.ccxt_symbol)
            
            # Extract precision information
            price_precision = market['precision']['price']
            qty_precision = market['precision']['amount']
            
            # Calculate tick size and qty step
            tick_size = 10 ** (-price_precision) if isinstance(price_precision, int) else price_precision
            qty_step = 10 ** (-qty_precision) if isinstance(qty_precision, int) else qty_precision
            
            # Extract limits
            self.instrument_info = InstrumentInfo(
                symbol=self.symbol,
                tick_size=tick_size,
                qty_step=qty_step,
                min_order_qty=market['limits']['amount']['min'],
                max_order_qty=market['limits']['amount']['max'],
                min_notional_value=market['limits']['cost']['min'] or 5.0,  # Default $5 for Bybit
                max_leverage=market['limits']['leverage']['max'] or 200,
                price_precision=price_precision if isinstance(price_precision, int) else int(abs(math.log10(price_precision))),
                qty_precision=qty_precision if isinstance(qty_precision, int) else int(abs(math.log10(qty_precision)))
            )
            
            logger.info(f"Instrument info loaded for {self.symbol}: "
                       f"tick_size={tick_size}, qty_step={qty_step}, "
                       f"min_qty={self.instrument_info.min_order_qty}, "
                       f"min_notional={self.instrument_info.min_notional_value}")
                       
        except Exception as e:
            logger.error(f"Failed to fetch instrument info: {e}")
            raise
    
    async def _check_and_enable_hedge_mode(self):
        """Check and enable hedge mode for bidirectional positions"""
        try:
            # Check current position mode
            response = await self._api_call('GET', '/v5/account/info')
            
            # For Bybit, hedge mode is controlled per symbol
            # We need to check if the symbol is in hedge mode
            position_mode = response.get('result', {}).get('unifiedMarginStatus', 0)
            
            # Bybit uses unified margin account by default which supports hedge mode
            logger.info(f"Position mode status: {position_mode}")
            
        except Exception as e:
            logger.warning(f"Failed to check position mode: {e}")
    
    async def _set_leverage(self):
        """Set leverage for the trading symbol"""
        try:
            # Ensure leverage doesn't exceed maximum
            leverage = min(self.leverage, self.instrument_info.max_leverage)
            
            # Set leverage via ccxt
            result = self.exchange.set_leverage(leverage, self.ccxt_symbol)
            
            logger.info(f"Leverage set to {leverage}x for {self.symbol}")
            
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            raise
    
    async def _api_call(self, method: str, endpoint: str, params: Dict = None):
        """
        Make API call with rate limiting and error handling
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint
            params: Request parameters
        """
        # Rate limiting check
        await self._check_rate_limit()
        
        try:
            # Use ccxt's unified API methods when possible
            if endpoint == '/v5/order/create':
                # Order placement - use ccxt
                return await self._place_order_ccxt(params)
            elif endpoint == '/v5/order/cancel':
                # Order cancellation - use ccxt
                return await self._cancel_order_ccxt(params)
            else:
                # Direct API call for other endpoints
                return await self._direct_api_call(method, endpoint, params)
                
        except ccxt.RateLimitExceeded as e:
            logger.warning(f"Rate limit exceeded: {e}")
            await self._handle_rate_limit()
            raise
        except ccxt.NetworkError as e:
            logger.error(f"Network error: {e}")
            raise
        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise
    
    async def _check_rate_limit(self):
        """Check and manage rate limits"""
        current_time = time.time()
        
        # Reset counter every minute
        if current_time - self.last_rate_limit_reset > 60:
            self.rate_limit_weight = 0
            self.last_rate_limit_reset = current_time
            self.api_call_timestamps.clear()
        
        # Check if we're approaching rate limit
        if self.rate_limit_weight > 100:  # Bybit's typical limit
            wait_time = 60 - (current_time - self.last_rate_limit_reset)
            if wait_time > 0:
                logger.warning(f"Approaching rate limit, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self.rate_limit_weight = 0
                self.last_rate_limit_reset = time.time()
    
    async def _handle_rate_limit(self):
        """Handle rate limit with exponential backoff"""
        base_wait = 5
        max_wait = 60
        
        # Calculate wait time with exponential backoff
        attempts = len([t for t in self.api_call_timestamps if time.time() - t < 60])
        wait_time = min(base_wait * (2 ** min(attempts, 5)), max_wait)
        
        # Add jitter
        import random
        wait_time += random.uniform(0, 1)
        
        logger.info(f"Rate limited, waiting {wait_time:.1f}s")
        await asyncio.sleep(wait_time)
    
    # ... Continue with more methods in next message due to length
    
    async def run(self):
        """Main bot execution loop"""
        self.running = True
        
        try:
            # Initialize bot components
            await self.initialize()
            
            # Start WebSocket connections
            await self._connect_websockets()
            
            # Main trading loop
            while self.running:
                try:
                    await self._grid_loop()
                    await asyncio.sleep(SYNC_TIME)
                    
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    await asyncio.sleep(5)
                    
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources on shutdown"""
        self.running = False
        
        # Close WebSocket connections
        if self.ws_public:
            await self.ws_public.close()
        if self.ws_private:
            await self.ws_private.close()
            
        # Persist final state
        await self._persist_state()
        
        logger.info("Bot cleanup completed")