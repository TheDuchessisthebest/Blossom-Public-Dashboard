# Blossom public dashboard

Deploy `app.py` using Python 3.12 on Streamlit Community Cloud. No API keys or
secrets are required. This repository must contain ONLY this deployment bundle,
never the local bot project or its private_trading folder.

The public collector fetches verified market metadata, order-book prices and
official settlements directly from the public Polymarket US API while the app
is running. It never connects to an account or places orders. Original main-call
thresholds are preserved. Missing or stale quotes are never treated as live.

Included seed data contains public market observations, calls and verified
outcomes only. There are no balances, transactions, credentials or model weights.
AI history/training metrics are historical public snapshots; this cloud viewer
does not retrain or execute the private AI bot. The local paper study, private
trade ledger and sealed test outcomes remain on the PC.

Free Community Cloud may sleep after inactivity; visitors can wake it. It does
not guarantee continuous collection or uptime. Runtime SQLite updates may be
lost after a reboot/redeploy; the public seed is restored in that case. This
hosting is a public viewer, not an always-on trading or research worker.
