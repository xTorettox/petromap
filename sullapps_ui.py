"""
SullApps Suite - Shared Python UI Helper Module
Sullair Argentina S.A.

Provides standardized enterprise styling, contextual loading spinners powered by
`shared/quotes/loading_quotes.json`, and celebration notifications across all SullApps.
"""

import os
import json
import html
import random
from contextlib import contextmanager
import streamlit as st

SULLAIR_PRIMARY = "#006837"
SULLAIR_DARK = "#004D26"
SULLAIR_LIGHT = "#E6F4EA"
SULLAIR_BG = "#F8F9FA"
SULLAIR_CARD = "#FFFFFF"
SULLAIR_TEXT = "#1F2937"

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
