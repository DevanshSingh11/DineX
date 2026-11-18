# HTTP API

The app serves the UI and API from one origin. `GET /openapi.json` gives the install's machine-readable request schemas, required fields and query parameters. `GET /health` checks database connectivity.

## Request conventions

- Use JSON for structured requests and raw bytes for images or voice notes. Add `X-DineX: 1` to API mutations. Browser requests must originate at the configured public origin.
- The platform and restaurant login endpoints set separate, path-scoped HttpOnly cookies. Keep the cookie for the corresponding API. Restaurant sign-in also requires a restaurant slug. The authenticated staff membership determines the tenant.
- An authorized QR issue returns a guest URL. The frontend reads its table ID and fragment, posts them to the guest entry endpoint, then uses `Authorization: Bearer <visit-token>` for that visit. It removes the fragment from the address bar. Guests can read only their own visit's orders, bills and requests.
- Monetary request and response fields are integer minor units. Basis-point fields use 100 for 1%. Timestamps in responses are UTC epoch seconds. The frontend formats them using the restaurant's IANA time zone.
- Request models reject extra fields. Validation errors use `422`, authentication errors use `401`, permission denials use `403`, missing/foreign records use `404`, conflicting state uses `409`, oversized bodies use `413`, rate limiting uses `429`, and temporary writer contention uses `503`. Errors include a human-readable `detail` string.

## Restaurant registration and credentials

`POST /api/register` accepts a unique slug, restaurant name, owner name/email and chosen password. Contact, address, branding, currency, time zone, initial table count and operating settings may accompany the registration. The browser collects contact and location details during registration. Manual platform creation uses the same model. The owner can authenticate once the tenant is active.

`POST /api/platform/login` takes email and password. `POST /api/restaurant/login` adds `slug`. `POST /api/{realm}/password` accepts `current` and `replacement` and revokes all sessions for the authenticated account. `POST /api/{realm}/logout` invalidates the presented session.

## Menu and order example

Create a category first. Send the following shape to `POST /api/restaurant/items` using a category ID returned for the current restaurant. For an edit, PUT the whole editable definition. New edited option rows receive new IDs.

```json
{
  "category_id": 1,
  "name": "Roast cauliflower",
  "price": 28000,
  "dietary": "vegetarian",
  "ingredients": "Cauliflower, yogurt, cumin",
  "groups": [{
    "name": "Portion", "minimum": 1, "maximum": 1,
    "options": [{"name": "Regular", "price": 0}, {"name": "Large", "price": 4500}]
  }]
}
```

After entering a table, get the guest menu to obtain the current item and option IDs. This example submits two portions to `POST /api/guest/orders`.

```json
{
  "request_key": "example-submission-00001",
  "lines": [{"item_id": 1, "quantity": 2, "options": [2], "note": "Sauce on the side"}]
}
```

Generate a new high-entropy submission key for each intentional order. Persist it with the payload before sending. Replay the same payload and key after a lost response. Reusing a key for different content returns 409. An accepted order response includes its number, server-calculated totals, immutable line snapshots and history. A closed visit can retry an already accepted identical submission without creating another order.

## Checkout and settlement

1. `POST /api/guest/bills` takes no tenant, table, order IDs or amounts. It collects the eligible orders on the authenticated visit and returns its current bill on a retry. Staff can initiate the same workflow through an order if a guest loses the browser.
2. The staff UI polls the pending-count route and queue. Use `GET /api/restaurant/bills?status=pending` for pending requests. Pages can use `limit` (1–100) and the last ID of the previous page as `before`. The order register supports the same pagination.
3. Send `{"status":"accepted"}` to `PUT /api/restaurant/bills/{ident}`. Then prepare it with `{"status":"prepared","adjustment":0,"discount":1000,"reason":"Manager courtesy"}` when the actor has adjustment permission. Preparation without adjustments needs no explanation.
4. Send `{"status":"awaiting_payment"}`. After staff verify the real payment, send `{"status":"paid","method":"upi","reference":"RECEIPT-EXAMPLE","confirmed":true}`. Cash and card are also valid. The API derives the amount from the prepared bill.
5. Send `{"status":"completed"}` after all included orders are served. Customer tracking shows the final bill and receipt state. A paid bill awaiting service keeps the table occupied. An unpaid request may be cancelled with `{"status":"cancelled","reason":"Guest requested another course"}`.

Each guest state response includes orders, stage history, bill contents, payment state and service requests for that visit. Staff-only payment references and assigned staff identities are omitted from guest bill details.

## Reporting and integrations

`GET /api/restaurant/reports?start=2026-11-01&end=2026-11-18` uses inclusive local dates and supports up to 366 days per request. Responses separate gross order value, paid receipts, currently unpaid requested bills, cancelled orders, order counts, average order value, daily series, hourly/table activity, popular dishes, category value, payment methods and service types. The restaurant overview is a live summary using the current local day.

