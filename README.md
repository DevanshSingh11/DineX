# DineX Universal

DineX connects a restaurant's QR menu to its kitchen, service desk and bill queue. Each restaurant has its own staff, menu, tables, orders and reports. The platform operator reviews registrations in a separate console.

## Start Saffron Courtyard on Windows

1. Stop any DineX window already serving port 8000 with Ctrl+C. Extract the ZIP and open the inner `DineX_Universal` folder.
2. Double-click **Start-DineX.bat**. The launcher uses your installed 64-bit Python 3.14 (including 3.14.2). On first launch it creates the Python environment, downloads the dependencies and asks you to choose the first platform administrator’s name, email and password. Keep the window open.
3. In a fresh workspace, the launcher installs **Saffron Courtyard** with **128 dishes in 16 sections and eight tables**. Choose **Staff sign in**. Enter slug `saffron-courtyard`, email `owner@saffroncourtyard.example` and the starter owner password supplied with this download. You can change it in the restaurant workspace. The platform administrator uses the separate **Platform administration** login.
4. Open **Tables & QR → Table 1 → Show QR**. Scan it on the same Wi-Fi or choose **Open guest menu**. Tap **Ask DineX AI**. The address printed by the launcher is the one to open on your phone. A server log mentioning `0.0.0.0` describes the network interfaces it listens on.

The sample menu also opens in Excel from [Saffron-Courtyard-Menu.csv](starter/Saffron-Courtyard-Menu.csv). Prices are in INR. The bundled database in `starter` supplies the sample restaurant. Your own data lives in the database selected by your local `.env`.

### Upgrade an existing Universal workspace

Stop the old server and back up its `.env` and `data` folder. Copy them into the new extracted project folder before launching it. If your configuration points to a different database location, carry over that database as well. The first launch upgrades the existing menu schema and marks older dishes for kitchen review. Double-click **Add-Demo.bat** to add the sample alongside an existing restaurant. Running it again preserves menu edits, changed passwords and existing tables. Slug collisions leave the existing restaurant in place.

### Use DineX AI

Guests can search by dish, ingredient, diet, course and budget. Try *Show me vegetarian starters under ₹300*. For an allergy, try *I’m allergic to peanuts. Show me desserts under ₹175*. Check the detected allergies and tap **Use these allergy filters**. The guide compares all available dishes, excludes declared allergens, possible traces and unreviewed recipes, and shows the ingredients behind each result. Guests can open a dish or send a question through **Ask the kitchen**. Selected filters last while the guest page stays open. **Clear filters** starts a fresh search.

A sample recipe describes the demo only. For live service, check the actual recipe, supplier ingredients, all options and garnishes, and shared equipment. In **Menu & categories → Edit dish → Recipe and allergen record**, enter the declarations and possible traces and select **Kitchen checked**. Confirm any real allergy order with the kitchen.

### Connect your Gemini key

After the first launch, double-click **Set-Gemini-Key.bat** in the project folder. Paste your key into the hidden prompt on your PC and press Enter. The setup checks your chosen model with one sample request. Restart DineX after the key is saved. The setting is stored in your local `.env` as `GEMINI_API_KEY` and serves the restaurants with DineX AI enabled on this installation. You can set `DINEX_GEMINI_MODEL` to a model available to your Google project. The default is `gemini-flash-latest`. Google receives the text and category names for a Gemini-assisted interpretation. DineX computes prices, ingredient facts and allergy matches from the restaurant catalog. When Gemini is unconfigured or unavailable, local text search continues.

- On a supported browser using trusted HTTPS or localhost, **Speak** puts live browser dictation into the editable question. Choose English (India) or Hindi and check the transcript before searching.
- On a phone visiting an HTTP Wi-Fi address, tap the microphone on the phone keyboard. With Gemini configured, **Use a voice note** also lets you record with the phone’s picker (when supported) or select an audio file, then explicitly send it to Google for transcription. Maximum size is 4 MB. DineX does not store audio or transcripts on the server. An assistance request is saved if the guest chooses to send it to staff.
- **Read answer aloud** uses the device’s available speech voices. Adding a recommended dish opens its normal customization flow.

## Staff access and faster service

DineX separates access by role. Kitchen accounts see only the Kitchen display and can move tickets through their preparation stages. Floor Staff can handle orders and service calls and use checkout; payment confirmation is available when the Owner grants that extra permission. Managers handle operations and reports. Owners manage restaurant settings, menus, tables and team access. Admins manage menus, tables and team access within their role. Platform administration is a separate account and workspace.

Restaurant workspaces refresh request queues every five seconds while visible. Choose **Sound on** in the top bar once per browser to enable distinct audio alerts for new orders, service calls and bill requests. Browsers require this first click before they allow sound.

Checkout now puts the next bill action directly on each queue row. Use **View bill** for line items, optional charges or discounts, and payment confirmation. The phone menu keeps a cart button at the bottom of the screen while guests browse.

## Register your own restaurant

| Where | Action |
|---|---|
| **Register a restaurant** on the home page | Enter the restaurant details and choose the owner's login. Keep the restaurant slug for staff sign-in. |
| **Platform administration** | Sign in with the account from bootstrap. Review the pending registration and set it to **Active**. Platform operators can also create a restaurant directly. |
| **Restaurant workspace** | Sign in with slug, owner email and owner password. Open **Setup guide**. Save the profile, supply a logo or cover, create a category and dish, then configure selections and prices. |
| **Tables & QR** and **Team** | Create a table, open **Show QR** and download the PNG. Add a Kitchen account and any floor staff. Review currency, tax, service charge and time zone in the final setup step. |
| **Guest menu** | Open the table's guest link or scan the printed code. Customize a dish, add it to the cart and place the order. Multiple tabs or guest devices can represent different visits. |
| **Kitchen display** | Use the kitchen account to advance the ticket through Accepted, Preparing, Ready and Served. Instructions and selections accompany each ticket. Floor staff can mark a ready order served from Orders. |
| **Orders & bill** on the guest device | Choose **Request bill / checkout** and confirm. The restaurant sees a pending count and a notification, refreshed every five seconds while the workspace is visible. |
| **Bill requests** on the staff device | Review the included orders, accept, prepare the bill, and mark it awaiting payment. Confirm receipt of the actual cash, UPI or card payment, then complete checkout once every included order has been served. |
| **Reports** | Check paid revenue, gross order value, category performance and table activity for the restaurant's local date. |

