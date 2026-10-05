# SmartBiz API integration guide for Lovable

This guide describes the JSON endpoints currently implemented in SmartBiz and the
limits that matter when connecting an external Lovable frontend or AI assistant.
It is based on the Django URL configuration and current view implementations.

## Important: current integration status

- The Django project does **not** currently expose a general REST API for all
  business records. Most sales, products, customers, restaurant operations,
  expenses, and settings routes are Django HTML pages/forms.
- The AI assistant at `POST /ai/assistant/` accepts a form field named
  `question` and returns rendered HTML. It is not a JSON chat API and it does
  not stream tokens.
- The ASGI WebSocket endpoint `/ws/v1/business/` provides business-scoped change
  notifications and request/response AI assistant chat. It does not replace the
  existing HTTP read APIs.
- The restaurant dashboard uses authenticated polling of
  `GET /analytics/api/restaurant-dashboard/` as a fallback when its WebSocket
  is unavailable. With a live socket, business data changes trigger an immediate
  refresh from that HTTP endpoint.
- The REST framework supports Django session authentication and HTTP Basic
  authentication. It does not currently configure OAuth/JWT/Bearer tokens.
- No CORS middleware/configuration for a separate Lovable origin was found.
  A browser app hosted on another origin cannot assume it can call these
  endpoints with credentials.

For a production Lovable integration, use a same-origin reverse proxy or a
server-side Lovable/Edge Function as the API client. Do not place Django
credentials, a Django `SECRET_KEY`, or the Gemini API key in browser code.
The WebSocket uses the existing Django session; it is not a public socket and
does not issue tokens. A separate Lovable origin must be explicitly allowed
with `WEBSOCKET_ALLOWED_ORIGINS`, and the browser must actually send an
authenticated session cookie. Cross-site cookie restrictions may require a
same-origin proxy or server-side connection. HTTP CORS and authentication
remain separate deployment concerns.

## Base URL and common behavior

Set the deployed SmartBiz origin as the base URL, for example:

```text
https://<your-smartbiz-domain>
```

The repository does not define a single production API hostname. Local
development commonly uses `http://127.0.0.1:8000`; that address is not reachable
from a deployed Lovable app.

JSON endpoints are mounted at their paths below, with trailing slashes. The
`/api/` prefix is **not** a versioned API prefix: it currently contains the
user ViewSet only. Other JSON endpoints live under their owning app paths.

### Authentication and CSRF

- Most JSON endpoints use Django `login_required`; REST Framework endpoints
  require an authenticated user.
- Requests must be made as an authenticated SmartBiz user. Normal API login
  and token-issuance endpoints are not implemented; `/accounts/login/` is an
  HTML page.
- Same-origin session requests use the Django session cookie. Unsafe requests
  (POST/PUT/PATCH/DELETE) need a valid CSRF token when session authentication is
  used. The HTML application obtains this through Django's CSRF cookie/form
  token.
- REST Framework is configured for `SessionAuthentication` and
  `BasicAuthentication`. Basic auth should only be used over HTTPS and is not
  a recommended browser-to-API integration strategy.
- The WebSocket uses `AuthMiddlewareStack`, so it authenticates via the
  existing Django session cookie. It rejects unauthenticated users and users
  without a business. The consumer derives the business group from the session;
  clients cannot subscribe to another business by choosing an ID.
- WebSocket origins are checked against `ALLOWED_HOSTS` by default. Configure
  an explicit comma-separated `WEBSOCKET_ALLOWED_ORIGINS` allowlist when the
  app and frontend use different origins. Do not use `*` for production.
- Business-scoped endpoints derive the business from the authenticated user;
  clients do not select a business ID in the request.

Typical JSON headers:

```http
Accept: application/json
Content-Type: application/json
```

Some legacy AJAX mutation views read `application/x-www-form-urlencoded`
request fields rather than JSON. Their request encoding is noted individually.
Errors generally use Django/DRF status codes and JSON bodies where the view
explicitly returns JSON; HTML login redirects and HTML error pages are still
possible for session-protected routes.

## Implemented JSON endpoints

### Users (Django REST Framework)

The same `UserViewSet` is mounted under both `/api/` and `/accounts/api/`.
The resource URLs support trailing slashes.

| Method | Path | Purpose |
|---|---|---|
| GET, POST | `/api/users/` | List users visible to the caller, or create a user |
| GET, PUT, PATCH, DELETE | `/api/users/{user_id}/` | Retrieve, update, partially update, or delete a user |
| GET | `/api/users/{user_id}/activities/` | Return up to 50 activities for that user |
| GET | `/api/users/me/` | Return the authenticated user's serialized profile |
| GET | `/api/users/permissions/` | Return the authenticated user's permission list |
| GET, POST | `/accounts/api/users/` | Legacy alias for user list/create |
| GET, PUT, PATCH, DELETE | `/accounts/api/users/{user_id}/` | Legacy alias for user retrieve/update/delete |
| GET | `/accounts/api/users/me/` | Legacy alias for the current-user profile |
| GET | `/accounts/api/users/permissions/` | Legacy alias for the current-user permissions |

