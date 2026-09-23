# Conference Intelligence Assistant

IQ Hack 2026 — Problem Statement 2 (idea owner: Bashar Hamad).

Consultants photograph posters, sit through sessions and take notes all day, then
spend hours after the conference closes turning it into a client debrief. This tool
collapses that second job: capture material, review the extracted intelligence, and
generate a client-tailored Word debrief.

## Run it

```powershell
.\run.ps1
```

First run creates `.venv` and installs dependencies (~5 min). After that it opens on
http://localhost:8501.

**No API key is required.** The app ships in `mock` mode, which returns realistic
stand-in intelligence so every screen is usable. Switch to a real provider on the
**Setup** page when credentials arrive — nothing else changes.

`.streamlit/config.toml` hides the Deploy button and dev menu so they cannot appear
mid-demo, and raises the upload limit to 400 MB for slide decks. Do not deploy this
to Streamlit Community Cloud without clearing it with the hackathon organisers —
the code and mock data reference internal material.

## Walkthrough

1. **Setup** — pick a model provider, define client profiles, load the demo dataset.
2. **Capture** — upload photos, `.pptx`, `.pdf`, `.docx`, `.txt`, or shoot a poster with the camera.
3. **Insights** — review, filter, edit and approve extracted cards.
4. **Debrief** — generate the client Word document, email draft, and answers to standing questions.
5. **Ask** — question the whole conference, with the source poster shown for every answer.

## How it works

Everything ingested becomes an **InsightCard**: company, asset, indication, trial,
phase, data points, key message, KOL quote, themes, confidence, source reference.
Once the conference is a table of cards, debriefs, Q&A, client tailoring and
year-over-year comparison are all just operations over that table.

Poster photos go to a vision model rather than classic OCR — multi-column poster
layouts and chart labels survive intact, which Tesseract reliably destroys.

```
core/
  schema.py     InsightCard, ClientProfile, Debrief
  config.py     settings, provider selection, paths
  llm.py        provider-agnostic: mock | openai | azure | gemini
  mockdata.py   deterministic stand-in content for offline work
  ingest.py     file -> Artifact (per slide, per page, per photo)
  extract.py    Artifact -> InsightCard
  store.py      SQLite persistence + TF-IDF retrieval
  synth.py      client relevance, debriefs, Q&A, historical delta
  docx_out.py   Word and email export
app.py, pages/  Streamlit UI (thin — all logic lives in core/)
```

`core/` has no Streamlit dependency, so the UI is replaceable.

## Sharing on the local network

```powershell
.\share.ps1
```

Streamlit's own "Network URL" is unreliable on a machine with a corporate VPN — it
often advertises the VPN adapter, which no other device can route to. `share.ps1`
filters those out and prints the address that actually works, then checks the
firewall and the running process. Re-run it whenever you change networks.

Some corporate and conference WiFi networks enable client isolation, which blocks
device-to-device traffic at the access point. If nothing works on the venue network,
that is why, and there is no fix from this side.

## Deploying to Azure

```powershell
.\deploy_azure.ps1 -AppName iqhack-conf-intel -RestrictToTenant
```

Creates an App Service plan and web app, enables WebSockets (Streamlit will not work
without this), and deploys. Always pass `-RestrictToTenant` unless you intend the app
to be open to the internet — without it anyone with the URL can upload files and spend
your API credits.

Set the API key as an app setting rather than committing it:

```powershell
az webapp config appsettings set -n <app> -g rg-iqhack-conf-intel --settings AZURE_OPENAI_API_KEY=<key>
```

`CI_DATA_DIR=/home/data` is set automatically because `/home` is the only path on App
Service that survives a restart. The SQLite database still resets if you recreate the
app, so reload the demo dataset after redeploying.

Vercel and Netlify cannot host this. Streamlit needs a long-running process holding an
open WebSocket per session; those platforms run short-lived stateless functions.

## Tests

```powershell
.\.venv\Scripts\python.exe smoke_test.py    # core pipeline end to end
.\.venv\Scripts\python.exe ingest_test.py   # every file parser
.\.venv\Scripts\python.exe ui_test.py       # every page renders headlessly
```

## Design decisions worth defending in the demo

- **Human-in-the-loop approval.** Nothing reaches a client deliverable without a
  consultant approving the card. Raw model output going straight to a pharma client
  is not a product anyone would buy.
- **Traceability.** Every sentence in the debrief carries a card id, and the Word
  appendix reproduces the source evidence including the original photo.
- **Unpublished flag.** Booth-only material and private conversations are marked and
  segregated into their own debrief section, because circulating non-public data to a
  client without a warning is a real compliance problem.
- **Client tailoring.** The same day's cards produce visibly different documents for
  different clients. The Debrief page can render two side by side.
- **Mock mode.** The app is fully demoable with no network. This is the demo-day
  insurance policy.
