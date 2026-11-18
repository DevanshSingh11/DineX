# Implementation plan and reference review

## Product and retained workflows

A platform operator approves restaurants. Owners configure their dining room and menu. A guest opens a table QR, customizes dishes and tracks the ticket. The kitchen advances preparation, the floor handles service and staff settle the bill after receiving payment.

The six supplied archives were inspected as references. The two attached briefs were byte-identical. Source paths, routes, frontend entry points, test inventories and project reports guided the review. Historical verification statements describe those snapshots only.

| Reference | What informed this build |
|---|---|
| DineX.zip | QR menu and kitchen pages, migration and pricing tests, server-side analytics and real-time/authentication coverage. |
| DineX(1).zip | Original menu customization and guest ordering concepts. Its archived environment, Git history and local configuration belong to that project. |
| DineX_Independent_Repair.zip | Distinct customer, kitchen and administration views, table-bound access and preservation of selections. |
| DineX_Final.zip | Single-restaurant workflow, repair notes and checks for migrations, roles and frontend assets. |
| DineX_Final_verified.zip | Smaller snapshot with role-route checks, a browser test script and explicit verification notes. |
| DineX_Final_rechecked.zip | Comparison of Python, JavaScript, HTML, CSS and Markdown with the verified ZIP found one difference, in the final verification report. |

## Architecture and design decisions

The new project has its own application identifier, storage path, first-run configuration and dependencies. Separate actor-bound APIs keep a guest QR, restaurant login and platform login in independent authorization contexts. Immutable order snapshots, a distinct checkout state machine and database-backed payment records carry the workflow through settlement.

| Location | Responsibility |
|---|---|
| `dinex/app.py`, `config.py`, `__main__.py` | Application factory, HTTP guards, environment and local initialization/bootstrap/server commands |
| `dinex/models.py`, `db.py` | SQLAlchemy schema, schema version, tenant-scoped retrieval and transactional units of work |
| `dinex/schemas.py`, `security.py` | Strict request DTOs, passwords, sessions, authorization, QR signing and audit helper |
| `dinex/catalog.py`, `ordering.py`, `payments.py` | Tenant setup, catalog, pricing, order and bill transitions, payment recorder contract |
| `dinex/assistant.py`, `reports.py` | Menu ranking providers and local-time financial/operational aggregations |
| `dinex/routes/` | Platform/onboarding/auth, restaurant operations, guest endpoints and branded media |
| `web/`, `web/static/` | HTML entry points, responsive styles, locally served fonts, photograph and shared JS components |
| `tests/`, `checks/` | Isolated API/integrity tests and optional cross-screen JavaScript integration journey |

## Restaurant permissions

| Capability | Owner | Admin | Manager | Kitchen | Staff |
|---|---:|---:|---:|---:|---:|
| Restaurant settings and onboarding guide | Yes | — | — | — | — |
| Menu, categories, images and tables | Yes | Yes | — | — | — |
| Manage accounts | All | Manager, Kitchen and Staff | — | — | — |
| Operational overview and reports | Yes | Yes | Yes | — | — |
| Audit details | Yes | Yes | — | — | — |
| Read kitchen tickets and advance preparation | Yes | Yes | Yes | Yes | — |
| Read order register and mark ready orders served | Yes | Yes | Yes | — | Yes |
| Cancel an eligible unbilled order with reason | Yes | Yes | Yes | — | — |
| Handle guest service and checkout | Yes | Yes | Yes | — | Yes |
| Confirm manual payments | Yes | Yes | With grant | — | With grant |
| Apply audited bill adjustments | Yes | Yes | With grant | — | — |

The Kitchen role can also mark a ready ticket served from its queue. Permission grants are limited to those shown. A restaurant must retain an active Owner. Only the platform console can review registrations, change tenant access, configure plans, assign entitlements, manage platform administrators and see platform statistics.

## Workflows and defaults

| Entity | Transitions and invariants |
|---|---|
| Restaurant | Public registration starts pending when approval is enabled. An approved or manually created restaurant is active. Suspension and deactivation invalidate its logins and visits. |
| Order | Received → Accepted → Preparing → Ready → Served. Completing a paid checkout advances its served orders to Completed. An operations user can cancel a received or accepted order without a current bill and must give a reason. |
| Bill | Pending → Accepted → Prepared → Awaiting payment → Paid → Completed. An unpaid bill can be cancelled with a reason. Bill preparation freezes adjustments. Historical bill membership survives cancellation. |
| Payment | Staff record one confirmed receipt per bill for the calculated payable amount. UPI and card refer to the method used outside DineX. |
| Table | Occupancy is derived from every active order and unfinished bill. Serving, a single receipt, or one guest leaving does not release a table with other active visits. |
| Service | Open → Accepted → Resolved. One outstanding request of each type per visit is sufficient to notify staff. |
| Guest | A table QR opens a private browser visit. Additional rounds share that visit. Other guests at the same table retain separate carts, order histories and bills. |

The restaurant sets currency, time zone, rates, branding and menu. A verified provider, merchant account and settlement policy remain operator decisions for any future payment integration.

## Phases and deliverables

| Phase | Delivered result |
|---:|---|
| 1 | Reference inventory, architecture, entity map, permission matrix and transition rules |
| 2 | Runnable FastAPI application, SQLite identity/version checks, health route and bootstrap |
| 3 | Platform console, account management, registration approval, tenant settings and plan assignment |
| 4 | Restaurant overview, eight-step guide, menu and option editors, staff grants and QR lifecycle |
| 5 | Mobile table menu, dish configuration, persistent visit cart, retry-safe ordering and tracking |
| 6 | Kitchen queue, validated preparation actions, floor service and visible queue updates |
| 7 | Private guest bill request, staff queue, adjustments, manual receipts and table release |
| 8 | Local/remote menu guide ranking and date-filtered, time-zone-aware reports |
| 9 | Responsive views and shared controls exercised through the application's actual JavaScript |
| 10 | Automated and live verification, Windows handover and a cumulative downloadable source ZIP |
