"""Centralized logging configuration for MCP Server.

Provides robust logger factory with file rotation, multiple handlers,
and consistent formatting across all MCP server components.

Features:
    - Dual output: Console (stdout) + File handlers
    - Automatic log file rotation (configurable via settings)
    - Separate error log file for quick issue identification
    - Configurable log levels per module
    - Structured logging with context (log_context)
    - ANSI colors for console output (auto-disabled for non-TTY)
    - Startup banner with configuration summary
    - Performance optimized for sync/async operations

Author: Odiseo
Version: 2.0.0
"""

import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import Settings

# ============================================================================
# Global Configuration
# ============================================================================
_ROOT_LOGGER: logging.Logger | None = None
_LOG_DIR: Path | None = None

# Log formats
_LOG_FORMAT_DETAILED = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
)
_LOG_FORMAT_SIMPLE = "%(asctime)s - %(levelname)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Module-level logger configuration (override root level for specific modules)
_MODULE_LEVELS = {
    "mcp_server": logging.INFO,
    "mcp_tools_search": logging.DEBUG,
    "mcp_tools_fuzzy": logging.DEBUG,
    "mcp_tools_bookings": logging.INFO,
    "mcp_handlers": logging.INFO,
    "mcp_db": logging.DEBUG,
    "mcp_embeddings": logging.INFO,
}

# Banner lock for multi-process scenarios
_BANNER_FLAG_FILE = os.path.join(tempfile.gettempdir(), ".mcp_server_banner_printed")
_BANNER_FLAG_PATH = Path(_BANNER_FLAG_FILE)
_banner_printed_by_this_process = False

# ============================================================================
# ANSI Color Codes (auto-disabled for non-TTY)
# ============================================================================
_USE_COLORS = sys.stdout.isatty()

COLORS = {
    "reset": "\033[0m" if _USE_COLORS else "",
    "bold": "\033[1m" if _USE_COLORS else "",
    "dim": "\033[2m" if _USE_COLORS else "",
    "cyan": "\033[36m" if _USE_COLORS else "",
    "green": "\033[32m" if _USE_COLORS else "",
    "yellow": "\033[33m" if _USE_COLORS else "",
    "blue": "\033[34m" if _USE_COLORS else "",
    "magenta": "\033[35m" if _USE_COLORS else "",
    "white": "\033[97m" if _USE_COLORS else "",
    "red": "\033[31m" if _USE_COLORS else "",
    # Bright variants
    "b_blue": "\033[94m" if _USE_COLORS else "",
    "b_cyan": "\033[96m" if _USE_COLORS else "",
    "b_green": "\033[92m" if _USE_COLORS else "",
    "b_yellow": "\033[93m" if _USE_COLORS else "",
    "b_magenta": "\033[95m" if _USE_COLORS else "",
}

# Color shortcuts for banner
_B = COLORS["bold"]
_R = COLORS["reset"]
_BC = COLORS["b_cyan"]
_BG = COLORS["b_green"]
_BY = COLORS["b_yellow"]
_BM = COLORS["b_magenta"]
_BB = COLORS["b_blue"]

# fmt: off
BANNER = f"""
{_B}{_BC} ███╗   ███╗{_BG}  ██████╗{_BY} ██████╗ {_R}
{_BC} ████╗ ████║{_BG} ██╔════╝{_BY} ██╔══██╗{_R}
{_BC} ██╔████╔██║{_BG} ██║     {_BY} ██████╔╝{_R}
{_BC} ██║╚██╔╝██║{_BG} ██║     {_BY} ██╔═══╝ {_R}
{_BC} ██║ ╚═╝ ██║{_BG} ╚██████╗{_BY} ██║     {_R}
{_BC} ╚═╝     ╚═╝{_BG}  ╚═════╝{_BY} ╚═╝     {_R}
{_R}"""
# fmt: on


