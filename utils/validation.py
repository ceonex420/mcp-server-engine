"""Centralized Validation Utilities.

Provides unified validation functions for common data types.
Consolidates validation logic to avoid duplication across modules.

Author: Odiseo Team
Created: 2025-12-05
Version: 1.1.0
"""

import re

# RFC 5321 limits
MAX_EMAIL_LENGTH = 254  # Total email length
MAX_LOCAL_PART_LENGTH = 64  # Before @ symbol
MAX_DOMAIN_LENGTH = 255  # After @ symbol


def validate_email(email: str) -> tuple[bool, str]:
    """Validate email address format using RFC 5322 pattern and RFC 5321 limits.

    Performs comprehensive email validation including:
    - Length validation per RFC 5321 (max 254 chars total)
    - Local part length (max 64 chars before @)
    - Domain length (max 255 chars after @)
    - Basic RFC 5322 pattern matching
    - Common TLD typo detection (.comm, .coom, etc.)

    Args:
        email: Email address to validate.

    Returns:
        Tuple of (is_valid: bool, error_message: str).
        If valid: (True, "")
        If invalid: (False, "descriptive error message")

    Example:
        >>> is_valid, msg = validate_email("user@example.com")
        >>> print(is_valid)
        True

        >>> is_valid, msg = validate_email("user@example.comm")  # Typo!
        >>> print(is_valid, msg)
        False Suspected TLD typo in email: user@example.comm (.comm instead of .com?)
    """
    if not email or not isinstance(email, str):
        return False, "Email must be a non-empty string"

    email = email.strip()

    # Check total length (RFC 5321)
    if len(email) > MAX_EMAIL_LENGTH:
        return False, f"Email too long: {len(email)} chars (max {MAX_EMAIL_LENGTH})"

    # Check for @ symbol
    if "@" not in email:
        return False, f"Invalid email format (missing @): {email}"

    local_part, domain = email.rsplit("@", 1)

    # Check local part length (RFC 5321)
    if len(local_part) > MAX_LOCAL_PART_LENGTH:
        return (
            False,
            f"Email local part too long: {len(local_part)} chars (max {MAX_LOCAL_PART_LENGTH})",
        )

    # Check domain length (RFC 5321)
    if len(domain) > MAX_DOMAIN_LENGTH:
        return False, f"Email domain too long: {len(domain)} chars (max {MAX_DOMAIN_LENGTH})"

    # Basic RFC 5322 pattern (simplified for practical use)
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    if not re.match(pattern, email):
        return False, f"Invalid email format: {email}"

    # Check for common typos (double letters in TLD)
    if re.search(r"\.c+o+m+m+$", email, re.IGNORECASE):
        return False, f"Suspected TLD typo in email: {email} (.comm instead of .com?)"

    if re.search(r"\.c+o+o+m+$", email, re.IGNORECASE):
        return False, f"Suspected TLD typo in email: {email} (.coom instead of .com?)"

    return True, ""


def validate_schema_name(schema_name: str) -> None:
    """Validate PostgreSQL schema name to prevent SQL injection attacks.

    PostgreSQL schema names must be valid identifiers: alphanumeric characters,
    underscores, and cannot start with a digit. This function ensures the schema
    name follows these rules before it's used in SQL queries.

    Args:
        schema_name: The schema name to validate

    Raises:
        ValueError: If schema name is invalid or potentially dangerous

    Example:
        >>> validate_schema_name("public")  # OK
        >>> validate_schema_name("my_schema")  # OK
        >>> validate_schema_name("'; DROP TABLE users; --")  # Raises ValueError
    """
    # PostgreSQL identifier rules: max 63 chars, alphanumeric + underscore, can't start with digit
    if not isinstance(schema_name, str) or len(schema_name) == 0:
        raise ValueError("Schema name must be a non-empty string")

    if len(schema_name) > 63:
        raise ValueError("Schema name exceeds PostgreSQL identifier length limit (63 chars)")

    # Only allow alphanumeric characters and underscores, must not start with digit
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema_name):
        raise ValueError(
            f"Invalid schema name '{schema_name}': must start with letter/underscore "
            "and contain only alphanumeric characters and underscores"
        )
