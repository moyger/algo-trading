"""
Observability Infrastructure for Grid Trading Bot

This module provides comprehensive monitoring, metrics, and structured logging
for production-ready grid trading operations with Prometheus integration.
"""

import json
import time
import logging
import asyncio
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
from datetime import datetime, timezone
import traceback
import psutil
import os
from pathlib import Path
from enum import Enum

try:
    from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server, CollectorRegistry
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class LogLevel(Enum):
    """Structured log levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(Enum):
    """Trading event types for structured logging"""
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELED = "order_canceled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    EMERGENCY_TRIGGERED = "emergency_triggered"
    GRID_ADJUSTED = "grid_adjusted"
    REGIME_CHANGED = "regime_changed"
    ANCHOR_RESET = "anchor_reset"
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"
    API_ERROR = "api_error"
    STATE_SAVED = "state_saved"
    STATE_LOADED = "state_loaded"
    BALANCE_UPDATED = "balance_updated"


@dataclass
class StructuredLogEntry:
    """Structured log entry format"""
    timestamp: float
    level: str
    event_type: str
    symbol: Optional[str]
    component: str
    message: str
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        entry_dict = asdict(self)
        # Convert timestamp to ISO format
        entry_dict['timestamp_iso'] = datetime.fromtimestamp(
            self.timestamp, timezone.utc
        ).isoformat()
        return json.dumps(entry_dict, default=str)


class StructuredLogger:
    """Production-ready structured logger with JSON output"""
    
    def __init__(self, 
                 name: str,
                 log_file: Optional[str] = None,
                 session_id: Optional[str] = None):
        self.name = name
        self.session_id = session_id or f"session_{int(time.time())}"
        
        # Setup standard logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Create formatters
        json_formatter = logging.Formatter('%(message)s')
        
        # Console handler for development
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(console_handler)
        
        # File handler for production (JSON format)
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(json_formatter)
            self.logger.addHandler(file_handler)
        
        # Trace ID management
        self._trace_id_local = threading.local()
    
    def set_trace_id(self, trace_id: str):
        """Set trace ID for current thread"""
        self._trace_id_local.trace_id = trace_id
    
    def get_trace_id(self) -> Optional[str]:
        """Get trace ID for current thread"""
        return getattr(self._trace_id_local, 'trace_id', None)
    
    def _log_structured(self,
                       level: LogLevel,
                       event_type: EventType,
                       message: str,
                       symbol: Optional[str] = None,
                       data: Optional[Dict[str, Any]] = None,
                       error: Optional[Exception] = None):
        """Log structured entry"""
        
        entry = StructuredLogEntry(
            timestamp=time.time(),
            level=level.value,
            event_type=event_type.value,
            symbol=symbol,
            component=self.name,
            message=message,
            trace_id=self.get_trace_id(),
            session_id=self.session_id,
            data=data,
            error=str(error) if error else None,
            stack_trace=traceback.format_exc() if error else None
        )
        
        # Log as JSON for structured parsing
        json_message = entry.to_json()
        
        # Route to appropriate log level
        if level == LogLevel.DEBUG:
            self.logger.debug(json_message)
        elif level == LogLevel.INFO:
            self.logger.info(json_message)
        elif level == LogLevel.WARNING:
            self.logger.warning(json_message)
        elif level == LogLevel.ERROR:
            self.logger.error(json_message)
        elif level == LogLevel.CRITICAL:
            self.logger.critical(json_message)
    
    def debug(self, event_type: EventType, message: str, **kwargs):
        self._log_structured(LogLevel.DEBUG, event_type, message, **kwargs)
    
    def info(self, event_type: EventType, message: str, **kwargs):
        self._log_structured(LogLevel.INFO, event_type, message, **kwargs)
    
    def warning(self, event_type: EventType, message: str, **kwargs):
        self._log_structured(LogLevel.WARNING, event_type, message, **kwargs)
    
    def error(self, event_type: EventType, message: str, **kwargs):
        self._log_structured(LogLevel.ERROR, event_type, message, **kwargs)
    
    def critical(self, event_type: EventType, message: str, **kwargs):
        self._log_structured(LogLevel.CRITICAL, event_type, message, **kwargs)


class MetricsCollector:
    """Prometheus metrics collector for trading bot"""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        
        if not PROMETHEUS_AVAILABLE:
            # Create dummy metrics if Prometheus not available
            self._create_dummy_metrics()
            return
        
        # Order metrics
        self.orders_placed = Counter(
            'grid_bot_orders_placed_total',
            'Total number of orders placed',
            ['symbol', 'side', 'order_type'],
            registry=self.registry
        )
        
        self.orders_filled = Counter(
            'grid_bot_orders_filled_total',
            'Total number of orders filled',
            ['symbol', 'side'],
            registry=self.registry
        )
        
        self.orders_canceled = Counter(
            'grid_bot_orders_canceled_total',
            'Total number of orders canceled',
            ['symbol', 'reason'],
            registry=self.registry
        )
        
        # Position metrics
        self.position_size = Gauge(
            'grid_bot_position_size',
            'Current position size',
            ['symbol', 'side'],
            registry=self.registry
        )
        
        self.unrealized_pnl = Gauge(
            'grid_bot_unrealized_pnl',
            'Unrealized P&L',
            ['symbol', 'side'],
            registry=self.registry
        )
        
        self.realized_pnl = Counter(
            'grid_bot_realized_pnl_total',
            'Total realized P&L',
            ['symbol'],
            registry=self.registry
        )
        
        # Grid metrics
        self.grid_spacing = Gauge(
            'grid_bot_grid_spacing',
            'Current grid spacing',
            ['symbol'],
            registry=self.registry
        )
        
        self.active_grid_levels = Gauge(
            'grid_bot_active_grid_levels',
            'Number of active grid levels',
            ['symbol'],
            registry=self.registry
        )
        
        self.grid_adjustments = Counter(
            'grid_bot_grid_adjustments_total',
            'Total number of grid adjustments',
            ['symbol', 'reason'],
            registry=self.registry
        )
        
        # Emergency metrics
        self.emergency_triggers = Counter(
            'grid_bot_emergency_triggers_total',
            'Total number of emergency triggers',
            ['symbol', 'trigger_type'],
            registry=self.registry
        )
        
        self.lockdown_activations = Counter(
            'grid_bot_lockdown_activations_total',
            'Total number of lockdown mode activations',
            ['symbol', 'side'],
            registry=self.registry
        )
        
        # API metrics
        self.api_calls = Counter(
            'grid_bot_api_calls_total',
            'Total number of API calls',
            ['endpoint', 'method', 'status'],
            registry=self.registry
        )
        
        self.api_latency = Histogram(
            'grid_bot_api_latency_seconds',
            'API call latency',
            ['endpoint', 'method'],
            registry=self.registry
        )
        
        self.websocket_messages = Counter(
            'grid_bot_websocket_messages_total',
            'Total WebSocket messages processed',
            ['symbol', 'message_type'],
            registry=self.registry
        )
        
        # System metrics
        self.system_cpu_usage = Gauge(
            'grid_bot_system_cpu_usage_percent',
            'System CPU usage',
            registry=self.registry
        )
        
        self.system_memory_usage = Gauge(
            'grid_bot_system_memory_usage_percent',
            'System memory usage',
            registry=self.registry
        )
        
        self.bot_uptime = Gauge(
            'grid_bot_uptime_seconds',
            'Bot uptime in seconds',
            registry=self.registry
        )
        
        # Regime and anchor metrics
        self.regime_changes = Counter(
            'grid_bot_regime_changes_total',
            'Total regime changes',
            ['symbol', 'from_regime', 'to_regime'],
            registry=self.registry
        )
        
        self.anchor_resets = Counter(
            'grid_bot_anchor_resets_total',
            'Total anchor resets',
            ['symbol', 'reset_reason'],
            registry=self.registry
        )
        
        self.anchor_performance = Gauge(
            'grid_bot_anchor_performance_score',
            'Current anchor performance score',
            ['symbol'],
            registry=self.registry
        )
        
        # Info metrics
        self.bot_info = Info(
            'grid_bot_info',
            'Bot information',
            registry=self.registry
        )
        
        # Start time for uptime calculation
        self.start_time = time.time()
        
        # System monitoring thread
        self._start_system_monitoring()
    
    def _create_dummy_metrics(self):
        """Create dummy metrics when Prometheus is not available"""
        class DummyMetric:
            def labels(self, *args, **kwargs):
                return self
            
            def inc(self, *args, **kwargs):
                pass
                
            def set(self, *args, **kwargs):
                pass
                
            def observe(self, *args, **kwargs):
                pass
                
            def info(self, *args, **kwargs):
                pass
        
        # Set all metrics to dummy
        for attr_name in dir(self):
            if not attr_name.startswith('_') and attr_name != 'registry':
                setattr(self, attr_name, DummyMetric())
    
    def _start_system_monitoring(self):
        """Start background system monitoring"""
        if not PROMETHEUS_AVAILABLE:
            return
            
        def monitor_system():
            while True:
                try:
                    # Update system metrics
                    self.system_cpu_usage.set(psutil.cpu_percent())
                    self.system_memory_usage.set(psutil.virtual_memory().percent)
                    self.bot_uptime.set(time.time() - self.start_time)
                    
                    time.sleep(60)  # Update every minute
                    
                except Exception as e:
                    pass  # Silently continue if monitoring fails
        
        thread = threading.Thread(target=monitor_system, daemon=True)
        thread.start()
    
    def set_bot_info(self, **info):
        """Set bot information"""
        if PROMETHEUS_AVAILABLE:
            self.bot_info.info(info)


class HealthMonitor:
    """Health monitoring and alerting"""
    
    def __init__(self):
        self.checks: Dict[str, Callable[[], bool]] = {}
        self.last_check_times: Dict[str, float] = {}
        self.failure_counts: Dict[str, int] = defaultdict(int)
        self.max_failures = 3
        
        # Health metrics
        self.last_ticker_time = 0
        self.last_websocket_message = 0
        self.api_error_rate = deque(maxlen=100)  # Track last 100 API calls
        self.position_sync_errors = 0
        
        # Alert thresholds
        self.ticker_stale_threshold = 30  # 30 seconds
        self.websocket_stale_threshold = 60  # 1 minute
        self.max_api_error_rate = 0.1  # 10% error rate
    
    def register_check(self, name: str, check_func: Callable[[], bool]):
        """Register a health check"""
        self.checks[name] = check_func
    
    def update_ticker_time(self):
        """Update last ticker timestamp"""
        self.last_ticker_time = time.time()
    
    def update_websocket_time(self):
        """Update last WebSocket message timestamp"""
        self.last_websocket_message = time.time()
    
    def record_api_call(self, success: bool):
        """Record API call result for error rate tracking"""
        self.api_error_rate.append(0 if success else 1)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        current_time = time.time()
        
        status = {
            'healthy': True,
            'timestamp': current_time,
            'checks': {},
            'alerts': []
        }
        
        # Built-in checks
        checks = {
            'ticker_fresh': self._check_ticker_fresh,
            'websocket_active': self._check_websocket_active,
            'api_error_rate': self._check_api_error_rate,
            'system_resources': self._check_system_resources
        }
        
        # Add custom checks
        checks.update(self.checks)
        
        # Run all checks
        for check_name, check_func in checks.items():
            try:
                result = check_func()
                status['checks'][check_name] = {
                    'healthy': result,
                    'last_check': current_time
                }
                
                if not result:
                    status['healthy'] = False
                    self.failure_counts[check_name] += 1
                    
                    if self.failure_counts[check_name] >= self.max_failures:
                        status['alerts'].append(f"{check_name} has failed {self.failure_counts[check_name]} times")
                else:
                    self.failure_counts[check_name] = 0
                    
            except Exception as e:
                status['checks'][check_name] = {
                    'healthy': False,
                    'error': str(e),
                    'last_check': current_time
                }
                status['healthy'] = False
        
        return status
    
    def _check_ticker_fresh(self) -> bool:
        """Check if ticker data is fresh"""
        if self.last_ticker_time == 0:
            return True  # Not started yet
        return (time.time() - self.last_ticker_time) < self.ticker_stale_threshold
    
    def _check_websocket_active(self) -> bool:
        """Check if WebSocket is active"""
        if self.last_websocket_message == 0:
            return True  # Not started yet
        return (time.time() - self.last_websocket_message) < self.websocket_stale_threshold
    
    def _check_api_error_rate(self) -> bool:
        """Check API error rate"""
        if len(self.api_error_rate) < 10:
            return True  # Not enough data
            
        error_rate = sum(self.api_error_rate) / len(self.api_error_rate)
        return error_rate < self.max_api_error_rate
    
    def _check_system_resources(self) -> bool:
        """Check system resource usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            return cpu_percent < 90 and memory_percent < 90
        except:
            return True  # Assume OK if can't check


