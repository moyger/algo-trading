import asyncio
import os
import sys
import signal
import threading
import time
import yaml
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import sys
import os
sys.path.append(os.path.dirname(__file__))
from binance_multi_bot import BinanceGridBot
from logging_config import setup_logging, create_bot_logger, DailyStatusLogger

# Load environment variables
load_dotenv()

# Global variables to control all bots
running_bots = {}
stop_event = threading.Event()

# Configure optimized logging system
main_logger = setup_logging()
daily_status_logger = DailyStatusLogger(main_logger)

def load_config(config_file='config/symbols.yaml'):
    """
    Load configuration file
    
    Args:
        config_file: Configuration file path, supports yaml and json formats
        
    Returns:
        dict: Configuration dictionary
    """
    if not os.path.exists(config_file):
        main_logger.error(f"Configuration file {config_file} does not exist")
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                config = yaml.safe_load(f)
            elif config_file.endswith('.json'):
                config = json.load(f)
            else:
                main_logger.error(f"Unsupported configuration file format: {config_file}")
                return None
        
        # Validate configuration format
        if 'symbols' not in config:
            main_logger.error("Missing 'symbols' field in configuration file")
            return None
        
        if not isinstance(config['symbols'], list):
            main_logger.error("'symbols' field must be in list format")
            return None
        
        # Validate each symbol configuration
        for i, symbol_config in enumerate(config['symbols']):
            if 'name' not in symbol_config:
                main_logger.error(f"Symbol configuration #{i+1} missing 'name' field")
                return None
            
            # Set default values
            if 'grid_spacing' not in symbol_config:
                symbol_config['grid_spacing'] = 0.001
            if 'initial_quantity' not in symbol_config:
                symbol_config['initial_quantity'] = 3
            if 'leverage' not in symbol_config:
                symbol_config['leverage'] = 20
            if 'contract_type' not in symbol_config:
                symbol_config['contract_type'] = 'USDT'
        
        main_logger.info(f"Successfully loaded configuration file: {config_file}")
        return config
    
    except Exception as e:
        main_logger.error(f"Failed to load configuration file: {e}")
        return None

def validate_environment():
    """
    Validate environment variables
    
    Returns:
        tuple: (api_key, api_secret) or (None, None)
    """
    api_key = os.getenv("API_KEY", "")
    api_secret = os.getenv("API_SECRET", "")
    
    if not api_key or not api_secret:
        main_logger.error("API_KEY and API_SECRET must be set in .env file")
        return None, None
    
    # Validate other optional configurations
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    enable_notifications = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"
    
    if enable_notifications:
        if not telegram_bot_token or not telegram_chat_id:
            main_logger.warning("Telegram notifications enabled but missing BOT_TOKEN or CHAT_ID, disabling notification feature")
        else:
            main_logger.info("Telegram notification feature enabled")
    
    return api_key, api_secret

def create_bot_logger(symbol):
    """
    Create independent logger for each symbol
    
    Args:
        symbol: Symbol name
        
    Returns:
        logging.Logger: Logger instance
    """
    from logging_config import create_bot_logger as create_logger
    return create_logger(symbol)

def run_single_bot(symbol_config, api_key, api_secret):
    """
    Run grid bot for single symbol
    
    Args:
        symbol_config: Symbol configuration dictionary
        api_key: API key
        api_secret: API secret
        
    Returns:
        tuple: (symbol, success, error_message)
    """
    symbol = symbol_config['name']
    logger = create_bot_logger(symbol)
    
    try:
        # Build configuration dictionary
        config = {
            'grid_spacing': symbol_config['grid_spacing'],
            'initial_quantity': symbol_config['initial_quantity'],
            'leverage': symbol_config['leverage'],
            'contract_type': symbol_config['contract_type']
        }
        
        logger.info(f"Starting {symbol} grid bot")
        logger.info(f"Configuration: grid_spacing={config['grid_spacing']:.3f}, initial_quantity={config['initial_quantity']}, leverage={config['leverage']}")
        
        # Create bot instance
        bot = BinanceGridBot(symbol=symbol, api_key=api_key, api_secret=api_secret, config=config)
        
        # Store bot instance (for stopping)
        running_bots[symbol] = bot
        
        # Create event loop and run bot in new thread
        def run_bot_with_loop():
            try:
                # Create new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Run bot
                loop.run_until_complete(bot.start())
            except Exception as e:
                logger.error(f"Bot runtime exception: {e}")
            finally:
                try:
                    loop.close()
                except:
                    pass
        
        # Run in new thread
        import threading
        bot_thread = threading.Thread(target=run_bot_with_loop, name=f"bot-{symbol}")
        bot_thread.daemon = True
        bot_thread.start()
        
        # Wait briefly to ensure thread starts
        import time
        time.sleep(0.1)
        
        # Wait for bot to actually start
        max_wait_time = 30  # Wait maximum 30 seconds
        wait_time = 0
        while wait_time < max_wait_time:
            if symbol in running_bots:
                # Check if bot is actually running
                bot = running_bots[symbol]
                if hasattr(bot, 'running') and bot.running:
                    logger.info(f"{symbol} bot added to running list")
                    return symbol, True, None
            time.sleep(1)
            wait_time += 1
        
        # Remove from running list if timeout
        if symbol in running_bots:
            del running_bots[symbol]
        
        return symbol, False, "Bot startup timeout"
        
    except Exception as e:
        error_msg = f"Failed to start {symbol} bot: {str(e)}"
        logger.error(error_msg)
        return symbol, False, error_msg

