"""
auth.py — branded sign-in gate for the Nofar Grid Interconnection Intelligence app.

Credentials live in st.secrets as SHA-256 hashes, never in git:

    [auth]
    analyst = "<sha256 of the password>"   # python auth.py 'yourpassword'
    lead    = "<sha256 of the password>"

    [auth_meta]
    company  = "Nofar USA · BlueSky Utility"
    title    = "Grid Interconnection Intelligence"
    subtitle = "Headroom, congestion & siting — ISO-NE / Northeast"

If the [auth] block is absent the app runs in dev mode with no gate, so a fresh
clone works before secrets are configured.
"""
from __future__ import annotations
import base64
import hashlib
from pathlib import Path

import streamlit as st

# Nofar brand tokens
INDIGO = "#4A2EE3"
DEEP   = "#2B1B8F"
GOLD   = "#F4C843"
INK    = "#17153A"
PAPER  = "#F2F1F7"


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def _sect(name: str) -> dict:
    """Read a secrets section, tolerating a completely absent secrets.toml (dev mode)."""
    try:
        return dict(st.secrets.get(name, {}))
    except Exception:
        return {}


def _check(user: str, pw: str) -> bool:
    stored = _sect("auth").get(user)
    return bool(stored) and _hash(pw) == stored


def _logo_b64() -> str:
    for p in ("assets/nofar_logo.png", "assets/logo.png"):
        f = Path(p)
        if f.exists():
            try:
                return base64.b64encode(f.read_bytes()).decode()
            except Exception:
                pass
    return ""


def current_user():
    return st.session_state.get("_auth_user")


def logout():
    st.session_state.pop("_auth_user", None)
    st.rerun()


def _styles():
    st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');
.stApp {{ background:{PAPER}; }}
#MainMenu, footer, header[data-testid="stHeader"] {{ visibility:hidden; }}
.block-container {{ padding-top:3.5rem; max-width:560px; }}

/* logo plate */
.nf-logo {{ background:#fff; border-radius:20px; padding:26px 30px; text-align:center;
  box-shadow:0 10px 34px rgba(43,27,143,.13); margin-bottom:34px; }}
.nf-logo img {{ max-height:88px; max-width:100%; }}
.nf-logo .fallback {{ font-family:'Space Grotesk'; font-size:44px; font-weight:700;
  color:{INDIGO}; letter-spacing:-.02em; }}
.nf-logo .fallback sup {{ font-size:17px; vertical-align:super; }}

/* wordmark block */
.nf-eyebrow {{ font-family:'Inter'; font-size:15px; color:#6B668F; margin-bottom:2px; }}
.nf-title {{ font-family:'Space Grotesk'; font-size:38px; font-weight:700; color:{INK};
  letter-spacing:-.02em; line-height:1.1; margin:0 0 6px; }}
.nf-sub {{ font-family:'Inter'; font-size:16px; color:#4A4670; margin-bottom:22px; }}
.nf-rule {{ height:6px; width:120px; border-radius:99px; margin-bottom:26px;
  background:repeating-linear-gradient(45deg,{GOLD} 0 10px,{INDIGO} 10px 20px); }}

/* form */
div[data-testid="stForm"] {{ background:#fff; border:1px solid #E6E2FA; border-radius:18px;
  padding:22px 24px 6px; box-shadow:0 6px 22px rgba(43,27,143,.07); }}
div[data-testid="stForm"] label {{ font-family:'Inter'; font-weight:600; color:{INK};
  font-size:13.5px; }}
div[data-testid="stForm"] input {{ border-radius:10px !important; }}
div[data-testid="stForm"] button {{ width:100%; background:{INDIGO}; color:#fff; border:none;
  border-radius:10px; font-family:'Inter'; font-weight:600; padding:10px 0; font-size:15px; }}
div[data-testid="stForm"] button:hover {{ background:{DEEP}; color:{GOLD}; }}
.nf-foot {{ text-align:center; color:#8A85AD; font-size:12px; margin-top:22px;
  font-family:'Inter'; }}
</style>""", unsafe_allow_html=True)


def require_login():
    """Blocks the app until a valid sign-in. Returns the username."""
    if st.session_state.get("_auth_user"):
        return st.session_state["_auth_user"]

    users = _sect("auth")
    if not users:                       # dev mode: no credentials configured yet
        st.session_state["_auth_user"] = "dev"
        return "dev"

    meta = _sect("auth_meta")
    _styles()

    b64 = _logo_b64()
    logo_html = (f'<img src="data:image/png;base64,{b64}">' if b64
                 else '<div class="fallback">Nofar<sup>USA</sup></div>')
    st.markdown(f'<div class="nf-logo">{logo_html}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="nf-eyebrow">{meta.get("company", "Nofar USA · BlueSky Utility")}</div>'
        f'<div class="nf-title">{meta.get("title", "Grid Interconnection Intelligence")}</div>'
        f'<div class="nf-sub">{meta.get("subtitle", "Headroom, congestion & siting — ISO-NE / Northeast")}</div>'
        f'<div class="nf-rule"></div>', unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        u = st.text_input("Username", placeholder="your username")
        p = st.text_input("Password", type="password", placeholder="\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022")
        ok = st.form_submit_button("Sign in")

    if ok:
        if _check(u.strip(), p):
            st.session_state["_auth_user"] = u.strip()
            st.rerun()
        else:
            st.error("Incorrect username or password.")

    st.markdown('<div class="nf-foot">Authorized personnel only \u00b7 '
                'Contains licensed third-party data (Orennia)</div>', unsafe_allow_html=True)
    st.stop()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(_hash(sys.argv[1]))
    else:
        print("usage: python auth.py <password>")