Guests who wish to share a single bill can order multiple rounds on one guest device. Each guest visit has its own bill. Other active visits keep a table occupied. Staff can request a bill from the order register if a guest closes the browser or loses the visit credential.

## Scan from a phone

Desktop-only inspection works through **Tables & QR → Show QR → Open guest menu**. For an actual phone, connect the phone and PC to the same trusted private network. Run `ipconfig` on the PC and find its active Wi-Fi adapter's IPv4 address.

1. Stop the local server and open the project `.env`. Set `DINEX_PUBLIC_URL` to the PC's reachable origin, including the port. For example, use `http://192.168.1.25:8000` only if that is your PC's address.
2. Start the server with the following command.

   ```powershell
   .\.venv\Scripts\python.exe -m dinex serve --host 0.0.0.0 --port 8000
   ```

3. Open that same origin in the PC browser. Download or print new QR images containing that address. Allow the application through Windows Firewall on the trusted private network if required. The phone must be able to reach the PC on port 8000.

For public service, use your HTTPS origin and terminate TLS in front of Uvicorn. HTTPS activates secure staff cookies. Use one worker on one host with a local SQLite disk. Review the operations and security notes before accepting live orders.

## Configuration

| Variable | Meaning |
|---|---|
| `DINEX_DATABASE` | New DineX Universal SQLite file, relative to the project or absolute. |
| `DINEX_SECRET` | Random signing key for printed QR credentials. Replacing it invalidates issued codes. Keep it with your protected backups. |
| `DINEX_PUBLIC_URL` | Canonical origin for QR links and browser write requests. Restart the process after changing it. |
| `DINEX_SECURE_COOKIES` | Set true for a TLS deployment. HTTPS public origins set this automatically. |
| `GEMINI_API_KEY`, `DINEX_GEMINI_MODEL` | Optional server-side Gemini credential and model for menu interpretation and voice notes. |
| `DINEX_AI_URL`, `DINEX_AI_MODEL`, `DINEX_AI_KEY` | Optional full HTTPS chat-completions endpoint, model and provider key. Without a Gemini key, these three values enable the existing compatible provider for general menu searches. |

Registration approval starts enabled. INR and Asia/Kolkata are editable restaurant defaults. Currency uses two decimal places throughout the supported currency list. Existing orders lock the restaurant currency to preserve report meaning. Owners configure rates for their own restaurant. The baseline tax and service charge are both zero.

## Run the checks

Run these commands in the extracted project folder.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q dinex tests checks
```

The optional interface check exercises the shipped JavaScript against a real temporary HTTP server. Install Node.js 22+ only to run this developer check. npm access is needed once to install its test tools.

```powershell
npm ci --prefix checks/ui
.\.venv\Scripts\python.exe checks/ui_journey.py
```

## Fix a request-origin error

If a browser shows the message `Use the configured DineX origin and request header`, compare its address with the origin printed by `Start-DineX.bat`. Open the printed origin. Do not open `0.0.0.0` or an old address.

For this PC, if the current Wi-Fi address is `192.168.0.101`, stop DineX with Ctrl+C. In PowerShell, from the project folder, start the server with the matching origin:

```powershell
$env:DINEX_PUBLIC_URL = 'http://192.168.0.101:8000'
.\.venv\Scripts\python.exe -m dinex serve --host 0.0.0.0 --port 8000
```

Open `http://192.168.0.101:8000/platform` again and refresh. This address can change after switching Wi-Fi networks. The corrected launcher uses the active network route to select the same address for the server, browser and printed QR codes.

## Operations and support

- Back up the database using SQLite's online backup API or stop DineX before copying the complete data directory. Back up `.env` separately and protect both copies. Restore them into the same Universal schema generation with the service stopped.
- `python -m dinex init` can be repeated. It retains an existing configuration and data. A foreign application database or unsupported future schema stops startup.
- If your browser reports a request-origin error, open the exact origin in `DINEX_PUBLIC_URL`. If a QR no longer opens a table, check the tenant, table activation and credential status, then issue a current QR.
- For a setup problem, share the command that failed, the terminal error and the relevant screen. Redact passwords, API keys, cookies and QR credentials. Keep the live database and `.env` private.

## Project documents

| File | Contents |
|---|---|
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Reference review, architecture, permissions, workflows and phases |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | Entities, tenant keys, transactions, migrations and backups |
| [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | API contract, routes, money units and examples |
| [SECURITY_REVIEW.md](SECURITY_REVIEW.md) | Authorization, input handling, threat boundaries and deployment assumptions |
| [TEST_REPORT.md](TEST_REPORT.md) | Executed tests, observations and verification limits |
| [DEVELOPMENT_PROGRESS.md](DEVELOPMENT_PROGRESS.md) | Delivered scope, integration status and remaining operational validation |
| [IMPLEMENTATION_CHANGELOG.md](IMPLEMENTATION_CHANGELOG.md) | Changes across the implementation milestones |

The landing image was generated for DineX. The bundled DM Sans and Instrument Serif font licenses are in `web/static/fonts`.
