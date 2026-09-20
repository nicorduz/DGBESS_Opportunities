"""
ai_assistant.py — data-grounded chat over the Orennia buses + substations tables,
running on a FREE large-language-model API.

WHAT IT DOES
------------
Lets the team ask the data questions in plain English — "what's the best 115 kV node
in Massachusetts with the most headroom and the least congestion?", "which owner has
the most open capacity in Rhode Island?", "compare the top 5 buses near Worcester" —
and get an answer that reads the tables and reasons over the real numbers.

FREE BY DEFAULT
---------------
The module auto-detects whichever key you put in Settings → Secrets, in this order,
and ALL of the first three are free to sign up for:

    1. GEMINI_API_KEY     Google AI Studio   aistudio.google.com/app/apikey   (free tier, recommended)
    2. GROQ_API_KEY       Groq               console.groq.com/keys            (free tier, very fast Llama-3.3-70B)
    3. OPENROUTER_API_KEY OpenRouter         openrouter.ai/keys               (has :free models)
    4. OPENAI_API_KEY     OpenAI             (paid — optional fallback)

No key at all → the tab still renders and explains, in one line, how to switch it on.
Nothing else in the app depends on this module; if it fails to import, the app runs.

HOW THE ANSWER IS GROUNDED
--------------------------
Every question is answered against:
  • a compact SCHEMA (column meanings, from data_loader),
  • SUMMARY stats of the currently-filtered buses view (what the user is looking at),
  • the TOP rows of that view, plus
  • a keyword RETRIEVAL pass over the full dataset (so a place/owner the user names
    but hasn't filtered to is still pulled in).
The model is told to answer only from the rows it is shown and to say so when the
data doesn't cover something (e.g. NY headroom, which this ISO-NE export lacks).
"""
from __future__ import annotations

import json
import re
import pandas as pd
import streamlit as st

import data_loader as dl

# ── provider registry ─────────────────────────────────────────────────────────
# Each entry: secret key -> (human name, builder fn). Priority = order here.
_PROVIDERS = ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"]

_MODEL_DEFAULTS = {
    "GEMINI_API_KEY":     "gemini-2.0-flash",
    "GROQ_API_KEY":       "llama-3.3-70b-versatile",
    "OPENROUTER_API_KEY": "meta-llama/llama-3.3-70b-instruct:free",
    "OPENAI_API_KEY":     "gpt-4o-mini",
}
_PROVIDER_NAME = {
    "GEMINI_API_KEY": "Google Gemini (free)",
    "GROQ_API_KEY": "Groq Llama-3.3-70B (free)",
    "OPENROUTER_API_KEY": "OpenRouter (free)",
    "OPENAI_API_KEY": "OpenAI",
}


def _secret(key):
    try:
        return st.secrets.get(key)
    except Exception:
        return None


def active_provider() -> str | None:
    for k in _PROVIDERS:
        if _secret(k):
            return k
    return None


def is_available() -> tuple[bool, str]:
    try:
        import requests  # noqa
    except Exception as e:
        return False, f"`requests` is not installed ({e}). Add it to requirements.txt."
    if not active_provider():
        return False, (
            "No LLM key found. The assistant is **free** — add ONE of these under "
            "**Settings → Secrets** and reload:\n\n"
            "• `GEMINI_API_KEY` — get it free at aistudio.google.com/app/apikey  *(recommended)*\n"
            "• `GROQ_API_KEY` — free at console.groq.com/keys\n"
            "• `OPENROUTER_API_KEY` — openrouter.ai/keys (use a `:free` model)")
    return True, ""


