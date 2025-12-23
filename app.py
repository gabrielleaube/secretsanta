import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Sheets Test", page_icon="✅", layout="centered")

SHEET_NAME = "secret-santa-data"  # MUST match your Google Sheet title exactly

@st.cache_resource
def open_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)

st.title("✅ Google Sheets Connection Test")

try:
    sh = open_sheet()
    st.success("Connected to your Google Sheet ✅")

    # Read players tab
    ws = sh.worksheet("players")
    df = pd.DataFrame(ws.get_all_records())

    st.subheader("players tab preview")
    st.dataframe(df, hide_index=True, use_container_width=True)

except Exception as e:
    import traceback
    st.error("Connection failed ❌")

    st.subheader("Debug")
    st.code(repr(e))  # shows the exception type/details
    st.code(traceback.format_exc())  # full traceback

    # If it's a gspread APIError, it often has a .response with useful JSON/text
    resp = getattr(e, "response", None)
    if resp is not None:
        st.subheader("Raw response text")
        st.code(getattr(resp, "text", str(resp)))

