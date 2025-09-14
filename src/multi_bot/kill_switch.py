"""
Kill Switch and Capital Guardrails System

This module provides comprehensive emergency controls and capital protection
mechanisms for production grid trading operations.
"""

import asyncio
import time
import logging
import signal
import os
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class EmergencyAction(Enum):
    """Types of emergency actions"""
    CANCEL_ALL_ORDERS = "cancel_all_orders"
    CLOSE_ALL_POSITIONS = "close_all_positions"
    ENTER_LOCKDOWN = "enter_lockdown"
    STOP_TRADING = "stop_trading"
    REDUCE_POSITIONS = "reduce_positions"


class GuardrailType(Enum):
    """Types of capital guardrails"""
    MAX_TOTAL_NOTIONAL = "max_total_notional"
    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_ORDERS_PER_SYMBOL = "max_orders_per_symbol"
    MIN_AVAILABLE_BALANCE = "min_available_balance"
    MAX_POSITION_SIZE = "max_position_size"
    MAX_LEVERAGE = "max_leverage"


@dataclass
class EmergencyTrigger:
    """Definition of an emergency trigger condition"""
    name: str
    trigger_type: GuardrailType
    threshold: float
    current_value: float
    enabled: bool = True
    last_triggered: Optional[float] = None
    trigger_count: int = 0
    
    @property
    def is_breached(self) -> bool:
        """Check if trigger condition is breached"""
        if not self.enabled:
            return False
            
        if self.trigger_type in [GuardrailType.MAX_TOTAL_NOTIONAL, 
                               GuardrailType.MAX_DAILY_LOSS,
                               GuardrailType.MAX_ORDERS_PER_SYMBOL,
                               GuardrailType.MAX_POSITION_SIZE]:
            return self.current_value > self.threshold
        elif self.trigger_type == GuardrailType.MIN_AVAILABLE_BALANCE:
            return self.current_value < self.threshold
        
        return False


@dataclass
class EmergencyState:
    """Current emergency state"""
    active: bool = False
    triggered_at: Optional[float] = None
    triggered_by: Optional[str] = None
    actions_taken: List[EmergencyAction] = None
    lockdown_mode: bool = False
    trading_disabled: bool = False
    
    def __post_init__(self):
        if self.actions_taken is None:
            self.actions_taken = []


