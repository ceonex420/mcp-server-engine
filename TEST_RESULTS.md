## Production Test Scenarios

**Test Date:** 2025-12-28 21:06:48 UTC
**Service URL:** https://mcp-server-4k3haexkga-uc.a.run.app
**Results:** 24/24 passed (0 failed)

### Health

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| health: GET /health | ✅ PASS | 396.51ms | DB: 45 products |

### MCP Protocol

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| initialize: Session init | ✅ PASS | 318.95ms | Server: Odiseo MCP Server v1.25.0 |
| tools/list: List all tools | ✅ PASS | 447.97ms | 14 tools available |
| resources/list: List all resources | ✅ PASS | 345.11ms | 5 resources available |

### Sales Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| fetch_by_sku: SKU=COMP-0001 | ✅ PASS | 341.34ms | {'id': 1, 'sku': 'COMP-0001', 'name': 'G |
| fetch_by_id: product_id=1 | ✅ PASS | 345.48ms | {'id': 1, 'sku': 'COMP-0001', 'name': 'G |
| search_products: query='wireless headphones' | ✅ PASS | 348.32ms | 5 items |
| fuzzy_search_smart: query='laptop' | ✅ PASS | 363.07ms | 5 items |

### Booking Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| get_services: List services | ✅ PASS | 333.82ms | Data retrieved |
| get_business_hours: Get schedule | ✅ PASS | 350.41ms | Data retrieved |
| get_available_slots: date=2025-01-15 | ✅ PASS | 345.41ms | Data retrieved |
| create_booking: Create test booking | ✅ PASS | 346.37ms | Expected: Error executing tool create_booking... |
| get_booking_by_id: ID=1 | ✅ PASS | 345.55ms | {'id': 1, 'customer_name': 'Test User',  |
| list_customer_bookings: email=test@example.com | ✅ PASS | 359.82ms | 1 items |
| cancel_booking: ID=99999 | ✅ PASS | 335.72ms | Expected: Error executing tool cancel_booking... |
| reschedule_booking: ID=99999 | ✅ PASS | 341.57ms | Expected: Error executing tool reschedule_boo... |

### OTP Tools

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| generate_otp: email=test-otp@example.com | ✅ PASS | 398.92ms | Success |
| verify_otp: code=000000 (invalid) | ✅ PASS | 339.17ms | Expected: Error... |

### MCP Resources

| Test | Status | Response Time | Details |
|------|--------|---------------|---------|
| product://sku/COMP-0001: Product by SKU | ✅ PASS | 348.48ms | Product: Gaming Laptop Pro |
| database://stats: Database stats | ✅ PASS | 340.44ms | 45 products |
| tool-categories://sales: Sales tools list | ✅ PASS | 332.31ms | 4 tools |
| tool-categories://bookings: Booking tools list | ✅ PASS | 324.44ms | 8 tools |
| tool-categories://pageable-tools: Pageable tools list | ✅ PASS | 323.51ms | 2 tools |
| tool-categories://otp: OTP tools list | ✅ PASS | 325.21ms | 2 tools |