The user serializer includes `id`, `email`, `first_name`, `last_name`,
`full_name`, `phone_number`, `profile_picture`, `role`, `business`,
`is_active`, `is_email_verified`, timestamps, and `permissions`. Password is
not returned in the serialized representation.

**Caution:** these endpoints currently use `IsAuthenticated` as their
ViewSet-level permission. The queryset scopes reads to the user's business
(except `SUPER_ADMIN`), but this is not a substitute for authorization rules on
user creation and mutation. Do not expose these write operations to Lovable
until their role and business-assignment permissions have been reviewed and
locked down.

### Dashboard and analytics

| Method | Path | Access | Purpose / response |
|---|---|---|---|
| GET | `/analytics/api/dashboard-data/` | Authenticated user with a business | Dashboard analytics for the preceding 30-day window. Returns aggregated data including revenue, order value, expenses, profit, daily sales, sales by category, top products, and payment methods. Decimal values are converted to JSON numbers. |
| GET | `/analytics/api/restaurant-dashboard/` | Authenticated user with a restaurant business | Current restaurant dashboard data from saved records: `currency`, `today_revenue`, `completed_orders`, `open_orders`, `average_order`, `menu_item_count`, `low_stock_count`, `top_items`, `low_stock_items`, `recent_orders`, and `last_updated`. Returns `404` for non-restaurant businesses. |
| GET (current implementation has no method restriction) | `/analytics/insights/{insight_id}/read/` | Authenticated user with a business | Marks the caller-business insight read and returns `{"success": true}`. This changes data despite being reachable by GET. |
| POST | `/analytics/insights/{insight_id}/dismiss/` | Authenticated user with a business | Dismisses the caller-business insight and returns `{"success": true}`. |
| POST | `/analytics/insights/{insight_id}/action/` | Authenticated user with a business | Marks the caller-business insight actioned and returns `{"success": true}`. |
| GET | `/sales/api/stats/` | Authenticated user with `record_sales` permission | Sales counts/revenue for today, this week, and this month, plus top products and payment-method totals. |
| GET | `/sales/api/invoice/?invoice={sale_number}` | Authenticated user with `record_sales` permission | Look up a sale belonging to the caller's business by `sale_number`. Returns sale ID, number, customer name/phone, total, payment status, and item rows. Missing `invoice` returns `400`; no match returns `404`. |
| GET | `/inventory/api/stats/` | Authenticated user with `manage_inventory` permission | Stock counts/value and recent transactions, plus low-stock products. |
| GET | `/inventory/api/check-alerts/` | Authenticated user with `manage_inventory` permission | Creates missing low/out-of-stock alerts and returns `success`, `alerts_created`, `low_stock_count`, and `out_of_stock_count`. **This GET has a database side effect**; do not call it as a normal read/poll endpoint. |

The restaurant dashboard response is built from the caller's saved sales,
products, and stock records. It is the best existing read endpoint for a live
restaurant overview. Its dashboard frontend now refreshes in response to
WebSocket change events and falls back to a 30-second poll while disconnected.

## WebSocket API (v1)

### Connection

```text
ws://<smartbiz-host>/ws/v1/business/
wss://<smartbiz-host>/ws/v1/business/   # HTTPS deployment
```

The socket uses Django session authentication. Open it from an already
authenticated same-origin application, or use an authenticated reverse proxy.
An unauthenticated connection closes with code `4401`; an authenticated user
without an associated business closes with code `4403`.

On connect, the server sends:

```json
{
  "type": "connection.ready",
  "business_id": "f0a3c706-a08a-4eae-a13d-3cd6e3f6c51b",
  "capabilities": {
    "business_events": true,
    "assistant_chat": true
  }
}
```

The assistant capability is true only for owner, manager, admin, and
super-admin roles. Business update notifications are sent to authenticated
users associated with the same business.

### Business data change events

After a database transaction commits, the server emits a metadata-only event:

```json
{
  "type": "business.data.changed",
  "event_id": "3eba4ba1-cbe4-49a7-9fef-1d0504541caf",
  "occurred_at": "2026-10-05T13:00:00+03:00",
  "resource": "sales",
  "operation": "created",
  "object_id": "a7e7d1b9-3270-4ff9-a0cc-77de2b02a24d"
}
```

`operation` is `created`, `updated`, or `deleted`. Current event resource
families include team/settings, menu/products, customers, sales/payments,
expenses, inventory, restaurant tables/reservations/kitchen/suppliers/purchase
orders/cash drawer, barber floor/services/appointments/goals/schedule, and
salon appointments/packages. Events contain no customer, payment, or business
record details. Use the event as an invalidation signal and refetch the data
from the corresponding authenticated HTTP endpoint.

