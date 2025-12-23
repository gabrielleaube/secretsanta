import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Sheets Test", page_icon="✅", layout="centered")

SHEET_NAME = "Secret Santa Detective"  # MUST match your Google Sheet title exactly

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
    st.error("Connection failed ❌")
    st.write("Most common causes:")
    st.write("• Sheet not shared with the service account email (Editor)")
    st.write("• SHEET_NAME mismatch (must match title exactly)")
    st.write("• Secrets formatting issue")
    st.write("Error details:")
    st.code(str(e))

