"""
Official MCP-Compliant Server Implementation
Follows Anthropic's official MCP Python SDK specification exactly.
Uses official protocol version, capabilities, and types from mcp.types module.
"""

from mcp.server.fastmcp import FastMCP
from mcp.types import DEFAULT_NEGOTIATED_VERSION, LATEST_PROTOCOL_VERSION

from config import settings
from mcp_handlers import (
    booking_handlers,
    otp_handler,
    prompt_handlers,
    resource_handlers,
    sales_handlers,
)
from utils.db_async import fetchall_async, fetchone_async
from utils.logger import cleanup_banner_flag, setup_logging
from utils.validation import validate_schema_name

# Cleanup banner flag from previous runs (for fresh banner on restart)
cleanup_banner_flag()

# Setup logger with banner and config summary
logger = setup_logging("mcp_server", settings=settings)

# Create MCP server with official configuration
mcp = FastMCP(
    name="Odiseo MCP Server",
    instructions=(
        "Production-ready MCP server with tools across three domains: "
        "(1) Product Search - semantic search with Gemini embeddings, fuzzy matching, SKU lookup; "
        "(2) Booking Management - appointments with Google Calendar integration; "
        "(3) OTP Verification - secure one-time password generation and verification via email."
    ),
    debug=settings.DEBUG_MODE,  # Configurable via DEBUG_MODE env var
    log_level=settings.LOG_LEVEL,
    stateless_http=True,  # Enable stateless HTTP for proper remote client support
)

# Initialize handlers with MCP instance
sales_handlers.init_sales_handlers(mcp)  # Register sales/product tools
booking_handlers.init_booking_handlers(mcp)  # Register booking tools
otp_handler.init_otp_handlers(mcp)  # Register OTP tools
resource_handlers.init_resource_handlers(mcp)
prompt_handlers.init_prompt_handlers(mcp)

# Validate tool registries (auto-discovery system)
try:
    from utils.tool_discovery_validator import (
        log_tool_discovery_status,
        validate_tool_registries,
    )

    validation = validate_tool_registries(
        mcp,
        booking_registry=booking_handlers.booking_tool_registry,
        sales_registry=sales_handlers.sales_tool_registry,
        pageable_registry=sales_handlers.pageable_tool_registry,
        otp_registry=otp_handler.otp_tool_registry,
    )
    log_tool_discovery_status(validation)

    if not validation.is_valid:
        logger.error("Tool discovery validation failed. See errors above.")
        logger.error("Some tools may not be available to agents.")
except Exception as e:
    logger.warning(f"Tool discovery validation skipped: {e}")
    logger.warning("This is not critical, but tool discovery may not work optimally.")


# ============================================================================
# Database Initialization
# ============================================================================
# Note: Database pool is lazily initialized on first request via get_pool()
# This avoids event loop conflicts with uvicorn's async runtime
logger.info("Database pool will be initialized on first request (lazy initialization)")


# ============================================================================
# Main Entry Point - Official MCP Configuration
# ============================================================================

if __name__ == "__main__":
    import sys

    import uvicorn

    # Configuration based on official MCP SDK patterns
    # Supported transports:
    # - stdio: For local CLI usage
    # - streamable-http: For remote HTTP access (default, recommended)
    transport = "streamable-http"
    host = "0.0.0.0"  # Listen on all interfaces for remote access
    port = settings.MCP_PORT  # Configurable via MCP_PORT env var (default: 8009)

    # Parse command line arguments
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--stdio":
            transport = "stdio"
        elif arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        elif arg == "--host" and i + 1 < len(args):
            host = args[i + 1]

    logger.info(f"Starting MCP server with transport: {transport}")
    logger.info(
        f"Protocol version support: {LATEST_PROTOCOL_VERSION} (latest), {DEFAULT_NEGOTIATED_VERSION} (default)"
    )

    if transport == "stdio":
        # For stdio transport (local CLI usage)
        logger.info("Running in stdio mode for local CLI clients")
        mcp.run(transport="stdio")
    else:
        # For streamable-http transport (remote access)
        logger.info(f"MCP server accessible at http://{host}:{port}/mcp")
        logger.info("Server supports all official MCP capabilities:")
        logger.info("  - Tools (with Context support)")
        logger.info("  - Resources (URI-based access)")
        logger.info("  - Prompts (AI assistant templates)")
        logger.info("  - Logging (structured logging)")
        logger.info("  - Progress reporting")
        logger.info("  - Session management")

        # Get the ASGI app from FastMCP
        app = mcp.streamable_http_app()

        # Add health check endpoint using Starlette routing
        import time

        from starlette.responses import JSONResponse
        from starlette.routing import Route

        from config import settings

        async def health_check(request):
            """Database health check endpoint (async)."""
            start_time = time.time()
            health_status = {"status": "healthy", "timestamp": time.time(), "checks": {}}

            # Check database connection
            try:
                # Validate schema name to prevent SQL injection
                validate_schema_name(settings.SCHEMA_NAME)

                # Count products
                result = await fetchone_async(
                    f"SELECT COUNT(*) as count FROM {settings.SCHEMA_NAME}.products"
                )
                product_count = result["count"] if result else 0

                # Count bookings/appointments
                booking_result = await fetchone_async(
                    f"SELECT COUNT(*) as count FROM {settings.SCHEMA_NAME}.appointments"
                )
                booking_count = booking_result["count"] if booking_result else 0

                # Check extensions
                extensions = await fetchall_async(
                    "SELECT extname FROM pg_extension WHERE extname IN ('pg_trgm', 'unaccent', 'vector')"
                )
                ext_names = [e["extname"] for e in extensions]

                # Check normalize_text function
                try:
                    await fetchone_async(f"SELECT {settings.SCHEMA_NAME}.normalize_text('test')")
                    has_normalize = True
                except Exception:
                    has_normalize = False

                db_response_time = (time.time() - start_time) * 1000

                health_status["checks"]["database"] = {
                    "status": "healthy",
                    "response_time_ms": round(db_response_time, 2),
                    "product_count": product_count,
                    "booking_count": booking_count,
                    "schema": settings.SCHEMA_NAME,
                    "extensions": ext_names,
                    "normalize_text_available": has_normalize,
                }

                missing_extensions = {"pg_trgm", "unaccent", "vector"} - set(ext_names)
                if missing_extensions:
                    health_status["checks"]["database"]["status"] = "degraded"
                    health_status["checks"]["database"]["warning"] = (
                        f"Missing extensions: {list(missing_extensions)}"
                    )
                    health_status["status"] = "degraded"

                if not has_normalize:
                    health_status["checks"]["database"]["status"] = "degraded"
                    health_status["checks"]["database"]["warning"] = (
                        "normalize_text function not available"
                    )
                    health_status["status"] = "degraded"

            except Exception as e:
                health_status["status"] = "unhealthy"
                health_status["checks"]["database"] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "response_time_ms": round((time.time() - start_time) * 1000, 2),
                }

            # Set HTTP status code based on health
            status_code = 200 if health_status["status"] == "healthy" else 503

            return JSONResponse(content=health_status, status_code=status_code)

        # Add the route to the existing Starlette app
        health_route = Route("/health", health_check)
        app.routes.append(health_route)

        logger.info(f"Health check endpoint available at http://{host}:{port}/health")

        # Run with uvicorn using official configuration
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
