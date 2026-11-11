"""
SullApps Suite - Shared Python UI Helper Module
Sullair Argentina S.A.

Provides standardized enterprise styling, contextual loading spinners powered by
`shared/quotes/loading_quotes.json`, celebration notifications, and unified
Single Sign-On (SSO) verification across all SullApps.
"""

import os
import json
import html
import hmac
import hashlib
import time
import random
from contextlib import contextmanager
import streamlit as st

SULLAIR_PRIMARY = "#006837"
SULLAIR_DARK = "#004D26"
SULLAIR_LIGHT = "#E6F4EA"
SULLAIR_BG = "#F8F9FA"
SULLAIR_CARD = "#FFFFFF"
SULLAIR_TEXT = "#1F2937"

DEFAULT_SSO_SECRET = "SullApps_Enterprise_SSO_Secret_Key_2026_FedeCendra"

DEFAULT_QUOTES = {
    "general": [
        "Cebando un mate mientras bajan los datos...",
        "Ajustando tuercas y revisando niveles...",
        "Validando que todo esté 10 impecable...",
    ],
    "scraping": [
        "Peleando con el login de Worklift (vamos ganando)...",
        "Buscando la póliza en el servidor...",
        "Cazando certificados (es temporada!)...",
    ],
    "reports": [
        "Armando el paquete de documentación flama 🔥...",
        "Firmando digitalmente y foliando hojas...",
        "Dejando todo prístino para salir...",
    ],
}


def _resolve_quotes_paths() -> list[str]:
    """Return candidate paths for loading_quotes.json in priority order."""
    here = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()
    return [
        os.path.normpath(os.path.join(here, "..", "..", "shared", "quotes", "loading_quotes.json")),
        os.path.normpath(os.path.join(here, "..", "shared", "quotes", "loading_quotes.json")),
        os.path.normpath(os.path.join(here, "quotes", "loading_quotes.json")),
        os.path.normpath(os.path.join(cwd, "shared", "quotes", "loading_quotes.json")),
        os.path.normpath(os.path.join(cwd, "..", "..", "shared", "quotes", "loading_quotes.json")),
        os.path.normpath(os.path.join(here, "loading_quotes.json")),
    ]


def _resolve_users_access_paths() -> list[str]:
    """Return candidate paths for shared/users_access.json."""
    here = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()
    return [
        os.path.normpath(os.path.join(here, "..", "..", "shared", "users_access.json")),
        os.path.normpath(os.path.join(here, "..", "shared", "users_access.json")),
        os.path.normpath(os.path.join(cwd, "shared", "users_access.json")),
        os.path.normpath(os.path.join(cwd, "..", "..", "shared", "users_access.json")),
    ]


def _get_sso_secret() -> str:
    """Resolve SSO HMAC secret from users_access.json, st.secrets, or default."""
    for candidate in _resolve_users_access_paths():
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("sso_secret"):
                    return str(data["sso_secret"])
            except Exception:
                continue
    try:
        if hasattr(st, "secrets") and "SSO_SECRET" in st.secrets:
            return str(st.secrets["SSO_SECRET"])
    except Exception:
        pass
    return DEFAULT_SSO_SECRET


def verify_sullapps_sso(max_age_seconds: int = 86400) -> dict | None:
    """
    Verifies the HMAC-SHA256 signed SSO parameters passed by the SullApps Hub
    (`sso_user`, `sso_role`, `sso_name`, `sso_ts`, `sso_sig`).
    Caches valid identity in `st.session_state['_sullapps_sso_payload']`.
    """
    cached = st.session_state.get("_sullapps_sso_payload")
    if isinstance(cached, dict) and cached.get("username"):
        return cached

    try:
        qp = st.query_params
        sso_user = str(qp.get("sso_user", "")).strip()
        sso_role = str(qp.get("sso_role", "")).strip()
        sso_name = str(qp.get("sso_name", "")).strip()
        sso_ts = str(qp.get("sso_ts", "")).strip()
        sso_sig = str(qp.get("sso_sig", "")).strip()
    except Exception:
        return None

    if not sso_user or not sso_ts or not sso_sig:
        return None

    try:
        ts_int = int(sso_ts)
        now = int(time.time())
        if abs(now - ts_int) > max_age_seconds:
            return None
    except ValueError:
        return None

    secret = _get_sso_secret()
    payload_str = f"{sso_user}|{sso_role}|{sso_ts}"
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, sso_sig):
        return None

    identity = {
        "username": sso_user,
        "role": sso_role or "user",
        "display_name": sso_name or sso_user,
    }
    st.session_state["_sullapps_sso_payload"] = identity
    return identity


