"""Configuration settings for MCP Server using Pydantic BaseSettings v2.

This module uses Pydantic BaseSettings to manage configuration from environment
variables and .env files, following best practices for 2025.

Migration from dataclasses to Pydantic v2 for:
- Type validation and conversion
- Better .env file handling
- Field validators
- Computed properties
"""

from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for MCP Server.

    All settings can be overridden via environment variables or .env file.
    Type validation and conversion is handled automatically by Pydantic.
    """

    # ============================================================================
    # Pydantic Configuration
    # ============================================================================
    model_config = SettingsConfigDict(
        # Path to .env file (relative to project root)
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,  # Allow DATABASE_URL or database_url
        extra="ignore",  # Ignore extra fields in .env
        validate_default=True,  # Validate default values on instantiation
    )

    # ============================================================================
    # Database Configuration
    # ============================================================================
    DATABASE_URL: str = Field(
        ...,  # Required field
        description="PostgreSQL connection URL",
        examples=["postgresql://user:pass@localhost:5434/mcpdb"],
    )

    SCHEMA_NAME: str = Field(
        default="test",
        description="PostgreSQL schema name to use",
    )

    # ============================================================================
    # Google GenAI Configuration
    # ============================================================================
    USE_ADC: bool = Field(
        default=False,
        description="Use Application Default Credentials for Gemini API (recommended for Cloud Run)",
    )

    GOOGLE_API_KEY: str = Field(
        default="",
        description="Google API key for Gemini AI embeddings (not required when USE_ADC=true)",
    )

    EMBEDDING_MODEL: str = Field(
        default="gemini-embedding-001",
        description="Gemini embedding model to use",
    )

    EMBEDDING_DIMENSION: int = Field(
        default=1536,
        ge=256,
        le=3072,
        description="Embedding vector dimension (gemini-embedding-001 supports up to 3072)",
    )

    # ============================================================================
    # Data Configuration
    # ============================================================================
    BATCH_SIZE: int = Field(
        default=8,
        gt=0,
        description="Batch size for processing operations",
    )

    PGVECTOR_IVF_LISTS: int = Field(
        default=100,
        gt=0,
        description="Number of IVF lists for pgvector (more = faster search, more memory)",
    )

    # ============================================================================
    # Logging Configuration
    # ============================================================================
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    LOG_MAX_SIZE_MB: int = Field(
        default=10,
        gt=0,
        description="Maximum log file size in megabytes",
    )

    LOG_BACKUP_COUNT: int = Field(
        default=5,
        gt=0,
        description="Number of backup log files to keep",
    )

    LOG_DIR: str = Field(
        default="logs",
        description="Directory for log files (relative to mcp_server/)",
    )

    # ============================================================================
    # Server Configuration
    # ============================================================================
    DEBUG_MODE: bool = Field(
        default=False,
        description="Enable debug mode for MCP server (disable in production)",
    )

    MCP_PORT: int = Field(
        default=8009,
        ge=1024,
        le=65535,
        description="Port for MCP server HTTP endpoint",
    )

    MAX_CONCURRENT_REQUESTS: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum concurrent requests per worker (concurrency limit)",
    )

    # ============================================================================
    # Email Service Integration (HTTP Client)
    # ============================================================================
    EMAIL_SERVICE_ENABLED: bool = Field(
        default=True,
        description="Enable HTTP integration with email service",
    )

    EMAIL_SERVICE_BASE_URL: str = Field(
        default="http://localhost:8001",
        description="Base URL for email service (e.g., http://localhost:8001)",
    )

    EMAIL_SERVICE_API_KEY: str = Field(
        default="",
        description="API key for email service authentication (empty = no auth)",
    )

    EMAIL_SERVICE_TIMEOUT_SECONDS: float = Field(
        default=5.0,
        gt=0,
        le=30,
        description="HTTP timeout for email service requests (seconds)",
    )

    EMAIL_SERVICE_MAX_RETRIES: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retry attempts for transient failures",
    )

    EMAIL_SERVICE_RETRY_DELAY_SECONDS: float = Field(
        default=0.5,
        ge=0.1,
        le=5,
        description="Initial delay between retries (exponential backoff)",
    )

    EMAIL_SERVICE_CIRCUIT_BREAKER_THRESHOLD: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of failures before circuit breaker opens",
    )

    EMAIL_SERVICE_CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Time before circuit breaker allows retry (seconds)",
    )

    # ============================================================================
    # Google Calendar API Configuration (Booking System)
    # ============================================================================
    GOOGLE_CALENDAR_ENABLED: bool = Field(
        default=False,
        description="Enable Google Calendar integration for bookings",
    )

    GOOGLE_CALENDAR_CREDENTIALS_PATH: str = Field(
        default="credentials/service-account.json",
        description="Path to Google service account JSON credentials",
    )

    GOOGLE_CALENDAR_ID: str = Field(
        default="primary",
        description="Google Calendar ID for bookings (default: primary)",
    )

    GOOGLE_CALENDAR_TIMEZONE: str = Field(
        default="America/Costa_Rica",
        description="Timezone for Google Calendar events and availability checks (default: America/Costa_Rica)",
    )

    # ============================================================================
    # Booking Configuration
    # ============================================================================
    BOOKING_DEFAULT_DURATION_MINUTES: int = Field(
        default=60,
        gt=0,
        le=480,  # Max 8 hours
        description="Default appointment duration in minutes",
    )

    BOOKING_SLOT_INTERVAL_MINUTES: int = Field(
        default=30,
        gt=0,
        description="Time slot interval for availability checks",
    )

    BOOKING_ADVANCE_BOOKING_DAYS: int = Field(
        default=30,
        gt=0,
        description="Maximum days in advance for booking",
    )

    BOOKING_MIN_ADVANCE_MINUTES: int = Field(
        default=60,
        ge=0,
        le=1440,  # Max 24 hours = 1440 minutes
        description="Minimum minutes in advance required for booking (default: 60 = 1 hour)",
    )

    BOOKING_MAX_DAILY_APPOINTMENTS: int = Field(
        default=10,
        gt=0,
        description="Maximum appointments per day",
    )

    # ============================================================================
    # Booking Input Parser Configuration (Confidence Thresholds)
    # ============================================================================
    BOOKING_CHOICE_CONFIDENCE_THRESHOLD: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for booking choice classification (reschedule/cancel)",
    )

    BOOKING_PARTIAL_MATCH_CONFIDENCE: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence score for partial word matches in booking input",
    )

    BOOKING_MIN_KEYWORD_LENGTH: int = Field(
        default=3,
        gt=0,
        description="Minimum string length for substring matching in booking keywords",
    )

    BOOKING_FUZZY_MATCH_THRESHOLD: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="SequenceMatcher threshold for fuzzy matching in booking input",
    )

    BOOKING_CONFIRMATION_THRESHOLD: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for yes/no confirmation in booking context",
    )

    BOOKING_CLARIFICATION_THRESHOLD: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence threshold below which to ask for clarification",
    )

    BOOKING_EMAIL_QUEUE_PRIORITY: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Email queue priority for booking notifications (1=lowest, 10=highest)",
    )

    # ============================================================================
    # OTP (One-Time Password) Configuration
    # ============================================================================
    OTP_ENABLED: bool = Field(
        default=True,
        description="Enable OTP generation and verification tools",
    )

    OTP_CODE_LENGTH: int = Field(
        default=6,
        ge=4,
        le=8,
        description="Length of generated OTP codes (4-8 digits)",
    )

    OTP_EXPIRY_MINUTES: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Minutes until OTP expires (1-60 minutes)",
    )

    OTP_MAX_ATTEMPTS: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum verification attempts before OTP is invalidated",
    )

    OTP_COOLDOWN_SECONDS: int = Field(
        default=60,
        ge=30,
        le=300,
        description="Minimum seconds between OTP generation for same email (rate limiting)",
    )

    OTP_HASH_ALGORITHM: str = Field(
        default="sha256",
        description="Hash algorithm for storing OTP codes (sha256, sha384, sha512)",
    )

    OTP_PURPOSE_VERIFICATION: str = Field(
        default="email_verification",
        description="Default purpose for OTP verification",
    )

    # ============================================================================
    # Field Validators
    # ============================================================================
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}, got: {v}")
        return v.upper()

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate DATABASE_URL format."""
        if not v:
            raise ValueError("DATABASE_URL cannot be empty")
        if not v.startswith("postgresql://"):
            raise ValueError("DATABASE_URL must start with 'postgresql://'")
        return v

    @field_validator("GOOGLE_API_KEY")
    @classmethod
    def validate_google_api_key(cls, v: str) -> str:
        """Validate GOOGLE_API_KEY format (allow empty when USE_ADC=true)."""
        # Allow empty string - validation with USE_ADC happens in model_validator
        return v.strip() if v else ""

    @field_validator("OTP_HASH_ALGORITHM")
    @classmethod
    def validate_otp_hash_algorithm(cls, v: str) -> str:
        """Validate OTP hash algorithm is supported."""
        allowed = {"sha256", "sha384", "sha512"}
        if v.lower() not in allowed:
            raise ValueError(f"OTP_HASH_ALGORITHM must be one of {allowed}, got: {v}")
        return v.lower()

    @model_validator(mode="after")
    def validate_configuration_consistency(self) -> Self:
        """Validate that configuration values are consistent and compatible.

        This method ensures cross-field configuration consistency to prevent
        runtime errors from conflicting or invalid setting combinations.

        Returns:
            Settings: The validated settings instance

        Raises:
            ValueError: If configuration conflicts are detected
        """
        # Authentication: Either USE_ADC or GOOGLE_API_KEY must be configured
        if not self.USE_ADC and not self.GOOGLE_API_KEY:
            raise ValueError(
                "Authentication not configured. Set USE_ADC=true for Cloud Run "
                "or provide GOOGLE_API_KEY for local development."
            )

        # Booking configuration: Duration must be >= Interval
        if self.BOOKING_DEFAULT_DURATION_MINUTES < self.BOOKING_SLOT_INTERVAL_MINUTES:
            raise ValueError(
                f"BOOKING_DEFAULT_DURATION_MINUTES ({self.BOOKING_DEFAULT_DURATION_MINUTES} min) "
                f"must be >= BOOKING_SLOT_INTERVAL_MINUTES ({self.BOOKING_SLOT_INTERVAL_MINUTES} min). "
                f"Otherwise, slot generation produces overlapping slots."
            )

        return self

    # ============================================================================
    # Computed Properties
    # ============================================================================
    @property
    def log_max_bytes(self) -> int:
        """Get max log file size in bytes."""
        return self.LOG_MAX_SIZE_MB * 1024 * 1024

    @property
    def log_dir_path(self) -> Path:
        """Get absolute path to logs directory."""
        return Path(__file__).parent.parent / self.LOG_DIR

    @property
    def google_calendar_credentials_path(self) -> Path:
        """Get absolute path to Google Calendar service account credentials.

        Resolves relative paths to project root, handles absolute paths as-is.
        This ensures the credentials file can be found regardless of MCP server
        working directory.

        Returns:
            Absolute Path to credentials file
        """
        creds_path = Path(self.GOOGLE_CALENDAR_CREDENTIALS_PATH)
        if not creds_path.is_absolute():
            # Resolve relative to project root
            # Path(__file__) = /Users/og/Documents/Claude/Projects/Odiseo live/Odiseo/mcp_server/config/settings.py
            # .parent = /Users/og/Documents/Claude/Projects/Odiseo live/Odiseo/mcp_server/config
            # .parent.parent = /Users/og/Documents/Claude/Projects/Odiseo live/Odiseo/mcp_server
            # .parent.parent.parent = /Users/og/Documents/Claude/Projects/Odiseo live/Odiseo (project root)
            return Path(__file__).parent.parent.parent / creds_path
        return creds_path

    # ============================================================================
    # Helper Methods
    # ============================================================================
    def validate_settings(self) -> bool:
        """Validate all required settings are present.

        Returns:
            bool: True if all settings are valid

        Raises:
            ValueError: If any setting is invalid
        """
        # Pydantic automatically validates on initialization
        # This method is kept for backward compatibility
        return True

    def get_database_config(self) -> dict[str, str]:
        """Get database configuration as dictionary.

        Returns:
            dict: Database configuration parameters
        """
        return {
            "database_url": self.DATABASE_URL,
            "schema_name": self.SCHEMA_NAME,
        }

    def get_embedding_config(self) -> dict[str, str]:
        """Get embedding configuration as dictionary.

        Returns:
            dict: Embedding configuration parameters
        """
        return {
            "api_key": self.GOOGLE_API_KEY,
            "model": self.EMBEDDING_MODEL,
        }

    def get_logging_config(self) -> dict[str, str | int]:
        """Get logging configuration as dictionary.

        Returns:
            dict: Logging configuration parameters
        """
        return {
            "level": self.LOG_LEVEL,
            "max_size_mb": self.LOG_MAX_SIZE_MB,
            "backup_count": self.LOG_BACKUP_COUNT,
            "log_dir": self.LOG_DIR,
        }

    def get_calendar_config(self) -> dict[str, str | bool]:
        """Get Google Calendar configuration as dictionary.

        Returns:
            dict: Google Calendar configuration parameters
        """
        return {
            "enabled": self.GOOGLE_CALENDAR_ENABLED,
            "credentials_path": self.GOOGLE_CALENDAR_CREDENTIALS_PATH,
            "calendar_id": self.GOOGLE_CALENDAR_ID,
            "timezone": self.GOOGLE_CALENDAR_TIMEZONE,
        }

    def get_booking_config(self) -> dict[str, int]:
        """Get booking configuration as dictionary.

        Returns:
            dict: Booking configuration parameters
        """
        return {
            "default_duration_minutes": self.BOOKING_DEFAULT_DURATION_MINUTES,
            "slot_interval_minutes": self.BOOKING_SLOT_INTERVAL_MINUTES,
            "advance_booking_days": self.BOOKING_ADVANCE_BOOKING_DAYS,
            "min_advance_minutes": self.BOOKING_MIN_ADVANCE_MINUTES,
            "max_daily_appointments": self.BOOKING_MAX_DAILY_APPOINTMENTS,
        }

    def get_email_service_config(self) -> dict[str, str | bool | int | float]:
        """Get email service HTTP client configuration.

        Returns:
            dict: Email service configuration parameters
        """
        return {
            "enabled": self.EMAIL_SERVICE_ENABLED,
            "base_url": self.EMAIL_SERVICE_BASE_URL,
            "api_key": self.EMAIL_SERVICE_API_KEY,
            "timeout_seconds": self.EMAIL_SERVICE_TIMEOUT_SECONDS,
            "max_retries": self.EMAIL_SERVICE_MAX_RETRIES,
            "retry_delay_seconds": self.EMAIL_SERVICE_RETRY_DELAY_SECONDS,
            "circuit_breaker_threshold": self.EMAIL_SERVICE_CIRCUIT_BREAKER_THRESHOLD,
            "circuit_breaker_timeout": self.EMAIL_SERVICE_CIRCUIT_BREAKER_TIMEOUT_SECONDS,
        }

    def get_otp_config(self) -> dict[str, str | bool | int]:
        """Get OTP configuration as dictionary.

        Returns:
            dict: OTP configuration parameters
        """
        return {
            "enabled": self.OTP_ENABLED,
            "code_length": self.OTP_CODE_LENGTH,
            "expiry_minutes": self.OTP_EXPIRY_MINUTES,
            "max_attempts": self.OTP_MAX_ATTEMPTS,
            "cooldown_seconds": self.OTP_COOLDOWN_SECONDS,
            "hash_algorithm": self.OTP_HASH_ALGORITHM,
            "default_purpose": self.OTP_PURPOSE_VERIFICATION,
        }


# ============================================================================
# Global Settings Instance (Singleton)
# ============================================================================
settings = Settings()