def signal_handler(signum, frame):
    """
    Signal handler for graceful shutdown of all bots
    """
    main_logger.info("Received stop signal, shutting down all bots...")
    stop_event.set()
    
    # Stop all bots
    for symbol, bot in running_bots.items():
        try:
            bot.stop()
            main_logger.info(f"Stopped {symbol} bot")
        except Exception as e:
            main_logger.error(f"Failed to stop {symbol} bot: {e}")
    
    sys.exit(0)

def print_status():
    """
    Print current running status and write status summary log
    """
    while not stop_event.is_set():
        try:
            active_bots = len(running_bots)
            if active_bots > 0:
                symbols = list(running_bots.keys())
                status_info = f"Current active bots: {active_bots} - {', '.join(symbols)}"
                # Use daily status logger, log only once per day
                daily_status_logger.log_status(status_info)
                
                # Write status summary log (maintain original real-time updates)
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                status_summary = f"[{timestamp}] Active Bots: {', '.join([f'{s}=Running' for s in symbols])}"
                
                # Write status summary file
                try:
                    with open('log/status_summary.log', 'a', encoding='utf-8') as f:
                        f.write(status_summary + '\n')
                except Exception as e:
                    main_logger.error(f"Failed to write status summary log: {e}")
            else:
                daily_status_logger.log_status("No active bots currently")
                
                # Write status summary file
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                status_summary = f"[{timestamp}] Active Bots: None"
                try:
                    with open('log/status_summary.log', 'a', encoding='utf-8') as f:
                        f.write(status_summary + '\n')
                except Exception as e:
                    main_logger.error(f"Failed to write status summary log: {e}")
                    
            time.sleep(30)  # Check status every 30 seconds
        except KeyboardInterrupt:
            break

def main():
    """
    Main function
    """
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    main_logger.info("Multi-symbol grid trading bot starting...")
    
    # Validate environment variables
    api_key, api_secret = validate_environment()
    if not api_key or not api_secret:
        main_logger.error("Environment variable validation failed, exiting")
        sys.exit(1)
    
    # Load configuration file
    config = load_config()
    if not config:
        main_logger.error("Configuration file loading failed, exiting")
        sys.exit(1)
    
    symbols = config['symbols']
    main_logger.info(f"Configured {len(symbols)} symbols: {[s['name'] for s in symbols]}")
    
    # Start status monitoring thread
    status_thread = threading.Thread(target=print_status, daemon=True)
    status_thread.start()
    
    # Run all bots directly, without using thread pool
    bot_threads = {}
    for symbol_config in symbols:
        symbol = symbol_config['name']
        main_logger.info(f"Starting {symbol} grid bot")
        
        # Create bot thread
        bot_thread = threading.Thread(
            target=run_single_bot, 
            args=(symbol_config, api_key, api_secret),
            name=f"bot-{symbol}",
            daemon=True
        )
        bot_thread.start()
        bot_threads[symbol] = bot_thread
    
    # Wait for all bots to start
    main_logger.info("Waiting for all bots to start...")
    for symbol, thread in bot_threads.items():
        thread.join(timeout=60)  # Wait maximum 60 seconds
    
    # Main loop: monitor bot status
    try:
        while not stop_event.is_set():
            active_bots = len(running_bots)
            if active_bots > 0:
                symbols = list(running_bots.keys())
                # Use daily status logger, log only once per day
                daily_status_logger.log_status(f"Current active bots: {active_bots} - {', '.join(symbols)}")
            else:
                daily_status_logger.log_status("No active bots currently")
            
            time.sleep(30)  # Check status every 30 seconds
    except KeyboardInterrupt:
        main_logger.info("Received interrupt signal, stopping all bots...")
        stop_event.set()
        
        # Stop all bots
        for symbol, bot in running_bots.items():
            try:
                bot.stop()
                main_logger.info(f"Stopped {symbol} bot")
            except Exception as e:
                main_logger.error(f"Failed to stop {symbol} bot: {e}")

if __name__ == "__main__":
    main() 