def clear_sullapps_sso() -> None:
    """Clears cached SullApps SSO session state."""
    st.session_state.pop("_sullapps_sso_payload", None)


def render_sullapps_portal_notice(portal_url: str = "https://sullapps.fedev.com.ar/default.php") -> None:
    """
    Renders a clean banner reminding users that SullApps uses unified login at the main portal.
    """
    safe_url = html.escape(portal_url)
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%);
            border: 1px solid #86EFAC;
            border-left: 5px solid #006837;
            border-radius: 10px;
            padding: 14px 18px;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        ">
            <div style="font-size: 0.9rem; color: #064E3B; line-height: 1.4;">
                <strong>🔐 Acceso Unificado SullApps:</strong> Ingresá desde el portal principal con tu clave única para acceder automáticamente a todas tus aplicaciones habilitadas.
            </div>
            <a href="{safe_url}" target="_top" style="
                background: #006837;
                color: #FFFFFF;
                text-decoration: none;
                font-weight: 700;
                font-size: 0.84rem;
                padding: 8px 14px;
                border-radius: 8px;
                white-space: nowrap;
                box-shadow: 0 2px 6px rgba(0, 104, 55, 0.2);
            ">Ir a SullApps Hub →</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def load_quotes_dict() -> dict[str, list[str]]:
    """
    Loads `loading_quotes.json` dynamically from disk on every call so live edits
    are reflected immediately without restarting the server. Falls back to DEFAULT_QUOTES.
    """
    for candidate in _resolve_quotes_paths():
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
            except Exception:
                continue
    return DEFAULT_QUOTES


def get_loading_quote(task_type: str = "default") -> str:
    """
    Returns a random contextual quote for the given `task_type`
    ('general', 'scraping', 'reports', or 'default').
    """
    quotes_map = load_quotes_dict()
    normalized = (task_type or "default").strip().lower()
    if normalized == "default":
        normalized = "general"

    bucket = quotes_map.get(normalized) or quotes_map.get("general") or DEFAULT_QUOTES["general"]
    if not isinstance(bucket, list) or not bucket:
        bucket = DEFAULT_QUOTES["general"]

    return str(random.choice(bucket))


@contextmanager
def sullapps_spinner(task_type: str = "default", custom_prefix: str = ""):
    """
    Context manager that reads `loading_quotes.json` (with built-in fallback)
    and displays `st.spinner(...)` with a fun/relatable Sullair quote.
    """
    quote = get_loading_quote(task_type)
    display_text = f"{custom_prefix} — {quote}" if custom_prefix else quote
    with st.spinner(display_text):
        yield quote