# ── low-level calls (one per provider, all via requests) ───────────────────────
def _call_gemini(key, model, system, user, timeout=120):
    import requests
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1400},
    }
    r = requests.post(url, json=body, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
    data = r.json()
    return "".join(p.get("text", "")
                   for p in data["candidates"][0]["content"]["parts"])


def _call_openai_compatible(base, key, model, system, user, timeout=120, extra_headers=None):
    import requests
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    body = {"model": model, "temperature": 0.2, "max_tokens": 1400,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    r = requests.post(base, headers=headers, json=body, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"{base.split('//')[1].split('/')[0]} {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def _dispatch(system: str, user: str) -> tuple[str, str]:
    key_name = active_provider()
    key = _secret(key_name)
    model = _secret("LLM_MODEL") or _MODEL_DEFAULTS[key_name]
    if key_name == "GEMINI_API_KEY":
        return _call_gemini(key, model, system, user), _PROVIDER_NAME[key_name]
    if key_name == "GROQ_API_KEY":
        return _call_openai_compatible(
            "https://api.groq.com/openai/v1/chat/completions",
            key, model, system, user), _PROVIDER_NAME[key_name]
    if key_name == "OPENROUTER_API_KEY":
        return _call_openai_compatible(
            "https://openrouter.ai/api/v1/chat/completions",
            key, model, system, user,
            extra_headers={"HTTP-Referer": "https://nofar-grid.streamlit.app",
                           "X-Title": "Nofar Grid Intelligence"}), _PROVIDER_NAME[key_name]
    if key_name == "OPENAI_API_KEY":
        return _call_openai_compatible(
            "https://api.openai.com/v1/chat/completions",
            key, model, system, user), _PROVIDER_NAME[key_name]
    raise RuntimeError("No provider configured.")


# ── grounding: turn dataframes into a text context the model can reason over ────
SYSTEM_ROLE = """You are the grid-siting analyst for Nofar USA / BlueSky Utility.
You help screen where to site solar + battery storage projects by reading Orennia's
interconnection-capacity ("headroom") data for the electrical buses/nodes, plus a
physical substations reference table.

WHAT THE NUMBERS MEAN (use them precisely):
- 'Headroom (MW)' = remaining margin on the first binding constraint. Higher is better.
- 'Interconnection capacity (MW)' = MW you could inject before ANYTHING binds. This is
  the practical "how big can I build here" figure. Higher is better.
- 'Voltage (kV)' = bus voltage class. The siting sweet spot is MEDIUM voltage, i.e.
  ≤115 kV (commonly 69 kV and 115 kV; 27/33/69 kV in NYISO territory).
- 'Constraint loading (%)' near or above 100, 'Already overloaded' = true, or a large
  |shift factor| all mean MORE congestion / worse siting, even if headroom looks okay.
- 'Upgrade risk' High/Medium/Low = how hard/expensive relieving the constraint is.

KEY RELATIONSHIP (use it, and show the arithmetic when helpful):
  A project injecting P MW at a bus adds SF·P MW of flow to its binding constraint,
  where SF is the shift factor. Capacity is the P that exhausts the headroom H, so
      Interconnection capacity  C ≈ H / |SF|.
  Example phrasing: "headroom 850 MW with shift factor 0.52 → about 850/0.52 ≈ 1,630 MW
  can be injected before that constraint binds." A larger |SF| means less MW fits for the
  same headroom; a smaller |SF| means more fits.

HOW TO ANSWER:
1. Answer ONLY from the rows and stats provided below. They are the current, real data.
2. When ranking "best" nodes, weigh headroom AND capacity AND congestion (loading,
   overload flag, shift factor, upgrade risk) — not headroom alone — and say why.
3. Always name the bus (Bus Name), its voltage, headroom, capacity, county/state, owner,
   and the limiting constraint when you cite a node. Where it helps, show the H/|SF| math.
4. If the question asks about something the data does NOT cover (for example a region not
   present in the loaded export), say so plainly instead of guessing.
5. Be concise and specific. Lead with the answer, then a short 'why', then a compact list
   or table of the supporting buses. Note that all figures are Orennia estimates for the
   stated study case, not a guarantee of grantable capacity.
"""

_AI_COLS = [
    "Bus Name", dl.VOLTAGE_COL, dl.HEADROOM_COL, dl.CAPACITY_COL,
    "Constraint AC Loading Ratio (Percentage)", "Existing Overload Flag",
    "Shift Factor (Number)", "Risk Level", "Constraint Type",
    "Primary Limiting Constraint", "County", "State", "Owner",
]

# US state name -> abbreviation, for keyword retrieval on free-text questions.
_STATES = {"massachusetts": "MA", "rhode island": "RI", "connecticut": "CT",
           "maine": "ME", "new hampshire": "NH", "vermont": "VT",
           "new york": "NY", "mass": "MA"}


def _rows_to_text(df: pd.DataFrame, n: int) -> str:
    cols = [c for c in _AI_COLS if c in df.columns]
    view = df[cols].head(n).copy()
    for c in view.columns:
        if view[c].dtype.kind in "fc":
            view[c] = view[c].round(1)
    return view.to_csv(index=False)


def _summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "The current filtered view is EMPTY."
    L = [f"Rows in current filtered view: {len(df)}."]
    if dl.HEADROOM_COL in df:
        s = df[dl.HEADROOM_COL].describe()
        L.append(f"Headroom (MW): min {s['min']:.0f}, median {s['50%']:.0f}, "
                 f"max {s['max']:.0f}.")
    if dl.CAPACITY_COL in df:
        s = df[dl.CAPACITY_COL].describe()
        L.append(f"Interconnection capacity (MW): median {s['50%']:.0f}, max {s['max']:.0f}.")
    if "State" in df:
        vc = df["State"].value_counts().head(6)
        L.append("By state: " + ", ".join(f"{k}={v}" for k, v in vc.items()))
    if dl.VOLTAGE_COL in df:
        vc = df[dl.VOLTAGE_COL].value_counts().sort_index()
        L.append("By voltage (kV): " + ", ".join(f"{k:g}={v}" for k, v in vc.items()))
    return "\n".join(L)


def _retrieve(full: pd.DataFrame, question: str, n: int = 25) -> pd.DataFrame:
    """Pull rows the question hints at, even if outside the current filter."""
    if full.empty:
        return full
    q = question.lower()
    df = full
    # state mentions
    st_hits = {ab for name, ab in _STATES.items() if name in q}
    st_hits |= {m.upper() for m in re.findall(r"\b(ma|ri|ct|me|nh|vt|ny)\b", q)}
    if st_hits and "State" in df:
        sub = df[df["State"].isin(st_hits)]
        df = sub if len(sub) else df
    # voltage mentions e.g. "115kv", "69 kv"
    volts = [float(v) for v in re.findall(r"(\d{2,3})\s*kv", q)]
    if volts and dl.VOLTAGE_COL in df:
        sub = df[df[dl.VOLTAGE_COL].isin(volts)]
        df = sub if len(sub) else df
    # county mention (token match)
    if "County" in df.columns:
        counties = {c.lower(): c for c in df["County"].dropna().unique()}
        for cl, cc in counties.items():
            if cl in q:
                df = df[df["County"] == cc]
                break
    sort_col = dl.HEADROOM_COL if dl.HEADROOM_COL in df else df.columns[0]
    return df.sort_values(sort_col, ascending=False).head(n)


def build_context(view_df, full_df, subs_df, question) -> str:
    schema = "\n".join(
        f"- {dl.label(dl.BUS_COLUMNS, c)}: {dl.BUS_COLUMNS[c][1]}"
        for c in _AI_COLS if c in dl.BUS_COLUMNS)

    top_view = _rows_to_text(view_df.sort_values(
        dl.HEADROOM_COL, ascending=False) if dl.HEADROOM_COL in view_df else view_df, 30)
    retrieved = _retrieve(full_df, question, 25)
    ret_txt = _rows_to_text(retrieved, 25)

    subs_note = ""
    if subs_df is not None and not subs_df.empty:
        subs_note = (f"\nSUBSTATION REFERENCE TABLE also available "
                     f"({len(subs_df)} rows: name, min/max kV, owner, county, state, "
                     f"coordinates). Use it for physical/location questions.")

    return f"""COLUMN MEANINGS
{schema}
{subs_note}

SUMMARY OF THE USER'S CURRENT FILTERED VIEW
{_summary(view_df)}

TOP BUSES IN THE CURRENT FILTERED VIEW (CSV, highest headroom first)
{top_view}

ADDITIONAL BUSES RETRIEVED FROM THE FULL DATASET MATCHING THE QUESTION (CSV)
{ret_txt}

USER QUESTION
{question}
"""


SUGGESTED = [
    "What are the best 115 kV nodes in Massachusetts by headroom, and how congested are they?",
    "Rank the top 5 buses under 115 kV with the most interconnection capacity.",
    "Which transmission owner has the most open headroom in Rhode Island?",
    "Show me low-risk buses with headroom over 400 MW and explain the trade-offs.",
    "For a 200 MW storage project, which buses look siteable and why?",
]


# ── UI ─────────────────────────────────────────────────────────────────────────
def render_chat(view_df, full_df, subs_df):
    st.markdown("#### \U0001F916 Ask the data")
    ok, reason = is_available()
    prov = active_provider()
    if prov:
        st.caption(f"Model in use: **{_PROVIDER_NAME[prov]}** · answers are grounded in the "
                   f"{len(view_df)} buses currently in your filtered view + keyword lookups "
                   f"across all {len(full_df)} buses.")
    if not ok:
        st.info(reason)
        return

    st.session_state.setdefault("ai_hist", [])

    if not st.session_state["ai_hist"]:
        st.caption("Try one of these:")
        cols = st.columns(2)
        for i, qsug in enumerate(SUGGESTED):
            if cols[i % 2].button(qsug, key=f"sq_{i}", use_container_width=True):
                st.session_state["ai_pending"] = qsug
                st.rerun()

    for m in st.session_state["ai_hist"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    q = st.chat_input("Ask about headroom, congestion, best nodes, owners, counties…")
    if not q and st.session_state.get("ai_pending"):
        q = st.session_state.pop("ai_pending")

    if q:
        st.session_state["ai_hist"].append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("Reading the tables…"):
                try:
                    ctx = build_context(view_df, full_df, subs_df, q)
                    text, prov_name = _dispatch(SYSTEM_ROLE, ctx)
                    st.markdown(text)
                    st.caption(f"Answered by {prov_name} · grounded in your filtered data")
                    st.session_state["ai_hist"].append(
                        {"role": "assistant", "content": text})
                except Exception as e:
                    st.error(f"LLM error: {e}")
                    st.caption("If a model name was rejected, set `LLM_MODEL` in Secrets to a "
                               "current model id for your provider.")
