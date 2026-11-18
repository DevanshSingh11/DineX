# Verification report

## DineX AI edition 1.1.0

The Python suite passed all 44 tests. The seven new cases cover the populated starter, repeat installation, migration of an existing menu, allergy confirmation and exclusions, distinct ingredient questions sent to staff, Gemini request formats, voice access and fallback behavior.

The existing interface journey also passed against a temporary HTTP server. A second journey used the bundled Saffron Courtyard login and a real table credential. It followed the guest interface through meal search, two allergy filters, a result added to the cart and an ingredient question delivered to staff. The speech branch used a simulated recognizer to verify that guests can edit a transcript before submitting. The provider tests used simulated Google responses. A live Gemini key, native Windows execution and a physical phone microphone were unavailable in this environment.

## Earlier release 1.0.0

**18 November 2026**

The clean-environment run finished with **37 passed, 0 failed, 0 skipped** in 61.11 seconds. Pytest emitted one upstream Starlette TestClient deprecation warning about its HTTPX adapter. The application, test client and installed requirements ran together successfully.

## Automated coverage

| Suite | Passed | What it verifies |
|---|---:|---|
| `test_accounts.py` | 8 | Registration and approval, active/suspended accounts, sign-in/logout, roles, last owner and platform administrator, plan limits, audit, tenant separation, image handling, rate limits and safe migrations |
| `test_ordering.py` | 13 | Authoritative pricing and tax rounding, snapshots after menu edits, nine invalid-input/availability cases, concurrent order and bill retries, QR rotation/revocation, service and grounded assistant behavior |
| `test_checkout.py` | 5 | Two guests and three orders, correct bill membership, restricted adjustments and receipts, kitchen/payment independence, completion and final table release, cancellation recovery, separate local receipt and order dates |
| `test_integrity.py` | 10 | CSRF requirement and response headers, database-enforced tenant isolation, both password-change realms, bill/order race, current onboarding status, expired guest recovery, floor permissions, paging, guide entitlements and atomic failure |
| `test_provider.py` | 1 | Mocked HTTPS provider contract, rejection of unknown/unavailable IDs and fallback after provider failure |

The test environment used CPython 3.12.14, SQLite 3.53.1, FastAPI 0.141.1, SQLAlchemy 2.1.9, Pydantic 2.13.4 and pytest 9.2.0 on Linux. Installation into a separate empty virtual environment from the shipped requirements succeeded. `pip check` found no broken requirements. Test cases use newly created temporary databases.

## Executed integration checks

| Check | Observed result |
|---|---|
| Guest in an actual Chrome window | Opened a disposable table QR link, selected a ₹45 large portion on a ₹280 dish, entered kitchen instructions and saw ₹325 in the cart. Placed the order, confirmed a bill request and saw the pending state. Staff actions through the real restaurant API served the order and recorded a simulated cash receipt. Automatic guest refresh displayed Paid, Completed, ₹325 and the full kitchen history. The table became available. |
| Cross-role interface journey | Passed using the shipped JavaScript in jsdom against real HTTP endpoints on a temporary Uvicorn server. Registered and approved a restaurant, completed all eight setup tasks, added a required customization and Kitchen user, issued a QR, ordered two dishes, requested water and a bill, used the menu guide, served tickets, applied a ₹10 discount, recorded a simulated ₹640 cash receipt on a ₹650 order, completed checkout, checked the report and observed table release. |
| Two independent visits at the same table | The first visit placed two orders and the second placed one. Completing the first bill closed its visit while the other visit kept the table occupied. Completing the second bill released the table. Cross-visit tracking and totals stayed private. |
| Independent QR decoding | Decoded the generated PNG using ZXing-C++ 3.1.1. The decoded text matched the issued URL including its restaurant, table and complete QR credential. |
| Source and static checks | Python compilation, Python undefined/unused-name checks, and Node syntax checks for all seven application JavaScript modules and the optional interface runner passed. All four HTML shells have language and viewport metadata, local asset references resolved and the CSS parsed with narrow-screen rules for navigation, menu, kitchen and data tables. |
| Windows launcher | Added `Start-DineX.bat` to detect the default network interface IPv4 address, set the session QR origin, create/reuse the local environment, install requirements, initialize the database, safely skip repeat administrator creation, open the LAN URL and serve on all interfaces. A live Windows desktop was not available for executing the batch file. |
| Fresh extraction | Initialized a newly extracted ZIP twice and verified configuration preservation. Created the first platform administrator through the CLI. Started Uvicorn, signed in using the HTTP API, checked the empty tenant list, health, six entry routes, bundled assets and OpenAPI schema. SQLite integrity and foreign-key checks passed. |
| Windows package resolution | pip downloaded wheels for the declared dependency set targeting 64-bit Windows CPython 3.12. This verifies wheel availability. The runtime and CLI checks above executed on Linux. |

## Reproduction

Run `.\.venv\Scripts\python.exe -m pytest -q` in the extracted project. Run the optional JavaScript journey with the commands in README.md. It starts its own temporary server, creates synthetic accounts and validates the same UI modules against real API transactions. The app itself runs with Python alone.

## Verification limits

A physical phone camera, paper print, native Windows PowerShell execution, visual checks on physical small-screen devices, production load and an independent security assessment remain unverified. The remote AI adapter was exercised with a simulated provider response and outage. Online payment collection and subscription charging are outside this release. The recorded QA receipts moved no money.
