# REQ-1: OTP (One-Time Password) Verification System

## Overview

| Field | Value |
|-------|-------|
| **Requirement ID** | REQ-1 |
| **Title** | OTP Verification System |
| **Version** | 1.0.0 |
| **Status** | Implemented |
| **Priority** | High |
| **Created** | 2025-12-07 |
| **Author** | Odiseo Team |

## Description

Implement a secure One-Time Password (OTP) system that allows agents to generate and verify OTP codes for user authentication workflows such as email verification, password reset, and identity confirmation.

## Requirements

### Functional Requirements

#### FR-1: OTP Generation
- **FR-1.1**: The system SHALL generate cryptographically secure OTP codes using Python's `secrets` module.
- **FR-1.2**: OTP codes SHALL be numeric only (digits 0-9) for easy user input.
- **FR-1.3**: OTP code length SHALL be configurable (4-8 digits, default: 6).
- **FR-1.4**: Each OTP SHALL have a configurable expiration time (1-60 minutes, default: 10).
- **FR-1.5**: The system SHALL invalidate all previous pending OTPs for the same email when generating a new one.

#### FR-2: OTP Storage
- **FR-2.1**: OTP codes SHALL NEVER be stored in plaintext.
- **FR-2.2**: OTP codes SHALL be hashed using SHA-256 (or SHA-384/512) before storage.
- **FR-2.3**: The database SHALL store: email, hashed_code, purpose, created_at, expires_at, attempts, max_attempts, is_used.
- **FR-2.4**: JSONB metadata field SHALL support extensibility (IP, user agent, etc.).

#### FR-3: OTP Verification
- **FR-3.1**: Verification SHALL use timing-attack resistant comparison (`secrets.compare_digest`).
- **FR-3.2**: Attempt counter SHALL be incremented BEFORE hash comparison (fail-safe).
- **FR-3.3**: OTP SHALL be marked as used immediately upon successful verification.
- **FR-3.4**: Verification SHALL fail if OTP is expired, already used, or max attempts exceeded.

#### FR-4: Email Delivery
- **FR-4.1**: OTP codes SHALL be sent via the integrated email service.
- **FR-4.2**: Email SHALL use the `otp_verification` template with dynamic expiry time.
- **FR-4.3**: Email sending SHALL be fire-and-forget (non-blocking).

#### FR-5: Rate Limiting
- **FR-5.1**: Cooldown period SHALL prevent rapid OTP requests (default: 60 seconds).
- **FR-5.2**: Maximum of 5 OTP generations per minute per email address.
- **FR-5.3**: Maximum verification attempts per OTP (default: 3).

### Non-Functional Requirements

#### NFR-1: Security
- **NFR-1.1**: Use CSPRNG (Cryptographically Secure Pseudo-Random Number Generator).
- **NFR-1.2**: Prevent timing attacks in verification.
- **NFR-1.3**: Prevent brute-force attacks via attempt limiting.
- **NFR-1.4**: Prevent replay attacks via single-use enforcement.
- **NFR-1.5**: Never expose OTP codes in logs or API responses.

#### NFR-2: Performance
- **NFR-2.1**: OTP generation: < 200ms (including email queueing).
- **NFR-2.2**: OTP verification: < 100ms.
- **NFR-2.3**: Database queries SHALL use indexes for email + purpose lookups.

#### NFR-3: Reliability
- **NFR-3.1**: OTP system SHALL be configurable via environment variables.
- **NFR-3.2**: System SHALL gracefully handle email service failures.
- **NFR-3.3**: All operations SHALL be atomic (no partial states).

#### NFR-4: Maintainability
- **NFR-4.1**: Code SHALL follow Repository pattern for database operations.
- **NFR-4.2**: Business logic SHALL be separated from MCP handlers.
- **NFR-4.3**: Full type hints coverage (Python 3.10+).

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Server                                │
├─────────────────────────────────────────────────────────────────┤
│  mcp_handlers/otp_handler.py                                    │
│  ├── generate_otp()    # MCP Tool: Generate and send OTP        │
│  └── verify_otp()      # MCP Tool: Verify OTP code              │
├─────────────────────────────────────────────────────────────────┤
│  tools/otp/                                                      │
│  ├── generator.py      # OTPGenerator, OTPCode dataclass        │
│  ├── storage.py        # OTPStorage (Repository pattern)        │
│  └── validator.py      # OTPValidator, timing-safe comparison   │
├─────────────────────────────────────────────────────────────────┤
│  Database: PostgreSQL                                            │
│  └── test.otp_codes    # OTP storage table                      │
├─────────────────────────────────────────────────────────────────┤
│  External: Email Service                                         │
│  └── POST /emails      # Fire-and-forget OTP delivery           │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Agent calls generate_otp(email, recipient_name, purpose)
   │
2. ├── Validate email format
   ├── Check cooldown period
   ├── Rate limit check
   ├── Invalidate previous OTPs
   │