`POST /api/guest/assistant` accepts `question` (up to 400 characters), optional `avoid` allergen IDs and a `confirmed` flag. The guest menu supplies the options and the plan’s guide capabilities. A natural-language allergy request returns the proposed IDs and `needs_confirmation`. Resubmit the same request with the checked IDs and `confirmed: true`. Responses contain catalog-backed items, a source mode, kitchen handoff and recipe information. An unresolved exclusion returns no items. Optional Gemini interpretation supplies a structured search, and the compatible provider remains available for ordinary searches.

`POST /api/guest/assistant/transcribe` accepts a voice note as raw audio with its MIME type, a valid visit token and the same origin header convention. It requires guide access and a configured Gemini key. A successful response contains an editable `transcript`. The server limits uploads to 4 MB and each client to eight requests per minute. A separate guest action sends a text question or an order.

The manual payment recorder implements the `PaymentRecorder` contract in `dinex/payments.py`. Online payment providers and recurring subscription billing need independent integration, verification and reconciliation. Current plan configuration enforces active table/staff limits and reports/guide access. The subscription label records administrative status.

## Endpoint inventory

The following inventory is generated from the release's FastAPI schema.

### Public and media

| Method | Path | Request model | Query parameters |
|---|---|---|---|
| GET | `/health` | — | — |
| POST | `/api/register` | Registration | — |
| GET | `/media/{tenant}/{ident}` | — | — |

### Platform

| Method | Path | Request model | Query parameters |
|---|---|---|---|
| POST | `/api/platform/login` | Credentials | — |
| POST | `/api/platform/logout` | — | — |
| GET | `/api/platform/overview` | — | — |
| GET | `/api/platform/restaurants/{ident}` | — | — |
| POST | `/api/platform/restaurants` | Registration | — |
| PUT | `/api/platform/restaurants/{ident}/state` | RestaurantState | — |
| PUT | `/api/platform/policy` | PolicyUpdate | — |
| GET | `/api/platform/plans` | — | — |
| POST | `/api/platform/plans` | PlanInput | — |
| PUT | `/api/platform/restaurants/{ident}/plan` | Assignment | — |
| GET | `/api/platform/accounts` | — | — |
| POST | `/api/platform/accounts` | PlatformAccount | — |
| PUT | `/api/platform/accounts/{ident}` | Toggle | — |
| GET | `/api/platform/audit` | — | — |
| POST | `/api/platform/password` | PasswordChange | — |

### Restaurant

| Method | Path | Request model | Query parameters |
|---|---|---|---|
| POST | `/api/restaurant/login` | RestaurantLogin | — |
| POST | `/api/restaurant/logout` | — | — |
| GET | `/api/restaurant/me` | — | — |
| POST | `/api/restaurant/password` | PasswordChange | — |
| GET | `/api/restaurant/overview` | — | — |
| GET | `/api/restaurant/profile` | — | — |
| PUT | `/api/restaurant/profile` | Profile | review_settings |
| GET | `/api/restaurant/menu` | — | — |
| POST | `/api/restaurant/categories` | CategoryInput | — |
| PUT | `/api/restaurant/categories/{ident}` | CategoryInput | — |
| POST | `/api/restaurant/items` | ItemInput | — |
| PUT | `/api/restaurant/items/{ident}` | ItemInput | — |
| GET | `/api/restaurant/tables` | — | — |
| POST | `/api/restaurant/tables` | TableInput | — |
| PUT | `/api/restaurant/tables/{ident}` | TableInput | — |
| POST | `/api/restaurant/tables/{ident}/credential` | QRAction | — |
| POST | `/api/restaurant/tables/{ident}/qr` | — | — |
| GET | `/api/restaurant/tables/{ident}/qr.png` | — | — |
| GET | `/api/restaurant/staff` | — | — |
| POST | `/api/restaurant/staff` | StaffInput | — |
| PUT | `/api/restaurant/staff/{ident}` | StaffEdit | — |
| GET | `/api/restaurant/orders` | — | before, limit |
| GET | `/api/restaurant/kitchen` | — | — |
| PUT | `/api/restaurant/orders/{ident}/status` | OrderStep | — |
| POST | `/api/restaurant/orders/{ident}/bill` | — | — |
| GET | `/api/restaurant/bills` | — | status, before, limit |
| GET | `/api/restaurant/bills/pending-count` | — | — |
| PUT | `/api/restaurant/bills/{ident}` | BillStep | — |
| GET | `/api/restaurant/services` | — | — |
| PUT | `/api/restaurant/services/{ident}` | ServiceStep | — |
| GET | `/api/restaurant/reports` | — | start, end |
| GET | `/api/restaurant/audit` | — | — |
| POST | `/api/restaurant/images` | string | — |

### Guest

| Method | Path | Request model | Query parameters |
|---|---|---|---|
| POST | `/api/guest/enter/{slug}` | Enter | — |
| GET | `/api/guest/menu` | — | — |
| POST | `/api/guest/orders` | OrderInput | — |
| GET | `/api/guest/state` | — | — |
| POST | `/api/guest/bills` | — | — |
| POST | `/api/guest/services` | ServiceInput | — |
| POST | `/api/guest/assistant` | Question | — |
| POST | `/api/guest/assistant/transcribe` | Raw audio | — |
