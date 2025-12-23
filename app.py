import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone

# ----------------------------
# CONFIG
# ----------------------------
st.set_page_config(page_title="Secret Santa Detective", page_icon="🎄", layout="wide")
SHEET_NAME = "secret-santa-data"  # your exact sheet title

# ----------------------------
# SHEETS CONNECT
# ----------------------------
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

def ws_df(sh, tab_name: str) -> pd.DataFrame:
    ws = sh.worksheet(tab_name)
    return pd.DataFrame(ws.get_all_records())

def utc_iso():
    return datetime.now(timezone.utc).isoformat()

def set_state(sh, key: str, value: str):
    """Set app_state[key] = value (TRUE/FALSE). Creates row if missing."""
    ws = sh.worksheet("app_state")
    rows = ws.get_all_records()

    # Find the row with this key (row index in sheet = i+2)
    target_row = None
    for i, r in enumerate(rows, start=2):
        if str(r.get("key", "")).strip().lower() == key.lower():
            target_row = i
            break

    if target_row:
        ws.update(f"B{target_row}", [[value]])
    else:
        ws.append_row([key, value])

def toggle_locked(sh):
    new_val = "FALSE" if is_locked(sh) else "TRUE"
    set_state(sh, "locked", new_val)
    return new_val

def add_post(sh, player: str, content: str):
    ws = sh.worksheet("posts")
    ws.append_row([utc_iso(), player, content])

def get_posts(sh, limit: int = 100) -> pd.DataFrame:
    df = ws_df(sh, "posts")
    if df.empty:
        return df
    # newest first if timestamp exists
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", ascending=False)
    return df.head(limit)
    
# ----------------------------
# APP STATE (LOCK)
# ----------------------------
def get_state(sh, key: str, default="FALSE") -> str:
    ws = sh.worksheet("app_state")
    rows = ws.get_all_records()
    for r in rows:
        if str(r.get("key", "")).strip().lower() == key.lower():
            return str(r.get("value", default)).strip()
    return default

def is_locked(sh) -> bool:
    return get_state(sh, "locked", "FALSE").upper() == "TRUE"

# ----------------------------
# AUTH
# ----------------------------
def login_panel(sh):
    st.sidebar.header("🔐 Login")
    players = ws_df(sh, "players")
    if players.empty:
        st.sidebar.error("Your 'players' tab is empty.")
        return

    names = players["name"].tolist()
    name = st.sidebar.selectbox("Your name", names)
    code = st.sidebar.text_input("Passcode", type="password")

    if st.sidebar.button("Log in"):
        ok = not players[(players["name"] == name) & (players["passcode"] == code)].empty
        if ok:
            st.session_state["player"] = name
            st.toast(f"Welcome, {name} 🎄", icon="🎄")
            st.rerun()
        else:
            st.sidebar.error("Wrong passcode.")

def require_login():
    if "player" not in st.session_state:
        st.info("Log in using the sidebar to play.")
        st.stop()

# ----------------------------
# GUESS SAVE (UPSERT-LIKE)
# ----------------------------
def upsert_guess(sh, player: str, giver_guess: str, receiver_guess: str, confidence: int, reason: str):
    """
    Overwrite player's guess for a given receiver_guess if it exists.
    Otherwise append a new row.
    """
    ws = sh.worksheet("guesses")
    records = ws.get_all_records()

    # find existing row index (2-based in Sheets because row 1 is headers)
    target_row = None
    for i, r in enumerate(records, start=2):
        if str(r.get("player", "")).strip() == player and str(r.get("receiver_guess", "")).strip() == receiver_guess:
            target_row = i
            break

    row_values = [utc_iso(), player, giver_guess, receiver_guess, int(confidence), reason]

    if target_row:
        # update the whole row A:F
        ws.update(f"A{target_row}:F{target_row}", [row_values])
    else:
        ws.append_row(row_values)

def get_my_guesses(sh, player: str) -> pd.DataFrame:
    df = ws_df(sh, "guesses")
    if df.empty:
        return df
    df = df[df["player"] == player].copy()
    # latest first
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", ascending=False)
    return df

# ----------------------------
# UI PAGES
# ----------------------------
def page_home(sh):
    st.title("🎄 Secret Santa Detective")
    st.write("Pick a page on the left to start.")
    st.write("Current status:")
    st.write(f"- Locked: **{is_locked(sh)}**")