3. ├── Generate secure code (secrets.randbelow)
   ├── Hash code (SHA-256)
   ├── Store in database
   │
4. ├── Queue email via email service
   │
5. └── Return confirmation (WITHOUT code)

---

1. Agent calls verify_otp(email, code, purpose)
   │
2. ├── Retrieve pending OTP from database
   ├── Check expiration
   ├── Check attempt limit
   │
3. ├── Increment attempts (BEFORE comparison)
   ├── Hash provided code
   ├── Timing-safe comparison
   │
4. ├── If match: Mark as verified
   │   If no match: Return failure with remaining attempts
   │
5. └── Return verification result
```

## Database Schema

### Table: otp_codes

```sql
CREATE TABLE test.otp_codes (
    id              BIGSERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL,
    hashed_code     VARCHAR(128) NOT NULL,
    purpose         VARCHAR(50) NOT NULL DEFAULT 'email_verification',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    verified_at     TIMESTAMPTZ,
    attempts        INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 3,
    is_used         BOOLEAN NOT NULL DEFAULT FALSE,
    metadata        JSONB
);

-- Indexes
CREATE INDEX idx_otp_codes_email_purpose ON test.otp_codes (email, purpose);
CREATE INDEX idx_otp_codes_pending ON test.otp_codes (email, purpose, is_used, expires_at)
    WHERE is_used = FALSE;
```

## Configuration

### Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OTP_ENABLED` | bool | `true` | Enable/disable OTP system |
| `OTP_CODE_LENGTH` | int | `6` | OTP code length (4-8) |
| `OTP_EXPIRY_MINUTES` | int | `10` | Expiration time (1-60) |
| `OTP_MAX_ATTEMPTS` | int | `3` | Max verification attempts (1-10) |
| `OTP_COOLDOWN_SECONDS` | int | `60` | Cooldown between requests (30-300) |
| `OTP_HASH_ALGORITHM` | str | `sha256` | Hash algorithm |

## API

### MCP Tools

#### generate_otp

```python
async def generate_otp(
    ctx: Context,
    email: str,           # Recipient email address
    recipient_name: str,  # Name for email personalization
    purpose: str = "email_verification"  # OTP purpose
) -> dict:
    """
    Returns:
        {
            "success": True,
            "message": "Verification code sent to j***@example.com",
            "email": "j***@example.com",  # Masked
            "expires_in_minutes": 10,
            "otp_id": 123
        }

    Note: OTP code is NEVER returned - only sent via email.
    """
```

#### verify_otp

```python
async def verify_otp(
    ctx: Context,
    email: str,   # Email that received OTP
    code: str,    # OTP code to verify
    purpose: str = "email_verification"
) -> dict:
    """
    Returns (success):
        {
            "success": True,
            "status": "success",
            "message": "Verification successful."
        }

    Returns (failure):
        {
            "success": False,
            "status": "invalid_code",  # or "expired", "max_attempts", "not_found"
            "message": "Invalid verification code. 2 attempts remaining.",
            "attempts_remaining": 2
        }
    """
```

## Security Considerations

### Implemented Protections

| Threat | Mitigation |
|--------|------------|
| Brute-force attack | Max attempts limit (3), rate limiting |
| Timing attack | `secrets.compare_digest()` for constant-time comparison |
| Replay attack | Single-use enforcement (`is_used` flag) |
| Code exposure | Hash storage (SHA-256), masked responses |
| Enumeration | Generic error messages |
| Spam/abuse | Cooldown period, rate limiting |

### Security Audit Checklist

- [x] OTP codes generated using CSPRNG (`secrets` module)
- [x] Codes hashed before storage (never plaintext)
- [x] Timing-safe hash comparison
- [x] Attempt counter incremented before comparison
- [x] OTP marked as used atomically on success
- [x] Expiration enforced at database level
- [x] Rate limiting per email address
- [x] No OTP codes in logs or responses

## Testing

### Test Cases

| ID | Description | Expected Result |
|----|-------------|-----------------|
| TC-1 | Generate OTP for valid email | OTP stored, email queued, confirmation returned |
| TC-2 | Generate OTP during cooldown | Error with remaining cooldown time |
| TC-3 | Verify with correct code | Success, OTP marked as used |
| TC-4 | Verify with wrong code | Failure, attempts decremented |
| TC-5 | Verify expired OTP | Failure with "expired" status |
| TC-6 | Verify already used OTP | Failure with "not_found" status |
| TC-7 | Exceed max attempts | Failure with "max_attempts" status |
| TC-8 | Reuse verified OTP | Failure (no pending OTP found) |

## References

- [Python secrets module](https://docs.python.org/3/library/secrets.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [RFC 4226 - HOTP](https://tools.ietf.org/html/rfc4226)
- [RFC 6238 - TOTP](https://tools.ietf.org/html/rfc6238)

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-12-07 | Odiseo Team | Initial implementation |