Events are emitted after `transaction.on_commit`, so rolled-back writes are not
broadcast. Delivery uses Redis when `REDIS_URL` is configured. The in-memory
channel layer is for local development and single-process tests only; it cannot
coordinate multiple workers or instances and should not be used for a
multi-worker production deployment.

### Assistant chat

The same WebSocket accepts assistant prompts as JSON:

```json
{
  "type": "assistant.ask",
  "request_id": "lovable-request-001",
  "question": "What were my top selling items this month?"
}
```

The question must contain 1-1,000 characters. The answer is generated by the
server using the authenticated user's business data; the Gemini API key is
never sent to Lovable. A successful response is:

```json
{
  "type": "assistant.answer",
  "request_id": "lovable-request-001",
  "answer": "..."
}
```

Failure responses use `type: "assistant.error"` with a `code`, readable
`message`, and the same `request_id` when supplied. Invalid questions return
`invalid_question`; unsupported roles return `forbidden`; provider/configuration
failures return `assistant_unavailable`. There is no token-by-token streaming:
the server sends the completed answer.

Keepalive is supported using `{"type":"ping"}`; the server replies
`{"type":"pong"}`. Other client message types return a JSON `error`.

### Lovable browser example

For a same-origin authenticated Lovable frontend:

```javascript
const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
const socket = new WebSocket(`${scheme}//${window.location.host}/ws/v1/business/`);

socket.addEventListener("message", async ({ data }) => {
  const message = JSON.parse(data);
  if (message.type === "connection.ready") {
    console.log("Connected", message.capabilities);
  } else if (message.type === "business.data.changed") {
    // Refresh the relevant HTTP resource using the same authenticated session.
    await refreshBusinessView(message.resource);
  } else if (message.type === "assistant.answer") {
    showAssistantMessage(message.request_id, message.answer);
  } else if (message.type === "assistant.error") {
    showAssistantError(message.request_id, message.message);
  }
});

function askAssistant(question) {
  const requestId = crypto.randomUUID();
  socket.send(JSON.stringify({
    type: "assistant.ask",
    request_id: requestId,
    question,
  }));
  return requestId;
}
```

Do not connect repeatedly for each question; keep one authenticated socket open
per logged-in client, reconnect with backoff after disconnection, and send a
`ping` periodically if the hosting proxy closes idle connections.

### Products and inventory AJAX

| Method | Path | Access | Request and response |
|---|---|---|---|
| GET | `/products/api/barcode/?barcode={barcode}` | Authenticated user with `manage_products` permission | Looks up an active product in the caller's business. Returns `id`, `name`, `sku`, `selling_price`, `current_stock`, and `unit`. Missing barcode returns `400`; no match returns `404`. |
| POST | `/products/api/update-stock/` | Authenticated user with `manage_products` permission | Form-encoded fields: `product_id`, integer `quantity`, and `action` (`set`, `add`, or `subtract`; defaults to `set`). Returns `success`, `current_stock`, and `is_low_stock`. |
| GET | `/products/api/live-barber-products/` | Authenticated user with `manage_products` permission; barber business only | Returns the live barber product/report payload: products, metrics, low-stock rows, barber rates, and `last_updated`. Other business types receive `404`. |
| POST | `/products/{product_id}/barber-action/` | Authenticated user with `manage_products` permission; barber business only | Form-encoded `action=restock` plus positive integer `quantity`, or `action=archive`. Returns `{"success": true}` on success. Invalid actions/quantities return JSON errors. |

`/inventory/api/check-alerts/` is not a substitute for stock mutation. The
dedicated stock adjustment and inventory transaction screens are HTML workflows,
not JSON endpoints.

### Barber live operations

These endpoints are specific to businesses of type `BARBER`; roles are further
limited by the endpoint's decorator.

| Method | Path | Access | Purpose / request |
|---|---|---|---|
| GET | `/dashboard/barber/api/live-floor/` | Owner, manager, barber, admin, super admin | Current persisted chair/floor state and queue |
| GET | `/dashboard/barber/api/live-board/?date=YYYY-MM-DD` | Owner, manager, barber, admin, super admin | Appointment board, queue, chairs, and metrics for the requested date; defaults to the local current date |
| GET | `/dashboard/barber/clients/live/?search={text}&status={status}` | Owner, manager, barber, admin, super admin | Current client rows and summary; barber users see only their relevant clients |
| GET | `/dashboard/barber/goals/live/` | Owner, manager, barber, admin, super admin | Current goal/streak payload; barber users receive their own scoped data |
| GET | `/dashboard/barber/schedule/live/?week=YYYY-MM-DD` | Owner, manager, barber, admin, super admin | Schedule for the week containing `week`; requires a valid ISO date |
| GET | `/dashboard/barber/money/live/` | Finance roles configured by the barber app | Business money summary; optional query parameters are those accepted by the money view |
| POST | `/dashboard/barber/appointments/create/` | Owner, manager, barber, admin, super admin | Form-encoded appointment fields: `service_id`, `appointment_type` (`booking` or `walk_in`), `client_name`, optional `client_phone`, optional `barber_id`, optional `chair_id`, and `start_time` for bookings. Success returns `success` and `appointment_id`. |
| POST | `/dashboard/barber/appointments/{appointment_id}/chairs/{chair_id}/seat/` | Owner, manager, barber, admin, super admin | Seat an eligible appointment at a chair; returns refreshed floor JSON |
| POST | `/dashboard/barber/chairs/{chair_id}/seat-next/` | Owner, manager, barber, admin, super admin | Seat the next eligible waiting appointment; returns refreshed floor JSON or `409` if none is waiting |
| POST | `/dashboard/barber/appointments/{appointment_id}/finish/` | Owner, manager, barber, admin, super admin | Mark the appointment done; returns refreshed floor JSON |

The mutation endpoints require a CSRF token when using session authentication.
The live schedule endpoint returns a bad-request response when `week` is not a
valid date. Appointment creation and chair assignment also return JSON errors
for invalid or conflicting actions.

### Business settings AJAX

| Method | Path | Access | Purpose / response |
|---|---|---|---|
| POST | `/businesses/settings/save/` | Authenticated user with a business; owner/admin/super-admin role | Form-encoded business settings. Valid input returns `{"success": true, "message": "Settings saved successfully!"}`; invalid input returns `{"success": false, "errors": ...}`. |

This route is intended for the existing same-origin settings UI. It is not a
general-purpose business-settings REST resource.

## AI assistant: what is and is not available

The current assistant endpoint is:

```text
GET  /ai/assistant/   -> rendered HTML assistant page
POST /ai/assistant/   -> accepts form field `question` (maximum 1,000 chars),
                         returns rendered HTML