def page_admin(sh):
    require_login()
    st.title("🔒 Admin")

    admin_code = st.text_input("Admin code", type="password", help="Only the host should have this.")
    if admin_code != st.secrets.get("ADMIN_CODE", ""):
        st.info("Enter the admin code to unlock admin controls.")
        return

    locked_now = is_locked(sh)
    st.write(f"Current lock status: **{'LOCKED 🔒' if locked_now else 'UNLOCKED ✅'}**")

    if st.button("Toggle Lock"):
        new_val = toggle_locked(sh)
        st.success(f"Locked set to {new_val}")
        st.rerun()

    st.divider()
    st.caption("When locked is TRUE, nobody can save or edit guesses.")

def page_guess_board(sh):
    require_login()
    player = st.session_state["player"]

    locked = is_locked(sh)
    st.title("🎁 Guess Board")
    if locked:
        st.error("Guesses are LOCKED 🔒 (no more edits)")
    else:
        st.caption("Submit your guesses. You can edit until the host locks the game.")

    players_df = ws_df(sh, "players")
    names = players_df["name"].tolist()

    st.subheader("Make a guess")
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        giver_guess = st.selectbox("I think the Secret Santa is…", names, index=0, disabled=locked)
    with col2:
        receiver_guess = st.selectbox("…for this person:", names, index=0, disabled=locked)
    with col3:
        confidence = st.slider("Confidence", 1, 5, 3, disabled=locked)

    reason = st.text_input("Reason (optional)", placeholder="e.g., They were being suspicious at dinner", disabled=locked)

    if st.button("Save / Update Guess", disabled=locked):
        if giver_guess == receiver_guess:
            st.warning("That guess is… chaotic. You can do it, but are you sure? 😭")
        upsert_guess(sh, player, giver_guess, receiver_guess, confidence, reason)
        st.success("Saved ✅")
        st.rerun()

    st.divider()
    st.subheader("My saved guesses")
    mine = get_my_guesses(sh, player)
    if mine.empty:
        st.write("No guesses yet.")
    else:
        show_cols = [c for c in ["timestamp", "giver_guess", "receiver_guess", "confidence", "reason"] if c in mine.columns]
        st.dataframe(mine[show_cols], hide_index=True, use_container_width=True)


def page_clue_wall(sh):
    require_login()
    player = st.session_state["player"]

    st.title("🕵️ Clue Wall")
    st.caption("Drop clues, theories, and chaotic accusations. Keep it fun 😈")

    locked = is_locked(sh)
    if locked:
        st.warning("Guesses are locked, but you can still post clues.")

    with st.form("post_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            anonymous = st.checkbox("Post anonymous", value=False)
        with col2:
            content = st.text_input("Your clue / theory", placeholder="Clue: My Santa definitely owns a Stanley cup.")

        submitted = st.form_submit_button("Post")
        if submitted:
            text = (content or "").strip()
            if len(text) < 3:
                st.error("Make it at least 3 characters.")
            else:
                author = "Anonymous" if anonymous else player
                add_post(sh, author, text)
                st.success("Posted ✅")
                st.rerun()

    st.divider()

    st.subheader("Feed")
    posts = get_posts(sh, limit=200)

    if posts.empty:
        st.write("No posts yet. Start the chaos 👀")
        return

    # Pretty feed cards
    for _, row in posts.iterrows():
        ts = str(row.get("timestamp", "")).replace("T", " ").replace("+00:00", " UTC")
        who = row.get("player", "Unknown")
        text = row.get("content", "")

        with st.container(border=True):
            st.write(f"**{who}**")
            if ts.strip():
                st.caption(ts)
            st.write(text)
#ADMIN LOCK

# ----------------------------
# MAIN
# ----------------------------
sh = open_sheet()

st.sidebar.title("🎄 Secret Santa Detective")

# Logged out -> show ONLY login + landing page
if "player" not in st.session_state:
    login_panel(sh)
    st.title("🎄 Secret Santa Detective")
    st.caption("Log in on the left to start guessing.")
    st.stop()

# Logged in -> show nav + pages
st.sidebar.success(f"Logged in as: {st.session_state['player']}")
if st.sidebar.button("Log out"):
    st.session_state.clear()
    st.rerun()

page = st.sidebar.radio("Go to", ["Guess Board", "Clue Wall", "Admin"], index=0)
if page == "Guess Board":
    page_guess_board(sh)
elif page == "Clue Wall":
    page_clue_wall(sh)
else:
    page_admin(sh)
