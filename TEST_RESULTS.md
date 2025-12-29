## Production Test Scenarios

**Test Date:** 2025-12-28 20:44:12 UTC
**Service URL:** https://mcp-server-4k3haexkga-uc.a.run.app
**Results:** 24/24 passed (0 failed)

### Health

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| health: GET /health | ✅ PASS | 532.55ms | DB: 45 products |

### MCP Protocol

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| initialize: Session init | ✅ PASS | 310.27ms | Server: Odiseo MCP Server v1.25.0 |
| tools/list: List all tools | ✅ PASS | 406.49ms | 14 tools available |
| resources/list: List all resources | ✅ PASS | 306.45ms | 5 resources available |

### Sales Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| fetch_by_sku: SKU=COMP-0001 | ✅ PASS | 306.37ms | {'id': 1, 'sku': 'COMP-0001', 'name': 'G |
| fetch_by_id: product_id=1 | ✅ PASS | 304.26ms | {'id': 1, 'sku': 'COMP-0001', 'name': 'G |
| search_products: query='wireless headphones' | ✅ PASS | 311.79ms | 5 items |
| fuzzy_search_smart: query='laptop' | ✅ PASS | 332.88ms | 5 items |

### Booking Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| get_services: List services | ✅ PASS | 301.88ms | Expected: Error executing tool get_services: ... |
| get_business_hours: Get schedule | ✅ PASS | 309.38ms | Expected: Error executing tool get_business_h... |
| get_available_slots: date=2025-01-15 | ✅ PASS | 293.95ms | Expected: Error executing tool get_available_... |
| create_booking: Create test booking | ✅ PASS | 291.75ms | Expected: Error executing tool create_booking... |
| get_booking_by_id: ID=1 | ✅ PASS | 312.97ms | Expected: Error executing tool get_booking_by... |
| list_customer_bookings: email=test@example.com | ✅ PASS | 312.5ms | Expected: Error executing tool list_customer_... |
| cancel_booking: ID=99999 | ✅ PASS | 299.69ms | Expected: Error executing tool cancel_booking... |
| reschedule_booking: ID=99999 | ✅ PASS | 303.27ms | Expected: Error executing tool reschedule_boo... |

### OTP Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| generate_otp: email=test-otp@example.com | ✅ PASS | 350.2ms | Success |
| verify_otp: code=000000 (invalid) | ✅ PASS | 315.29ms | Expected: Error... |

### MCP Resources

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| product://sku/COMP-0001: Product by SKU | ✅ PASS | 297.32ms | Product: Gaming Laptop Pro |
| database://stats: Database stats | ✅ PASS | 295.44ms | 45 products |
| tool-categories://sales: Sales tools list | ✅ PASS | 305.11ms | 4 tools |
| tool-categories://bookings: Booking tools list | ✅ PASS | 298.4ms | 8 tools |
| tool-categories://pageable-tools: Pageable tools list | ✅ PASS | 294.61ms | 2 tools |
| tool-categories://otp: OTP tools list | ✅ PASS | 296.54ms | 2 tools |
