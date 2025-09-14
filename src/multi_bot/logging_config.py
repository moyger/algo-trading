import os
import logging
import time
from datetime import datetime, date
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
from collections import defaultdict

class DuplicateFilter(logging.Filter):
    """Deduplication filter to avoid duplicate log messages"""
    
    def __init__(self, name='', max_duplicates=3, timeout=3600):
        super().__init__(name)
        self.max_duplicates = max_duplicates
        self.timeout = timeout
        self.duplicate_count = defaultdict(int)
        self.last_log_time = defaultdict(float)
    
    def filter(self, record):
        # Create unique identifier for log message
        message_key = f"{record.levelname}:{record.getMessage()}"
        current_time = time.time()
        
        # Check if timeout exceeded, reset count if timeout
        if current_time - self.last_log_time[message_key] > self.timeout:
            self.duplicate_count[message_key] = 0
        
        # Increment count
        self.duplicate_count[message_key] += 1
        self.last_log_time[message_key] = current_time
        
        # Filter out if exceeds maximum duplicate count
        if self.duplicate_count[message_key] > self.max_duplicates:
            return False
        
        return True

class DailyStatusLogger:
    """Daily status logger, ensures status information is logged only once per day"""
    
    def __init__(self, logger, log_file='log/daily_status.log'):
        self.logger = logger
        self.log_file = log_file
        self.last_status_date = None
        self.last_status_message = None
        
        # Ensure log directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    def log_status(self, message):
        """Log status information, only once per day"""
        current_date = date.today()
        
        # Log if it's a new day or the message has changed
        if (self.last_status_date != current_date or 
            self.last_status_message != message):
            
            self.logger.info(message)
            self.last_status_date = current_date
            self.last_status_message = message

class ThresholdStateLogger:
    """Threshold state logger, logs only when state changes"""
    
    def __init__(self, logger):
        self.logger = logger
        self.threshold_states = {}  # Record threshold states for each symbol
    
    def log_threshold_status(self, symbol, side, position, threshold, is_over_threshold):
        """Log threshold status, only when state changes"""
        state_key = f"{symbol}_{side}"
        
        # Check if state has changed
        if (state_key not in self.threshold_states or 
            self.threshold_states[state_key] != is_over_threshold):
            
            if is_over_threshold:
                self.logger.info(f"Position {position} exceeds threshold {threshold}, {side} entering lockdown")
            else:
                self.logger.info(f"Position {position} below threshold {threshold}, {side} resuming normal operation")
            
            self.threshold_states[state_key] = is_over_threshold

def setup_logging():
    """Setup optimized logging configuration"""
    
    # Ensure log directory exists
    os.makedirs("log", exist_ok=True)
    
    # Create main logger
    main_logger = logging.getLogger('main')
    main_logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    main_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    main_logger.addHandler(console_handler)
    
    # File handler - split by date, limit file size
    file_handler = TimedRotatingFileHandler(
        'log/multi_grid_BN.log',
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Add deduplication filter
    duplicate_filter = DuplicateFilter(max_duplicates=3, timeout=3600)
    file_handler.addFilter(duplicate_filter)
    
    main_logger.addHandler(file_handler)
    
    return main_logger

def create_bot_logger(symbol):
    """Create independent logger for each symbol"""
    
    logger = logging.getLogger(f'bot_{symbol}')
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handler addition
    if logger.handlers:
        return logger
    
    # File handler - split by date, limit file size
    file_handler = TimedRotatingFileHandler(
        f'log/grid_BN_{symbol}.log',
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Add deduplication filter
    duplicate_filter = DuplicateFilter(max_duplicates=3, timeout=3600)
    file_handler.addFilter(duplicate_filter)
    
    logger.addHandler(file_handler)
    
    return logger

def setup_binance_multi_bot_logging():
    """Setup logging configuration for Binance multi-symbol bot"""
    
    # Check if called from single-symbol script
    import inspect
    import sys
    import os
    
    # Ensure log directory exists
    os.makedirs("log", exist_ok=True)
    
    # Traverse call stack to find caller
    log_filename = None
    for frame_info in inspect.stack():
        frame = frame_info.frame
        filename = frame.f_globals.get('__file__', '')
        if filename and 'single_bot' in filename and 'binance_bot.py' in filename:
            log_filename = "binance_single_bot.log"
            break
    
    if not log_filename:
        script_name = os.path.splitext(os.path.basename(__file__))[0]
        log_filename = f"{script_name}.log"
    
    handlers = [logging.StreamHandler()]
    
    try:
        # Use rotating file handler instead of regular file handler
        file_handler = TimedRotatingFileHandler(
            f"log/{log_filename}",
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        handlers.append(file_handler)
        print(f"Log will be written to file: log/{log_filename}")
    except PermissionError as e:
        print(f"Warning: Cannot create log file (insufficient permissions): {e}")
        print("Log will only output to console")
    except Exception as e:
        print(f"Warning: Cannot create log file: {e}")
        print("Log will only output to console")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
    
    logger = logging.getLogger()
    
    # Add deduplication filter for file handlers
    for handler in handlers:
        if isinstance(handler, TimedRotatingFileHandler):
            duplicate_filter = DuplicateFilter(max_duplicates=3, timeout=3600)
            handler.addFilter(duplicate_filter)
    
    return logger

def cleanup_old_logs(days=7):
    """Clean up old log files"""
    import glob
    import os
    from datetime import datetime, timedelta
    
    log_dir = "log"
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # Find all log files
    log_patterns = [
        "*.log.*",  # Rotated log files
        "*.log.gz",  # Compressed log files
    ]
    
    for pattern in log_patterns:
        for log_file in glob.glob(os.path.join(log_dir, pattern)):
            try:
                # Get file modification time
                file_mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
                if file_mtime < cutoff_date:
                    os.remove(log_file)
                    print(f"Deleted old log file: {log_file}")
            except Exception as e:
                print(f"Failed to delete log file {log_file}: {e}")
