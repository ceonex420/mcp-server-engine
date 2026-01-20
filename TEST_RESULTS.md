## Production Test Scenarios

**Test Date:** 2026-01-20 13:06:17 UTC
**Service URL:** https://mcp-server-4k3haexkga-uc.a.run.app
**Results:** 24/24 passed (0 failed)

### Health

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| health: GET /health | ✅ PASS | 334.19ms | DB: 45 products |

### MCP Protocol

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| initialize: Session init | ✅ PASS | 289.16ms | Server: Odiseo MCP Server v1.25.0 |
| tools/list: List all tools | ✅ PASS | 334.47ms | 14 tools available |
| resources/list: List all resources | ✅ PASS | 246.15ms | 5 resources available |

### Sales Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| fetch_by_sku: SKU=COMP-0001 | ✅ PASS | 300.81ms | {'id': 1, 'sku': 'COMP-0001', 'name': 'G |
| fetch_by_id: product_id=1 | ✅ PASS | 297.27ms | {'id': 1, 'sku': 'COMP-0001', 'name': 'G |
| search_products: query='wireless headphones' | ✅ PASS | 505.56ms | 5 items |
| fuzzy_search_smart: query='laptop' | ✅ PASS | 404.28ms | 5 items |

### Booking Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| get_services: List services | ✅ PASS | 283.39ms | Data retrieved |
| get_business_hours: Get schedule | ✅ PASS | 283.95ms | Data retrieved |
| get_available_slots: date=2025-01-15 | ✅ PASS | 278.19ms | Data retrieved |
| create_booking: Create test booking | ✅ PASS | 328.26ms | Expected: Error executing tool create_booking... |
| get_booking_by_id: ID=1 | ✅ PASS | 264.28ms | {'id': 1, 'customer_name': 'Test User',  |
| list_customer_bookings: email=test@example.com | ✅ PASS | 301.86ms | 1 items |
| cancel_booking: ID=99999 | ✅ PASS | 270.46ms | Expected: Error executing tool cancel_booking... |
| reschedule_booking: ID=99999 | ✅ PASS | 284.46ms | Expected: Error executing tool reschedule_boo... |

### OTP Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| generate_otp: email=test-otp@example.com | ✅ PASS | 443.12ms | Success |
| verify_otp: code=000000 (invalid) | ✅ PASS | 307.64ms | Expected: Error... |

### MCP Resources

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| product://sku/COMP-0001: Product by SKU | ✅ PASS | 308.17ms | Product: Gaming Laptop Pro |
| database://stats: Database stats | ✅ PASS | 324.6ms | 45 products |
| tool-categories://sales: Sales tools list | ✅ PASS | 262.3ms | 4 tools |
| tool-categories://bookings: Booking tools list | ✅ PASS | 298.26ms | 8 tools |
| tool-categories://pageable-tools: Pageable tools list | ✅ PASS | 243.55ms | 2 tools |
| tool-categories://otp: OTP tools list | ✅ PASS | 284.25ms | 2 tools |
