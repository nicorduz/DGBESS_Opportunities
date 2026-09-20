# Nofar USA · Grid Interconnection Intelligence

A Streamlit application that turns Orennia's **Greenfield Interconnection Capacity
(Buses)** and **Substations** exports into a siting decision tool: map where solar +
storage can interconnect most easily by **headroom, capacity and congestion**, filter by
every physical and grid parameter, find the nearest medium-voltage node to any point, and
**query the data in plain English** with a free LLM — all behind a branded login.

## Capabilities

1. **Screen & map** — filter buses by state, county, transmission owner, voltage class,
   headroom, interconnection capacity, upgrade risk, constraint type, constraint loading,
   shift factor and overload flag; view them on a map colored by headroom / capacity /
   congestion; export the result (names, coordinates, all parameters) to CSV. A one-click
   preset returns the medium-voltage, high-headroom shortlist.
2. **Nearest-node lookup** — enter coordinates *or* an address and get the closest buses
   (with headroom) and the closest physical substations (names + coordinates), on a map.
3. **Ask the data** — a data-grounded assistant, running on a free LLM, that reads the
   tables and answers questions with the real numbers.

The app is driven entirely by the column registry in `data_loader.py`, so an export from
any ISO/RTO in the same schema works with no code changes.

---

## Contents

```
nofar-grid/
├── app.py               # map & screen, nearest-node lookup, assistant, data dictionary
├── auth.py              # branded username/password gate (SHA-256 hashes in secrets)
├── ai_assistant.py      # free-LLM "Ask the data" chat, grounded in the tables
├── data_loader.py       # load/clean/cache CSVs + the column registry (labels & meanings)
├── requirements.txt
├── .gitignore
├── README.md
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example   # copy to secrets.toml and fill in
├── assets/
│   └── README.txt            # drop nofar_logo.png here
└── data/
    ├── buses.csv             # Greenfield Interconnection Capacity (Buses)
    └── substations.csv       # Substations reference layer
```

---

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # optional; see below
streamlit run app.py
```

Without a `secrets.toml` the app runs in **dev mode** (no login), so a fresh clone works
immediately. Add secrets to switch on the login and the assistant.

---

## Deploy on Streamlit Community Cloud (free)

1. Push this folder to a **GitHub** repo (public or private).
2. At <https://share.streamlit.io> → **New app** → select the repo, branch and `app.py`.
3. Open **⋮ → Settings → Secrets** and paste the contents of your `secrets.toml`
   (login hashes + one LLM key). Save — the app reboots and is live.
4. To refresh data later, replace the CSVs in the repo **or** upload a new export in the
   sidebar at runtime.

> The `data/` CSVs are committed so the app works out of the box. If the data licence
> forbids committing it, remove the files from the repo (or use a private repo) and upload
> the exports in the sidebar each session.

---

## Login

Only SHA-256 password hashes are stored, never the passwords:

```bash
python auth.py 'ChooseAStrongPassword'      # prints the hash
```

```toml
[auth]
analyst = "the-hash-you-just-printed"
lead    = "another-hash"

[auth_meta]
company  = "Nofar USA · BlueSky Utility"
title    = "Grid Interconnection Intelligence"
subtitle = "Headroom, congestion & siting"
```

Drop a logo at `assets/nofar_logo.png` for the login screen, sidebar and hero (a clean
wordmark shows if it is missing).

---

## Connecting the assistant (free LLM)

The **Ask the data** tab auto-detects whichever key you add to secrets — **the first
three are free to obtain**:

| Secret key            | Provider   | Get a free key                                  | Default model                            |
|-----------------------|------------|-------------------------------------------------|------------------------------------------|
| `GEMINI_API_KEY`      | Google     | aistudio.google.com/app/apikey  *(recommended)* | `gemini-2.0-flash`                       |
| `GROQ_API_KEY`        | Groq       | console.groq.com/keys                           | `llama-3.3-70b-versatile`                |
| `OPENROUTER_API_KEY`  | OpenRouter | openrouter.ai/keys                              | `meta-llama/llama-3.3-70b-instruct:free` |
| `OPENAI_API_KEY`      | OpenAI     | platform.openai.com  *(paid)*                   | `gpt-4o-mini`                            |

```toml
GEMINI_API_KEY = "your-free-key"
# LLM_MODEL = "gemini-2.0-flash"   # optional override for any provider
```

**Grounding.** Every question is answered against the rows currently in the *Headroom map*
filter, a summary of that view, and a keyword lookup across the full dataset (so a
county/owner named but not filtered to is still pulled in). The model is instructed to
answer only from those rows and to state when the data does not cover something. It is a
screening aid, not a guarantee of grantable capacity.

---

## How the numbers relate

The three headline figures are tied together by the **shift factor (SF)** — the fraction
of power injected at a bus that appears as extra flow on its binding constraint:

```
ΔFlow_constraint = SF · P_inject
Interconnection capacity   C  ≈  Headroom (H)  ÷  |SF|
```

A project injecting `P` MW adds `SF·P` MW to the constraint; capacity is the `P` that
exhausts the headroom, i.e. `C = H / |SF|` (this identity reproduces the reported capacity
for ~91% of nodes in the dataset). **Constraint loading (%)** and the **overload flag**
show how loaded the element already is, and **upgrade risk** shows how hard it would be to
unlock more than `C`. The app's **Data dictionary** tab shows the full definitions plus a
live worked example computed from the loaded data.

Screening rule of thumb: **high headroom + low |shift factor| + low constraint loading +
low upgrade risk = the most siteable node.**

---

## The data, briefly

**Buses (analytical core)** — one row per bus/node per binding condition: headroom,
interconnection capacity, voltage, shift factor, constraint loading, overload flag,
upgrade risk, limiting constraint, contingency, county, state, owner, coordinates and
study metadata. The loader drops only *exact* duplicate rows; a bus that appears more than
once because it has two different limiting constraints is kept on purpose.

**Substations** — physical reference layer (name, min/max kV, owner, county, state,
coordinates) used by the nearest-node lookup and the optional map overlay.

## Regional coverage

The sample buses/headroom export covers **ISO-NE**. Because the app reads its schema from
`data_loader.py`, exporting the equivalent Greenfield Interconnection Capacity for another
ISO/RTO and saving it as `data/buses.csv` (or uploading it in the sidebar) extends the
map, filters, lookup and assistant to that region with no code changes.
