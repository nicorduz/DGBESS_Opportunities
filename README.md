# Nofar USA · Grid Interconnection Intelligence

A Streamlit app that turns Orennia's **Greenfield Interconnection Capacity (Buses)**
and **Substations** exports into a decision tool: map the best places to site solar +
storage by **headroom, capacity and congestion**, filter by every physical and grid
parameter, look up the nearest medium-voltage node to any point, and **ask the data
questions in plain English** with a free LLM. Behind a Nofar-branded login.

Built to answer Bill Hilliard's three asks:

1. **Screen a state by voltage + headroom** — names, coordinates and every congestion
   parameter. One click gives the Massachusetts 69/115 kV · >600 MW list (⭐ preset).
2. **Nearest medium-voltage headroom** — type coordinates *or* an address, get the
   closest buses (with headroom) and substations.
3. **Any state the data covers** — the same engine screens New York (Westchester, at
   27/33/69 kV) the moment a NYISO export is dropped in. *(See the note at the bottom —
   the sample export is ISO-NE only.)*

---

## What's in the box

```
nofar-grid/
├── app.py               # main app: map & screen, nearest-node lookup, AI, data dictionary
├── auth.py              # Nofar-branded username/password gate (SHA-256 hashes in secrets)
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
    ├── buses.csv             # Orennia Greenfield Interconnection Capacity (Buses)
    └── substations.csv       # Substations reference layer
```

---

## Run it locally

```bash
# 1) clone your repo, then:
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) (optional but recommended) configure secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
#    edit the file — see "Login" and "Free LLM" below

# 3) launch
streamlit run app.py
```

Without a `secrets.toml` the app runs in **dev mode** (no login) so a fresh clone works
immediately. Add secrets to switch the login and the AI on.

---

## Deploy on Streamlit Community Cloud (free)

1. Push this folder to a **GitHub** repo (public or private).
2. Go to <https://share.streamlit.io> → **New app** → pick the repo, branch and `app.py`.
3. Open **⋮ → Settings → Secrets** and paste the contents of your `secrets.toml`
   (login hashes + one LLM key). Save — the app reboots.
4. Done. Data ships in `./data`, so it's live on first boot. To refresh the data later,
   either replace the CSVs in the repo **or** upload a new export in the sidebar.

> The `data/` CSVs are committed so the app works out of the box. If your Orennia licence
> forbids committing the data, delete them from the repo and instead upload the exports in
> the sidebar each session (or use a private repo).

---

## Login

Passwords are never stored — only their SHA-256 hashes, in secrets.

```bash
python auth.py 'ChooseAStrongPassword'      # prints the hash
```

Put the hash in `secrets.toml`:

```toml
[auth]
niko = "the-hash-you-just-printed"
bill = "another-hash"

[auth_meta]
company  = "Nofar USA · BlueSky Utility"
title    = "Grid Interconnection Intelligence"
subtitle = "Headroom, congestion & siting — ISO-NE / Northeast"
```

Drop your logo at `assets/nofar_logo.png` for the login screen, sidebar and hero (a clean
wordmark shows if it's missing).

---

## Free LLM for "Ask the data"

The assistant auto-detects whichever key you add — **the first three are free**:

| Secret key            | Provider   | Get a free key                                | Default model                         |
|-----------------------|------------|-----------------------------------------------|---------------------------------------|
| `GEMINI_API_KEY`      | Google     | aistudio.google.com/app/apikey  *(recommended)* | `gemini-2.0-flash`                    |
| `GROQ_API_KEY`        | Groq       | console.groq.com/keys                         | `llama-3.3-70b-versatile`             |
| `OPENROUTER_API_KEY`  | OpenRouter | openrouter.ai/keys                            | `meta-llama/llama-3.3-70b-instruct:free` |
| `OPENAI_API_KEY`      | OpenAI     | (paid) platform.openai.com                    | `gpt-4o-mini`                         |

```toml
GEMINI_API_KEY = "your-free-key"
# LLM_MODEL = "gemini-2.0-flash"   # optional override
```

**How answers stay accurate.** Every question is answered against the rows currently in
your *Headroom map* filter, a summary of that view, and a keyword lookup across the full
dataset (so a county/owner you name but haven't filtered to is still pulled in). The model
is instructed to answer only from those rows and to say when the data doesn't cover
something. It's a screening aid, not a guarantee of grantable capacity.

Example questions: *"best 115 kV nodes in Massachusetts by headroom, and how congested
are they?"* · *"top 5 buses under 115 kV with the most capacity"* · *"which owner has the
most open headroom in Rhode Island?"* · *"for a 200 MW storage project, which buses look
siteable and why?"*

---

## The data, briefly

**Buses (the analytical core).** One row per bus/node per binding condition:

- **Headroom (MW)** — margin on the first binding constraint (higher = better).
- **Interconnection capacity (MW)** — MW you can inject before *anything* binds.
- **Voltage (kV)** — bus class; medium-voltage siting = ≤115 kV.
- **Constraint loading (%) / Already overloaded / Shift factor / Upgrade risk** — the
  congestion picture. High loading, an overload flag or a large |shift factor| mean a
  tighter site even when headroom looks fine.
- Plus limiting constraint, contingency, county, state, owner, coordinates and the study
  metadata. Full definitions live in the app's **Data dictionary** tab.

**Substations** — physical reference layer (name, min/max kV, owner, county, state,
coordinates) for the nearest-node lookup and the optional map overlay.

The loader drops only *exact* duplicate rows; a bus that appears more than once because it
has two different limiting constraints is kept on purpose.

---

## ⚠️ Coverage note (Bill's NY / Westchester ask)

The sample **buses/headroom export is ISO-NE only** (MA, ME, RI, NH, CT, VT). New York /
Westchester headroom is therefore **not** in this file, so the app can't report NY nodes
yet. The substations layer *does* include NY, so names/coordinates are available there —
but headroom is not. **The moment you export a NYISO "Greenfield Interconnection
Capacity" from Orennia and drop it into the sidebar (or save it as `data/buses.csv`), the
map, filters, lookup and AI all cover New York with no code changes**, because the app is
driven entirely by the column registry in `data_loader.py`.