```

It requires a logged-in user associated with a business and one of the
`OWNER`, `MANAGER`, `ADMIN`, or `SUPER_ADMIN` roles. The answer is generated
server-side from business data and the configured Gemini provider. Provider
credentials remain server-side. This route is **not suitable for a Lovable
fetch expecting JSON**, and it does not provide token streaming.

There is currently no implemented endpoint such as `POST /api/assistant/chat/`.
Do not configure Lovable to call that path until a backend JSON endpoint has
actually been added, authenticated, permission-checked, and tested. A suitable
future contract would accept a JSON `question` and return JSON containing an
answer and request metadata; that contract is a proposal, not a current API.

## Realtime behavior

Current supported behavior is WebSocket push for change notifications, with
HTTP polling as a dashboard fallback:

1. Authenticate the user with the existing Django session.
2. Connect to `/ws/v1/business/` and wait for `connection.ready`.
3. When a relevant `business.data.changed` event arrives, refetch the HTTP
   resource to get its current authorized snapshot.
4. Use the 30-second restaurant dashboard poll only while the socket is
   disconnected. `last_updated` is a snapshot timestamp, not an event cursor.

This is push-based invalidation, not an event history: clients joining late do
not receive prior events, and event IDs are not replay cursors. Redis and a
persistent ASGI host are required to deliver events across multiple workers or
instances.

### Running the ASGI/WebSocket server

Install the additional packages in `requirements.txt`, set `REDIS_URL` to a
production Redis service, and run the ASGI application with Daphne:

```bash
daphne -b 0.0.0.0 -p 8000 smartbiz.asgi:application
```

For a separate Lovable origin, set a narrowly scoped allowlist, for example:

```text
WEBSOCKET_ALLOWED_ORIGINS=https://your-lovable-app.example
```

The ASGI process must run on hosting that supports long-lived WebSocket
connections. The repository's Vercel settings include serverless-specific
SQLite handling; deploy the WebSocket ASGI service on a persistent ASGI host or
use an authenticated same-origin proxy to such a service. Both app instances
must use the same database and Redis channel layer. Configure HTTPS/WSS and
secure session cookies in production.

## Endpoints that are not REST APIs

The following areas currently expose Django pages/forms rather than JSON CRUD
APIs: account registration/login, product/menu management, sales/order
creation and updates, customers, expenses, restaurant tables/reservations/
kitchen/recipes/suppliers/cash drawer, and most business settings. Their URLs
are present in the Django app, but should not be treated as JSON contracts.

For Lovable to create or update those records directly, add explicit JSON
endpoints with serializers, validation, authentication, business scoping,
permission checks, and tests instead of calling template form routes.