class KillSwitchManager:
    """
    Comprehensive kill switch and capital protection system
    
    Features:
    - Multiple trigger conditions with configurable thresholds
    - Automatic and manual emergency procedures
    - Signal handlers for external kill commands
    - Graduated response system (warnings -> actions -> lockdown)
    - State persistence across restarts
    """
    
    def __init__(self, 
                 bot_instance: Any,
                 config: Dict[str, Any],
                 state_file: Optional[str] = None):
        
        self.bot = bot_instance
        self.config = config
        self.state_file = state_file or "killswitch_state.json"
        
        # Emergency state
        self.emergency_state = EmergencyState()
        self.triggers: Dict[str, EmergencyTrigger] = {}
        
        # Callbacks for emergency actions
        self.action_callbacks: Dict[EmergencyAction, Callable] = {}
        
        # Initialize triggers from config
        self._initialize_triggers()
        
        # Load persistent state
        self._load_state()
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        # Monitoring
        self._monitoring_task = None
        self._monitoring_interval = config.get('monitoring_interval', 5)  # 5 seconds
        
        logger.info("Kill switch manager initialized")
    
    def _initialize_triggers(self):
        """Initialize emergency triggers from configuration"""
        
        # Maximum total notional exposure
        max_notional = self.config.get('max_total_notional', 50000.0)
        self.triggers['max_notional'] = EmergencyTrigger(
            name="Maximum Total Notional",
            trigger_type=GuardrailType.MAX_TOTAL_NOTIONAL,
            threshold=max_notional,
            current_value=0.0
        )
        
        # Maximum daily loss
        max_daily_loss = self.config.get('max_daily_loss', 1000.0)
        self.triggers['max_daily_loss'] = EmergencyTrigger(
            name="Maximum Daily Loss",
            trigger_type=GuardrailType.MAX_DAILY_LOSS,
            threshold=max_daily_loss,
            current_value=0.0
        )
        
        # Maximum orders per symbol
        max_orders = self.config.get('max_orders_per_symbol', 500)
        self.triggers['max_orders'] = EmergencyTrigger(
            name="Maximum Orders Per Symbol",
            trigger_type=GuardrailType.MAX_ORDERS_PER_SYMBOL,
            threshold=max_orders,
            current_value=0
        )
        
        # Minimum available balance
        min_balance = self.config.get('min_available_balance', 1000.0)
        self.triggers['min_balance'] = EmergencyTrigger(
            name="Minimum Available Balance",
            trigger_type=GuardrailType.MIN_AVAILABLE_BALANCE,
            threshold=min_balance,
            current_value=0.0
        )
        
        # Maximum position size
        max_position = self.config.get('max_position_size', 10.0)
        self.triggers['max_position'] = EmergencyTrigger(
            name="Maximum Position Size",
            trigger_type=GuardrailType.MAX_POSITION_SIZE,
            threshold=max_position,
            current_value=0.0
        )
        
        logger.info(f"Initialized {len(self.triggers)} emergency triggers")
    
    def register_action_callback(self, action: EmergencyAction, callback: Callable):
        """Register callback for emergency action"""
        self.action_callbacks[action] = callback
        logger.info(f"Registered callback for {action.value}")
    
    async def start_monitoring(self):
        """Start continuous monitoring of trigger conditions"""
        if self._monitoring_task and not self._monitoring_task.done():
            return
        
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Kill switch monitoring started")
    
    async def stop_monitoring(self):
        """Stop monitoring"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Kill switch monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while True:
            try:
                await self._check_all_triggers()
                await asyncio.sleep(self._monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in kill switch monitoring: {e}")
                await asyncio.sleep(1)
    
    async def _check_all_triggers(self):
        """Check all trigger conditions"""
        await self._update_trigger_values()
        
        for trigger_name, trigger in self.triggers.items():
            if trigger.is_breached:
                await self._handle_trigger_breach(trigger_name, trigger)
    
    async def _update_trigger_values(self):
        """Update current values for all triggers"""
        try:
            # Get current trading state from bot
            if not hasattr(self.bot, 'get_trading_state'):
                return
            
            state = await self.bot.get_trading_state()
            
            # Update max notional
            total_notional = 0
            for symbol, positions in state.get('positions', {}).items():
                for side, position in positions.items():
                    if position.get('size', 0) != 0:
                        notional = abs(float(position['size'])) * float(position['mark_price'])
                        total_notional += notional
            
            self.triggers['max_notional'].current_value = total_notional
            
            # Update daily loss
            daily_pnl = state.get('daily_pnl', 0.0)
            if daily_pnl < 0:  # Only consider losses
                self.triggers['max_daily_loss'].current_value = abs(daily_pnl)
            
            # Update max orders
            max_orders = 0
            for symbol, orders in state.get('orders', {}).items():
                active_orders = len([o for o in orders if o.get('status') in ['NEW', 'PARTIALLY_FILLED']])
                max_orders = max(max_orders, active_orders)
            
            self.triggers['max_orders'].current_value = max_orders
            
            # Update available balance
            balance = state.get('balance', {})
            available = balance.get('available', 0.0)
            self.triggers['min_balance'].current_value = available
            
            # Update max position
            max_position = 0
            for symbol, positions in state.get('positions', {}).items():
                for side, position in positions.items():
                    position_size = abs(float(position.get('size', 0)))
                    max_position = max(max_position, position_size)
            
            self.triggers['max_position'].current_value = max_position
            
        except Exception as e:
            logger.error(f"Error updating trigger values: {e}")
    
    async def _handle_trigger_breach(self, trigger_name: str, trigger: EmergencyTrigger):
        """Handle trigger breach with appropriate response"""
        current_time = time.time()
        
        # Update trigger state
        if trigger.last_triggered is None or (current_time - trigger.last_triggered) > 300:
            trigger.trigger_count += 1
            trigger.last_triggered = current_time
            
            logger.critical(f"EMERGENCY TRIGGER BREACHED: {trigger.name}")
            logger.critical(f"Current: {trigger.current_value}, Threshold: {trigger.threshold}")
            
            # Determine response based on trigger type and count
            await self._execute_emergency_response(trigger_name, trigger)
            
            # Save state
            self._save_state()
    
    async def _execute_emergency_response(self, trigger_name: str, trigger: EmergencyTrigger):
        """Execute appropriate emergency response"""
        
        if trigger.trigger_count == 1:
            # First breach - warning and position reduction
            await self._send_emergency_alert(trigger_name, trigger, "WARNING")
            await self._execute_action(EmergencyAction.REDUCE_POSITIONS)
            
        elif trigger.trigger_count == 2:
            # Second breach - cancel all orders
            await self._send_emergency_alert(trigger_name, trigger, "CRITICAL")
            await self._execute_action(EmergencyAction.CANCEL_ALL_ORDERS)
            
        elif trigger.trigger_count >= 3:
            # Third breach - full emergency response
            await self._send_emergency_alert(trigger_name, trigger, "EMERGENCY")
            await self._execute_full_emergency()
    
    async def _execute_full_emergency(self):
        """Execute full emergency response (kill switch activated)"""
        logger.critical("KILL SWITCH ACTIVATED - EXECUTING FULL EMERGENCY RESPONSE")
        
        self.emergency_state.active = True
        self.emergency_state.triggered_at = time.time()
        self.emergency_state.trading_disabled = True
        
        # Execute all emergency actions
        actions = [
            EmergencyAction.CANCEL_ALL_ORDERS,
            EmergencyAction.CLOSE_ALL_POSITIONS,
            EmergencyAction.ENTER_LOCKDOWN,
            EmergencyAction.STOP_TRADING
        ]
        
        for action in actions:
            try:
                await self._execute_action(action)
                self.emergency_state.actions_taken.append(action)
            except Exception as e:
                logger.error(f"Failed to execute emergency action {action}: {e}")
        
        self.emergency_state.lockdown_mode = True
        
        # Persist emergency state
        self._save_state()
        
        # Send final alert
        await self._send_emergency_alert("KILL_SWITCH", None, "ACTIVATED")
    
    async def _execute_action(self, action: EmergencyAction):
        """Execute specific emergency action"""
        if action in self.action_callbacks:
            try:
                await self.action_callbacks[action]()
                logger.info(f"Executed emergency action: {action.value}")
            except Exception as e:
                logger.error(f"Failed to execute action {action.value}: {e}")
                raise
        else:
            logger.warning(f"No callback registered for action: {action.value}")
    
    async def manual_kill_switch(self, reason: str = "Manual activation"):
        """Manually activate kill switch"""
        logger.critical(f"MANUAL KILL SWITCH ACTIVATED: {reason}")
        
        self.emergency_state.triggered_by = f"manual: {reason}"
        await self._execute_full_emergency()
    
    async def manual_emergency_action(self, action: EmergencyAction, reason: str = "Manual"):
        """Manually execute specific emergency action"""
        logger.warning(f"MANUAL EMERGENCY ACTION: {action.value} - {reason}")
        
        await self._execute_action(action)
        
        # Send alert
        await self._send_emergency_alert("MANUAL", None, f"ACTION: {action.value}")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for external kill commands"""
        
        def signal_handler(signum, frame):
            logger.critical(f"RECEIVED KILL SIGNAL: {signum}")
            
            # Use asyncio to handle the kill switch
            if hasattr(asyncio, '_get_running_loop') and asyncio._get_running_loop():
                asyncio.create_task(self.manual_kill_switch(f"Signal {signum}"))
            else:
                # If no event loop, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.manual_kill_switch(f"Signal {signum}"))
        
        # Register signal handlers
        if hasattr(signal, 'SIGUSR1'):  # Unix systems
            signal.signal(signal.SIGUSR1, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("Signal handlers registered for kill switch")
    
    async def _send_emergency_alert(self, trigger_name: str, trigger: Optional[EmergencyTrigger], level: str):
        """Send emergency alert notification"""
        try:
            if hasattr(self.bot, 'send_emergency_notification'):
                message = f"🚨 EMERGENCY ALERT [{level}] 🚨\n"
                message += f"Trigger: {trigger_name}\n"
                
                if trigger:
                    message += f"Current Value: {trigger.current_value}\n"
                    message += f"Threshold: {trigger.threshold}\n"
                    message += f"Breach Count: {trigger.trigger_count}\n"
                
                message += f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                message += f"Actions: {', '.join([a.value for a in self.emergency_state.actions_taken])}"
                
                await self.bot.send_emergency_notification(message)
        except Exception as e:
            logger.error(f"Failed to send emergency alert: {e}")
    
    def _save_state(self):
        """Save emergency state to file"""
        try:
            state_data = {
                'emergency_state': {
                    'active': self.emergency_state.active,
                    'triggered_at': self.emergency_state.triggered_at,
                    'triggered_by': self.emergency_state.triggered_by,
                    'actions_taken': [action.value for action in self.emergency_state.actions_taken],
                    'lockdown_mode': self.emergency_state.lockdown_mode,
                    'trading_disabled': self.emergency_state.trading_disabled
                },
                'triggers': {
                    name: {
                        'last_triggered': trigger.last_triggered,
                        'trigger_count': trigger.trigger_count,
                        'enabled': trigger.enabled
                    }
                    for name, trigger in self.triggers.items()
                },
                'last_update': time.time()
            }
            
            # Write atomically
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(state_data, f, indent=2)
            
            os.replace(temp_file, self.state_file)
            
        except Exception as e:
            logger.error(f"Failed to save kill switch state: {e}")
    
    def _load_state(self):
        """Load emergency state from file"""
        if not os.path.exists(self.state_file):
            return
        
        try:
            with open(self.state_file, 'r') as f:
                state_data = json.load(f)
            
            # Restore emergency state
            emergency = state_data.get('emergency_state', {})
            self.emergency_state.active = emergency.get('active', False)
            self.emergency_state.triggered_at = emergency.get('triggered_at')
            self.emergency_state.triggered_by = emergency.get('triggered_by')
            self.emergency_state.lockdown_mode = emergency.get('lockdown_mode', False)
            self.emergency_state.trading_disabled = emergency.get('trading_disabled', False)
            
            # Restore actions taken
            actions_taken = emergency.get('actions_taken', [])
            self.emergency_state.actions_taken = [EmergencyAction(action) for action in actions_taken]
            
            # Restore trigger states
            for name, trigger_data in state_data.get('triggers', {}).items():
                if name in self.triggers:
                    trigger = self.triggers[name]
                    trigger.last_triggered = trigger_data.get('last_triggered')
                    trigger.trigger_count = trigger_data.get('trigger_count', 0)
                    trigger.enabled = trigger_data.get('enabled', True)
            
            logger.info(f"Loaded kill switch state from {self.state_file}")
            
            if self.emergency_state.active:
                logger.critical("EMERGENCY STATE ACTIVE FROM PREVIOUS SESSION")
            
        except Exception as e:
            logger.error(f"Failed to load kill switch state: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current kill switch status"""
        return {
            'emergency_active': self.emergency_state.active,
            'lockdown_mode': self.emergency_state.lockdown_mode,
            'trading_disabled': self.emergency_state.trading_disabled,
            'triggered_at': self.emergency_state.triggered_at,
            'triggered_by': self.emergency_state.triggered_by,
            'actions_taken': [action.value for action in self.emergency_state.actions_taken],
            'triggers': {
                name: {
                    'name': trigger.name,
                    'type': trigger.trigger_type.value,
                    'threshold': trigger.threshold,
                    'current_value': trigger.current_value,
                    'breached': trigger.is_breached,
                    'enabled': trigger.enabled,
                    'trigger_count': trigger.trigger_count,
                    'last_triggered': trigger.last_triggered
                }
                for name, trigger in self.triggers.items()
            }
        }
    
    async def reset_emergency_state(self, confirmation: str):
        """Reset emergency state (requires confirmation)"""
        if confirmation != "CONFIRM_RESET_EMERGENCY":
            raise ValueError("Invalid confirmation code")
        
        logger.warning("RESETTING EMERGENCY STATE - MANUAL CONFIRMATION RECEIVED")
        
        # Reset emergency state
        self.emergency_state = EmergencyState()
        
        # Reset trigger counts
        for trigger in self.triggers.values():
            trigger.trigger_count = 0
            trigger.last_triggered = None
        
        # Save state
        self._save_state()
        
        logger.info("Emergency state reset completed")
    
    def enable_trigger(self, trigger_name: str, enabled: bool = True):
        """Enable/disable specific trigger"""
        if trigger_name in self.triggers:
            self.triggers[trigger_name].enabled = enabled
            logger.info(f"Trigger '{trigger_name}' {'enabled' if enabled else 'disabled'}")
            self._save_state()
        else:
            raise ValueError(f"Unknown trigger: {trigger_name}")
    
    def update_threshold(self, trigger_name: str, new_threshold: float):
        """Update trigger threshold"""
        if trigger_name in self.triggers:
            old_threshold = self.triggers[trigger_name].threshold
            self.triggers[trigger_name].threshold = new_threshold
            logger.info(f"Updated '{trigger_name}' threshold: {old_threshold} -> {new_threshold}")
            self._save_state()
        else:
            raise ValueError(f"Unknown trigger: {trigger_name}")


# HTTP endpoint handlers for kill switch control
class KillSwitchHTTPHandler:
    """HTTP handlers for kill switch control interface"""
    
    def __init__(self, kill_switch: KillSwitchManager):
        self.kill_switch = kill_switch
    
    async def status_handler(self, request):
        """GET /kill-switch/status"""
        status = self.kill_switch.get_status()
        return {
            'status': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(status, indent=2, default=str)
        }
    
    async def manual_kill_handler(self, request):
        """POST /kill-switch/activate"""
        try:
            data = json.loads(request.get('body', '{}'))
            reason = data.get('reason', 'Manual HTTP activation')
            
            await self.kill_switch.manual_kill_switch(reason)
            
            return {
                'status': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'success': True, 'message': 'Kill switch activated'})
            }
        except Exception as e:
            return {
                'status': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'error': str(e)})
            }
    
    async def manual_action_handler(self, request):
        """POST /kill-switch/action"""
        try:
            data = json.loads(request.get('body', '{}'))
            action_name = data.get('action')
            reason = data.get('reason', 'Manual HTTP action')
            
            action = EmergencyAction(action_name)
            await self.kill_switch.manual_emergency_action(action, reason)
            
            return {
                'status': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'success': True, 'message': f'Action {action_name} executed'})
            }
        except Exception as e:
            return {
                'status': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'error': str(e)})
            }


