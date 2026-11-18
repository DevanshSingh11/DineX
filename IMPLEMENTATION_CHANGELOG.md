# Implementation changelog

## DineX AI edition 1.1.0

- Added the Saffron Courtyard starter restaurant with 128 sample recipes, 16 sections, eight tables and an editable menu CSV.
- Added a guest menu entry for DineX AI, browser dictation, optional Gemini voice-note transcription and spoken results.
- Added kitchen-editable allergen and possible-trace declarations, confirmation of guest exclusions and a distinct ingredient question in the service queue.
- Added a local Gemini key prompt, an additive installer for existing databases and the revision 2 migration.


## 1.0.0 · independent Universal release

- Reviewed the archived source families, their single-restaurant assumptions and supplied verification reports. Created a separate project, database signature and first-run environment.
- Added platform registrations, approval policy, account and plan administration and per-restaurant roles, service limits and ownership enforcement.
- Implemented the eight-step owner guide, real menu and customization editing, image sanitation, table lifecycle, downloadable and revocable QR credentials and team grants.
- Added private table visits, server-priced orders, immutable order lines and persisted submission keys. A retry reuses its original order. A changed payload using the same key returns a conflict.
- Connected distinct guest, management and kitchen views. Added order histories, queue polling, service requests and availability warnings.
- Added staff bill requests, historical bill membership, reasoned adjustments, separate payment receipt and completion, lost-device staff recovery and table release across multiple visits.
- Added timezone-aware reports, bounded order/bill history pages, operational summaries and the local menu guide. The optional external ranker returns constrained recommendations.
- Checked an actual guest browser journey and exercised the shipped JavaScript across platform, owner, kitchen and guest workspaces using a temporary HTTP server. Form edits, QR, grants, payment and analytics are included in the verification suite.
- Packaged application source, local assets, font licenses, automated checks, environment example and the full handover documents.

- Added a Windows double-click launcher that prepares the virtual environment, dependencies and database, creates the first platform account when needed, then starts the server. Made the initial administrator setup safe to run again.
