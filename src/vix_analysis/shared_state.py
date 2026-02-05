"""
Shared State and Utilities
===========================
Functions for managing shared state across multi-page Streamlit app.
"""

import streamlit as st
import yfinance as yf
from datetime import datetime


@st.cache_data(ttl=3600)
def load_vix_data():
    """Load VIX historical data."""
    vix = yf.download("^VIX", start="2004-01-01", progress=False)
    vix = vix[['Close']].copy()
    vix.columns = ['VIX']
    return vix


def get_shared_inputs():
    """
    Get all shared inputs from session state.
    These are set by the sidebar and used across all pages.

    Returns:
        dict: All input values
    """
    if 'inputs' not in st.session_state:
        return None
    return st.session_state.inputs


def set_shared_inputs(inputs):
    """
    Save inputs to session state for use across pages.

    Args:
        inputs: Dictionary of input values
    """
    st.session_state.inputs = inputs


def get_calculated_data():
    """
    Get calculated data from session state.
    This includes spike probability, scenarios, etc.

    Returns:
        dict: Calculated data or None if not yet calculated
    """
    if 'calculated_data' not in st.session_state:
        return None
    return st.session_state.calculated_data


def set_calculated_data(data):
    """
    Save calculated data to session state.

    Args:
        data: Dictionary of calculated values
    """
    st.session_state.calculated_data = data


def apply_custom_css():
    """Apply custom CSS styling to the app."""
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: bold;
            color: #1f77b4;
            text-align: center;
            margin-bottom: 0.5rem;
        }
        .sub-header {
            font-size: 1.2rem;
            color: #666;
            text-align: center;
            margin-bottom: 2rem;
        }
        .metric-container {
            background-color: #f0f2f6;
            padding: 1rem;
            border-radius: 0.5rem;
            margin: 0.5rem 0;
        }
        .big-metric {
            font-size: 3rem;
            font-weight: bold;
            text-align: center;
            margin: 1rem 0;
        }
        .status-good {
            color: #28a745;
        }
        .status-moderate {
            color: #ffc107;
        }
        .status-poor {
            color: #dc3545;
        }
        </style>
        """, unsafe_allow_html=True)


def format_currency(value):
    """Format value as currency."""
    if value >= 0:
        return f"+${value:,.0f}"
    else:
        return f"-${abs(value):,.0f}"


def format_percentage(value):
    """Format value as percentage."""
    if value >= 0:
        return f"+{value:.1f}%"
    else:
        return f"{value:.1f}%"