def _try_acquire_banner_lock() -> bool:
    """Try to acquire banner lock atomically using exclusive file creation.

    Returns:
        True if this process should print the banner, False otherwise.
    """
    try:
        # O_CREAT | O_EXCL ensures atomic creation - fails if file exists
        fd = os.open(_BANNER_FLAG_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def cleanup_banner_flag() -> None:
    """Remove banner flag file for fresh container/process starts.

    Call this at application shutdown or when restarting the server.
    """
    try:
        if _BANNER_FLAG_PATH.exists():
            _BANNER_FLAG_PATH.unlink()
    except OSError:
        pass


def _mask_sensitive(value: str, show_chars: int = 4) -> str:
    """Mask sensitive value for display, showing only first N chars.

    Args:
        value: Sensitive value to mask.
        show_chars: Number of chars to show at start.

    Returns:
        Masked string.
    """
    if not value:
        return "(not set)"
    if len(value) <= show_chars:
        return "***"
    return f"{value[:show_chars]}{'*' * 8}"


def print_banner() -> None:
    """Print the service startup banner to stderr (avoid STDIO conflicts)."""
    global _banner_printed_by_this_process
    if not _try_acquire_banner_lock():
        return

    _banner_printed_by_this_process = True
    print(BANNER, file=sys.stderr)
    print(f"{COLORS['dim']}{'─' * 72}{COLORS['reset']}", file=sys.stderr)
    print(
        f"{COLORS['cyan']}{COLORS['bold']}  "
        f"Odiseo MCP Server - Model Context Protocol{COLORS['reset']}",
        file=sys.stderr,
    )
    print(f"{COLORS['dim']}{'─' * 72}{COLORS['reset']}\n", file=sys.stderr)


def print_config_summary(settings: "Settings") -> None:
    """Print a formatted configuration summary organized by categories.

    Args:
        settings: Settings instance with loaded configuration.
    """
    if not _banner_printed_by_this_process:
        return  # Banner wasn't printed by this process

    c = COLORS

    def _line(label: str, value: str, color: str = "cyan") -> None:
        print(f"  {c['dim']}│{c['reset']} {label:<26} {c[color]}{value}{c['reset']}", file=sys.stderr)

    def _header(icon: str, title: str, color: str) -> None:
        print(f"\n  {c[color]}{icon} {title}{c['reset']}", file=sys.stderr)
        print(f"  {c['dim']}├{'─' * 50}{c['reset']}", file=sys.stderr)

    # =========================================================================
    # Database Configuration
    # =========================================================================
    _header("▶", "Database Configuration", "blue")
    # Mask password in DATABASE_URL
    db_url = settings.DATABASE_URL
    if "@" in db_url:
        parts = db_url.split("@")
        auth_part = parts[0]
        if ":" in auth_part.split("//")[-1]:
            user_pass = auth_part.split("//")[-1]
            user = user_pass.split(":")[0]
            masked_url = f"{auth_part.split('//')[0]}//{user}:***@{parts[1]}"
        else:
            masked_url = db_url
    else:
        masked_url = db_url
    _line("Database URL", masked_url[:50] + "..." if len(masked_url) > 50 else masked_url)
    _line("Schema", settings.SCHEMA_NAME)

    # =========================================================================
    # AI/Embeddings Configuration
    # =========================================================================
    _header("▶", "AI/Embeddings Configuration", "magenta")
    _line("Google API Key", _mask_sensitive(settings.GOOGLE_API_KEY))
    _line("Embedding Model", settings.EMBEDDING_MODEL)
    _line("Batch Size", str(settings.BATCH_SIZE))

    # =========================================================================
    # Google Calendar (if enabled)
    # =========================================================================
    if settings.GOOGLE_CALENDAR_ENABLED:
        _header("▶", "Google Calendar Configuration", "green")
        _line("Calendar ID", settings.GOOGLE_CALENDAR_ID)
        _line("Timezone", settings.GOOGLE_CALENDAR_TIMEZONE)
        _line("Credentials", str(settings.google_calendar_credentials_path)[:40] + "...")

    # =========================================================================
    # Booking Configuration
    # =========================================================================
    _header("▶", "Booking Configuration", "cyan")
    _line("Default Duration", f"{settings.BOOKING_DEFAULT_DURATION_MINUTES} min")
    _line("Slot Interval", f"{settings.BOOKING_SLOT_INTERVAL_MINUTES} min")
    _line("Advance Booking Days", str(settings.BOOKING_ADVANCE_BOOKING_DAYS))
    _line("Min Advance", f"{settings.BOOKING_MIN_ADVANCE_MINUTES} min")

    # =========================================================================
    # Server Configuration
    # =========================================================================
    _header("▶", "Server Configuration", "green")
    _line("Port", str(settings.MCP_PORT), "cyan")
    _line("Max Concurrent Requests", str(settings.MAX_CONCURRENT_REQUESTS))
    _line("Debug Mode", str(settings.DEBUG_MODE).lower())

    # =========================================================================
    # Logging Configuration
    # =========================================================================
    _header("▶", "Logging Configuration", "b_yellow")
    _line("Level", settings.LOG_LEVEL, "green")
    _line("Directory", settings.LOG_DIR)
    _line("Max File Size", f"{settings.LOG_MAX_SIZE_MB} MB")
    _line("Backup Count", str(settings.LOG_BACKUP_COUNT))

    # =========================================================================
    # Footer
    # =========================================================================
    print(f"\n{c['dim']}{'─' * 72}{c['reset']}", file=sys.stderr)
    print(f"  {c['green']}{c['bold']}✓ MCP Server ready{c['reset']}", file=sys.stderr)
    print(f"{c['dim']}{'─' * 72}{c['reset']}\n", file=sys.stderr)


def setup_logging(
    name: str = "mcp_server",
    level: str | None = None,
    enable_file: bool = True,
    show_banner: bool = True,
    settings: "Settings | None" = None,
) -> logging.Logger:
    """Configure logging with file rotation and console output.

    Should be called once at application startup. Creates:
    - Console handler with simple format
    - File handler with detailed format and rotation
    - Separate error file for ERROR+ level messages

    Args:
        name: Logger name (default: mcp_server)
        level: Logging level (DEBUG, INFO, WARNING, ERROR). If None, uses settings.
        enable_file: Whether to write logs to files.
        show_banner: Whether to print startup banner.
        settings: Optional Settings instance for config summary.

    Returns:
        Configured logger instance.

    Example:
        from utils.logger import setup_logging
        from config import settings

        logger = setup_logging(settings=settings)
        logger.info("MCP Server started")
    """
    global _ROOT_LOGGER, _LOG_DIR

    # Import settings if not provided
    if settings is None:
        from config import settings as app_settings

        settings = app_settings

    # Use level from settings if not provided
    if level is None:
        level = settings.LOG_LEVEL

    # Set log directory
    _LOG_DIR = settings.log_dir_path
    _LOG_DIR.mkdir(exist_ok=True, parents=True)

    # Get or create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console Handler (use stderr to avoid conflicts with STDIO transport)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_formatter = logging.Formatter(_LOG_FORMAT_SIMPLE, datefmt=_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File Handler with Rotation (if enabled)
    if enable_file:
        log_file = _LOG_DIR / f"{name}.log"

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # Capture all levels to file
        file_formatter = logging.Formatter(_LOG_FORMAT_DETAILED, datefmt=_DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Separate Error File Handler (uses same rotation settings)
        error_log_file = _LOG_DIR / f"{name}.error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(_LOG_FORMAT_DETAILED, datefmt=_DATE_FORMAT)
        error_handler.setFormatter(error_formatter)
        logger.addHandler(error_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    # Store as root logger
    _ROOT_LOGGER = logger

    # Print startup banner and config summary
    if show_banner:
        print_banner()
        print_config_summary(settings)

    return logger


def get_logger(name: str, log_level: str | None = None) -> logging.Logger:
    """Get a configured logger instance for a module.

    Gets or creates a logger with consistent formatting. Call setup_logging()
    once at startup for full configuration.

    Args:
        name: Logger name (typically module name like 'mcp_tools_search').
        log_level: Optional override for logger level (DEBUG, INFO, WARNING, ERROR).

    Returns:
        Configured logger instance ready for use.

    Example:
        from utils.logger import get_logger

        logger = get_logger("mcp_tools_bookings")
        logger.info("Processing booking request")
        logger.debug("Detailed debug information")
        logger.error("Error occurred", exc_info=True)
    """
    logger = logging.getLogger(name)

    # Set logger-specific level if provided or from module config
    if log_level:
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    elif name in _MODULE_LEVELS:
        logger.setLevel(_MODULE_LEVELS[name])

    # If no handlers and root logger exists, inherit from it
    if not logger.handlers and _ROOT_LOGGER:
        for handler in _ROOT_LOGGER.handlers:
            logger.addHandler(handler)
        logger.propagate = False

    return logger


def get_logs_directory() -> Path | None:
    """Get the logs directory path.

    Returns:
        Path object pointing to logs directory, or None if not configured.
    """
    return _LOG_DIR


def log_context(
    operation: str,
    session_id: str | None = None,
    user_id: str | None = None,
    **kwargs,
) -> str:
    """Format a log context string with metadata.

    Helper for structured logging with contextual information.

    Args:
        operation: Operation name (e.g., "search_products", "create_booking").
        session_id: Session ID if applicable.
        user_id: User ID if applicable.
        **kwargs: Additional context key-value pairs.

    Returns:
        Formatted context string for logging.

    Example:
        from utils.logger import log_context, get_logger

        logger = get_logger("mcp_tools_search")
        ctx = log_context(
            "search_products",
            session_id="abc123",
            query="laptop",
            results=5,
        )
        logger.info(f"Completed: {ctx}")
        # Output: Completed: [abc123] search_products (query=laptop, results=5)
    """
    context_parts = [operation]

    if session_id:
        context_parts.insert(0, f"[{session_id}]")

    if user_id:
        context_parts.append(f"user={user_id}")

    context = " ".join(context_parts)

    if kwargs:
        extra = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        context = f"{context} ({extra})"

    return context