def celebrate_success(message: str, subtitle: str = "", use_balloons: bool = True) -> None:
    """
    Triggers st.balloons() + st.toast() and renders a polished Sullair Enterprise success card.
    """
    if use_balloons:
        try:
            st.balloons()
        except Exception:
            pass

    try:
        st.toast(message, icon="🎉")
    except Exception:
        pass

    safe_msg = html.escape(str(message))
    safe_sub = html.escape(str(subtitle)) if subtitle else ""
    sub_html = f'<p style="margin: 6px 0 0 0; color: #065F46; font-size: 0.92rem;">{safe_sub}</p>' if safe_sub else ""

    st.markdown(
        f"""
        <div class="sullapps-celebration-card" style="
            background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
            border: 1.5px solid #10B981;
            border-left: 6px solid #006837;
            border-radius: 12px;
            padding: 16px 20px;
            margin: 12px 0;
            box-shadow: 0 4px 14px rgba(0, 104, 55, 0.10);
            display: flex;
            align-items: center;
            gap: 14px;
        ">
            <div style="
                width: 42px;
                height: 42px;
                border-radius: 10px;
                background: #006837;
                color: #FFFFFF;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.35rem;
                flex-shrink: 0;
            ">✅</div>
            <div style="flex-grow: 1;">
                <div style="font-weight: 800; font-size: 1.05rem; color: #064E3B; line-height: 1.3;">
                    {safe_msg}
                </div>
                {sub_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def inject_custom_css() -> None:
    """
    Polishes cards, buttons, tabs, tables, and form controls to match Sullair Enterprise style,
    and hides redundant Streamlit default headers/footers for clean iframe & standalone rendering.
    """
    st.markdown(
        """
        <style>
        /* =====================================================================
           SULLAPPS SUITE - ENTERPRISE STREAMLIT THEME & UI POLISH
           Primary: #006837 | Surface: #FFFFFF | Background: #F8F9FA
           ===================================================================== */
        :root {
            --sullapps-green: #006837;
            --sullapps-green-hover: #004D26;
            --sullapps-green-soft: #E6F4EA;
            --sullapps-bg: #F8F9FA;
            --sullapps-surface: #FFFFFF;
            --sullapps-text: #1F2937;
            --sullapps-border: #E5E7EB;
        }

        /* Hide redundant Streamlit chrome (footer, deploy button, menu, decoration bar) */
        #MainMenu,
        footer,
        [data-testid="stFooter"],
        [data-testid="stDecoration"],
        .stDeployButton,
        [data-testid="stAppDeployButton"],
        [data-testid="stToolbarActions"] {
            display: none !important;
        }

        /* Keep header minimal & transparent so sidebar toggle remains clickable */
        header[data-testid="stHeader"] {
            background: transparent !important;
            height: 2.5rem !important;
            pointer-events: none;
        }
        header[data-testid="stHeader"] button,
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapseButton"] {
            pointer-events: auto !important;
        }

        /* Clean container spacing for embedded & full-screen views */
        .block-container {
            padding-top: 1.75rem !important;
            padding-bottom: 2.5rem !important;
        }

        /* Primary Action Buttons */
        button[kind="primary"],
        button[data-testid="stBaseButton-primary"],
        button[data-testid="baseButton-primary"],
        .stFormSubmitButton > button[kind="primary"] {
            background: linear-gradient(135deg, #006837 0%, #00522B 100%) !important;
            border-color: #006837 !important;
            color: #FFFFFF !important;
            font-weight: 700 !important;
            border-radius: 8px !important;
            box-shadow: 0 2px 6px rgba(0, 104, 55, 0.18) !important;
            transition: all 0.18s ease !important;
        }
        button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover,
        button[data-testid="baseButton-primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #007F43 0%, #006837 100%) !important;
            border-color: #004D26 !important;
            box-shadow: 0 4px 12px rgba(0, 104, 55, 0.28) !important;
            transform: translateY(-1px);
        }

        /* Secondary Buttons */
        button[kind="secondary"],
        button[data-testid="stBaseButton-secondary"] {
            border-radius: 8px !important;
            font-weight: 600 !important;
            border: 1px solid #D1D5DB !important;
            transition: all 0.15s ease !important;
        }
        button[kind="secondary"]:hover,
        button[data-testid="stBaseButton-secondary"]:hover {
            border-color: #006837 !important;
            color: #006837 !important;
            background-color: #F0FDF4 !important;
        }

        /* Tabs Polish */
        div[data-testid="stTabs"] button[role="tab"] {
            font-weight: 600 !important;
            color: #4B5563 !important;
            padding: 8px 16px !important;
            border-radius: 8px 8px 0 0 !important;
            transition: all 0.15s ease !important;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: #006837 !important;
            font-weight: 700 !important;
            background-color: rgba(0, 104, 55, 0.06) !important;
        }

        /* Expanders & Bordered Containers */
        div[data-testid="stExpander"] {
            background-color: #FFFFFF;
            border: 1px solid #E5E7EB !important;
            border-radius: 10px !important;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
            overflow: hidden;
        }
        div[data-testid="stExpander"] summary {
            font-weight: 700 !important;
            color: #1F2937 !important;
        }

        /* Dataframes & Tables */
        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"] {
            border: 1px solid #E5E7EB;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
        }

        /* Metric Cards */
        div[data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-left: 4px solid #006837;
            border-radius: 10px;
            padding: 12px 16px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.03);
        }

        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            border-right: 1px solid #E5E7EB !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
