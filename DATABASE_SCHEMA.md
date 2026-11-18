# Database schema and migrations

## Identity and tenant relationships

SQLite schema revision **2** uses application ID `0x44585531`. Every connection enables foreign keys. All tenant child records contain a restaurant key named `tenant`. Composite foreign keys of the form `(tenant, parent_id)` reference `(tenant, id)` on parent tables. Repository helpers add the authenticated tenant to every tenant-owned lookup.

| Table | Keys, relationships and purpose |
|---|---|
| `platform_policy`, `platform_users` | Registration approval toggle, unique normalized platform email and active flag |
| `plans`, `restaurants` | Active staff/table limits, analytics/guide entitlements and trial duration. Restaurant stores a unique slug, profile/settings, plan, subscription label and optional trial expiry |
| `staff`, `logins` | Unique email per restaurant. Base roles and whitelisted grants. A login belongs exclusively to a platform user or a tenant/staff pair and stores a token digest and expiration |
| `categories`, `items` | Tenant category with unique name. Menu items carry an availability flag, feature flag, archive flag, image, dietary metadata, integer price, ingredients, declared allergens, possible traces and a recipe status (unreviewed, reviewed or sample) |
| `choice_groups`, `choices` | Item-specific minimum/maximum and option price deltas. Autoincrementing IDs keep removed choices from being reassigned |
| `media` | Sanitized WebP bytes owned by the restaurant. A public image response requires a current branding reference or an unarchived dish in an active category |
| `dining_tables`, `visits` | Table name unique per restaurant, QR generation nonce and revocation flag. A 48-hour visit records a private token digest, originating table/nonce and closed flag |
| `orders`, `order_lines`, `order_history` | Order number unique per tenant. Unique (visit, submission key) and stored request fingerprint. Lines retain quantity, name, category name, base and final unit price, selections and instructions. Append-only stage history carries UTC timestamps |
| `bills`, `bill_orders` | Request and bill share one lifecycle record. A partial unique index permits one non-cancelled bill per visit. Membership rows preserve every original snapshot, even when a cancelled bill's orders are attached to a successor |
| `payments` | Unique bill reference, exact minor-unit amount, actual method, optional external reference, confirming staff member and receipt timestamp |
| `service_requests` | Private visit and table context, type, note, timestamp and independent service status |
| `audit` | Actor reference, event, entity reference, tenant or platform context, timestamp and operational detail |

Analytics are computed from operational rows. The menu assistant handles a single question at a time. Browser-local presentation holds its latest answer. The service does not persist guest conversations.

## Money, dates and locking

Supported currencies use two decimal places. The client supplies item IDs, quantities, options and notes. The server sums base price and selected deltas in integer minor units. Tax and configured service charge each apply to the order subtotal and round half-up to a minor unit with `(subtotal * basis_points + 5000) // 10000`. Combined bills sum the stored order subtotals and rounded charges. During preparation, an authorized staff member can add an explained charge or discount. The final payable amount must be nonnegative.

UTC epoch seconds are persisted. Restaurant reports use inclusive local date labels converted to a half-open UTC interval. Gross value follows order creation. Paid revenue follows receipt time. Pending payments sum the still-unpaid bills requested in the period. Category totals use item value before order-level charges and bill adjustments.

A request gets one SQLAlchemy session and transaction. Mutations acquire a SQLite write reservation before reading the business state. Readers use snapshot transactions. The assistant obtains a read transaction. Writes flush inside the transaction, commit together and roll back on exceptions. WAL, an 8-second busy timeout, foreign keys and uniqueness constraints apply on a local disk. SQLite accepts one concurrent writer. Size the deployment against observed peak service and report traffic. [SQLite isolation](https://www.sqlite.org/isolation.html)

## Migrations and recovery

`dinex/db.py::migrate` checks file identity, takes a write reservation and applies each forward revision in a transaction. Fresh databases receive the schema and one default plan/policy. Upgrading from Universal v1 adds the two JSON lists and a review status in one transaction. Existing recipes start as unreviewed. An unrelated nonempty database or a higher revision causes a startup error.

For the next schema change, add an explicit, ordered from-version step to `migrate`. Keep a fixture from the previous release, apply the revision to a copy, verify foreign keys, retained snapshots and row counts, then update `user_version` in the same transaction. SQLite table rebuilds require explicit copy and verification for changed constraints. Editing ORM declarations alone does not migrate an installed database.

To back up a running instance, use SQLite's online backup API. For an offline backup, stop the server and copy the entire data directory with any WAL/SHM files plus the protected configuration. Test restores under a separate database path. Previous DineX project databases have a different schema and are outside the migration chain.
