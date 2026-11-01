# Application preview origins

## Current Reconlith preview

[Desktop overview](reconlith-overview-desktop.png) is a direct, unedited Chromium
viewport screenshot of the publication checkout's actual React overview at
1600 x 900 (16:9), captured on 2026-11-01. The six Reconlith presentation edits
were present; no application data or behavior was changed for the capture.

Only a local Vite frontend was started. A fresh browser context used the light
theme, reduced motion and bundled fonts. Service/API and external requests were
blocked by the capture harness; no blocked request was attempted on this overview.
No API responses, metrics, customer records, incidents or model outputs were
injected. The architecture artwork inside the UI is conceptual, not live data.
This image demonstrates interface presentation, not banking or AI integration.

The source reviewed before capture was `frontend/src/pages/Overview.tsx`, the
application shell and shared branding components. No credential or account entry
screen was opened. The screenshot contains no customer data or credentials;
PNG ancillary metadata is checked separately from visible content.

## Historical preview

[Original overview](workspace-overview.png), 1440 x 1326, retains its BankOps AI
branding and original pixels. The existing publication records identify it as a
static browser-test preview using no service requests or customer data. It is not
new Reconlith execution evidence and has not been relabeled as a live integration.

## Integration evidence is separate

[Step 75](../verification/STEP75_INTEGRATION_REPORT.md) documents the historical
synthetic scheduler-to-dashboard scenario: RCA Undetermined, inference disabled,
no hypotheses, verified retrieval and citations, and partial operational evidence.
Neither overview screenshot depicts that run. The README's demo video remains
planned; no final MP4 is linked or claimed.