# Example usage
if __name__ == "__main__":
    import sys
    
    # Mock bot class for testing
    class MockBot:
        async def get_trading_state(self):
            return {
                'positions': {
                    'BTCUSDT': {
                        'long': {'size': 0.1, 'mark_price': 50000}
                    }
                },
                'orders': {
                    'BTCUSDT': [{'status': 'NEW'}]
                },
                'balance': {'available': 5000},
                'daily_pnl': -50
            }
        
        async def send_emergency_notification(self, message):
            print(f"EMERGENCY ALERT: {message}")
    
    async def test_kill_switch():
        # Configuration
        config = {
            'max_total_notional': 1000.0,
            'max_daily_loss': 100.0,
            'max_orders_per_symbol': 10,
            'min_available_balance': 1000.0,
            'max_position_size': 1.0
        }
        
        # Create mock bot and kill switch
        bot = MockBot()
        kill_switch = KillSwitchManager(bot, config)
        
        # Register action callbacks
        async def cancel_all():
            print("EMERGENCY: Canceling all orders")
        
        async def close_positions():
            print("EMERGENCY: Closing all positions")
        
        kill_switch.register_action_callback(EmergencyAction.CANCEL_ALL_ORDERS, cancel_all)
        kill_switch.register_action_callback(EmergencyAction.CLOSE_ALL_POSITIONS, close_positions)
        
        # Start monitoring
        await kill_switch.start_monitoring()
        
        # Wait a bit for monitoring to run
        await asyncio.sleep(10)
        
        # Test manual kill switch
        await kill_switch.manual_kill_switch("Testing manual activation")
        
        # Show status
        status = kill_switch.get_status()
        print(f"Kill switch status: {json.dumps(status, indent=2, default=str)}")
        
        await kill_switch.stop_monitoring()
    
    # Run test
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_kill_switch())
    else:
        print("Kill switch module loaded. Use 'python kill_switch.py test' to run tests.")