class ObservabilityManager:
    """Main observability manager coordinating all components"""
    
    def __init__(self, 
                 bot_name: str,
                 enable_prometheus: bool = True,
                 prometheus_port: int = 9090,
                 log_file: Optional[str] = None):
        
        self.bot_name = bot_name
        self.session_id = f"{bot_name}_{int(time.time())}"
        
        # Initialize components
        self.logger = StructuredLogger(
            bot_name, 
            log_file=log_file,
            session_id=self.session_id
        )
        
        self.metrics = MetricsCollector()
        self.health = HealthMonitor()
        
        # Set bot info
        self.metrics.set_bot_info(
            name=bot_name,
            version="1.0.0",
            exchange="bybit",
            session_id=self.session_id,
            start_time=datetime.now(timezone.utc).isoformat()
        )
        
        # Start Prometheus server if enabled
        if enable_prometheus and PROMETHEUS_AVAILABLE:
            try:
                start_http_server(prometheus_port, registry=self.metrics.registry)
                self.logger.info(
                    EventType.WEBSOCKET_CONNECTED,  # Reusing event type
                    f"Prometheus metrics server started on port {prometheus_port}"
                )
            except Exception as e:
                self.logger.error(
                    EventType.API_ERROR,
                    f"Failed to start Prometheus server: {e}",
                    error=e
                )
    
    def create_trace_id(self, prefix: str = "trade") -> str:
        """Create a new trace ID"""
        import uuid
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    
    def start_trace(self, trace_id: str):
        """Start a new trace"""
        self.logger.set_trace_id(trace_id)
    
    def get_health_endpoint_data(self) -> Dict[str, Any]:
        """Get data for /health endpoint"""
        return self.health.get_health_status()
    
    def record_order_placed(self, symbol: str, side: str, order_type: str, trace_id: str):
        """Record order placement"""
        self.start_trace(trace_id)
        self.metrics.orders_placed.labels(symbol=symbol, side=side, order_type=order_type).inc()
        self.logger.info(
            EventType.ORDER_PLACED,
            f"Order placed: {side} {symbol}",
            symbol=symbol,
            data={'side': side, 'order_type': order_type}
        )
    
    def record_order_filled(self, symbol: str, side: str, quantity: float, price: float, trace_id: str):
        """Record order fill"""
        self.start_trace(trace_id)
        self.metrics.orders_filled.labels(symbol=symbol, side=side).inc()
        self.logger.info(
            EventType.ORDER_FILLED,
            f"Order filled: {side} {quantity} {symbol} @ {price}",
            symbol=symbol,
            data={'side': side, 'quantity': quantity, 'price': price}
        )
    
    def record_emergency_trigger(self, symbol: str, trigger_type: str, reason: str):
        """Record emergency trigger"""
        trace_id = self.create_trace_id("emergency")
        self.start_trace(trace_id)
        self.metrics.emergency_triggers.labels(symbol=symbol, trigger_type=trigger_type).inc()
        self.logger.warning(
            EventType.EMERGENCY_TRIGGERED,
            f"Emergency triggered: {trigger_type} - {reason}",
            symbol=symbol,
            data={'trigger_type': trigger_type, 'reason': reason}
        )
    
    def record_api_call(self, endpoint: str, method: str, status: int, latency: float, success: bool):
        """Record API call metrics"""
        self.metrics.api_calls.labels(endpoint=endpoint, method=method, status=str(status)).inc()
        self.metrics.api_latency.labels(endpoint=endpoint, method=method).observe(latency)
        self.health.record_api_call(success)
    
    def update_position_metrics(self, symbol: str, side: str, size: float, unrealized_pnl: float):
        """Update position metrics"""
        self.metrics.position_size.labels(symbol=symbol, side=side).set(size)
        self.metrics.unrealized_pnl.labels(symbol=symbol, side=side).set(unrealized_pnl)
    
    def update_grid_metrics(self, symbol: str, spacing: float, active_levels: int):
        """Update grid metrics"""
        self.metrics.grid_spacing.labels(symbol=symbol).set(spacing)
        self.metrics.active_grid_levels.labels(symbol=symbol).set(active_levels)


# Health endpoint for HTTP server
async def health_endpoint_handler(request, observability: ObservabilityManager):
    """HTTP handler for health endpoint"""
    health_data = observability.get_health_endpoint_data()
    
    status_code = 200 if health_data['healthy'] else 503
    
    return {
        'status': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(health_data, indent=2)
    }


# Example usage
if __name__ == "__main__":
    # Initialize observability
    obs = ObservabilityManager(
        bot_name="bybit_grid_bot",
        enable_prometheus=True,
        prometheus_port=9090,
        log_file="logs/bot_structured.log"
    )
    
    # Example usage
    trace_id = obs.create_trace_id("test")
    obs.record_order_placed("BTCUSDT", "buy", "limit", trace_id)
    obs.record_order_filled("BTCUSDT", "buy", 0.01, 50000, trace_id)
    
    # Check health
    health = obs.get_health_endpoint_data()
    print(f"Bot healthy: {health['healthy']}")
    
    print("Observability system initialized. Metrics available at http://localhost:9090")