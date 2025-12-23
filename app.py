import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone

# ----------------------------
# CONFIG
# ----------------------------
st.set_page_config(
    page_title="Secret Santa Detective",
    page_icon="🎄",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown("""
<style>
@media (max-width: 768px) {
  section.main > div { padding-left: 0.8rem; padding-right: 0.8rem; }
  .stButton button { padding: 0.8rem 1rem; font-size: 1.05rem; border-radius: 14px; }
  .stTextInput input { font-size: 1.05rem; }
  .stSelectbox div[data-baseweb="select"] > div { font-size: 1.05rem; }
  .stCheckbox label { font-size: 1.05rem; }
}
</style>
""", unsafe_allow_html=True)
SHEET_NAME = "secret-santa-data"  # your exact sheet title

st.markdown("""
<style>
.bingo-header{
  display:flex; gap:10px; justify-content:center; margin: 8px 0 16px 0;
}
.bingo-header span{
  width:54px; height:54px; display:flex; align-items:center; justify-content:center;
  border-radius:14px; border:2px solid rgba(255,255,255,0.18);
  font-weight:900; font-size:26px;
}
.bingo-card{
  max-width: 880px; margin: 0 auto;
  padding: 18px; border-radius: 22px;
  border:1px solid rgba(255,255,255,0.18);
  background: rgba(255,255,255,0.03);
}
.square{
  border-radius: 18px;
  border:1px solid rgba(255,255,255,0.18);
  padding: 14px 12px;
  min-height: 120px;
  display:flex; flex-direction:column; justify-content:space-between;
}
.square.stamped{
  border:2px solid rgba(80,200,120,0.65);
  background: rgba(80,200,120,0.08);
}
.square .label{
  font-weight:800;
  font-size: 18px;
  line-height: 1.2;
}
.square .status{
  opacity: .85;
  font-size: 14px;
  margin-top: 10px;
}
.small-note{
  opacity: .7;
  font-size: 12px;
}
</style>
""", unsafe_allow_html=True)
# ----------------------------
# SHEETS CONNECT
# ----------------------------
BINGO_PEOPLE = [
    "Montse", "Alejandro", "Diego",
    "Gabby", "Alvaro", "Mauricio",
    "Bennett", "Luzma", "Cesar"
]
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

@st.cache_data(ttl=15)
def read_tab(tab_name: str) -> pd.DataFrame:
    sh = open_sheet()  # uses cached resource
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
        st.cache_data.clear()
    else:
        ws.append_row([key, value])
        st.cache_data.clear()
def toggle_locked(sh):
    new_val = "FALSE" if is_locked() else "TRUE"
    set_state(sh, "locked", new_val)
    return new_val

def add_post(sh, player: str, content: str):
    ws = sh.worksheet("posts")
    ws.append_row([utc_iso(), player, content])
    st.cache_data.clear()
    
def get_posts(sh, limit: int = 100) -> pd.DataFrame:
    df = read_tab("posts")
    if df.empty:
        return df
    # newest first if timestamp exists
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", ascending=False)
    return df.head(limit)
    
# ----------------------------
# APP STATE (LOCK)
# ----------------------------
@st.cache_data(ttl=10)
def get_state(key: str, default="FALSE") -> str:
    sh = open_sheet()
    ws = sh.worksheet("app_state")
    rows = ws.get_all_records()
    for r in rows:
        if str(r.get("key", "")).strip().lower() == key.lower():
            return str(r.get("value", default)).strip()
    return default
def is_locked() -> bool:
    return get_state("locked", "FALSE").upper() == "TRUE"


# ----------------------------
# AUTH
# ----------------------------
def login_panel(sh):
    st.sidebar.header("🔐 Login")
    players = read_tab("players")

    if players.empty:
        st.sidebar.error("Your 'players' tab is empty.")
        return

    names = players["name"].tolist()
    name = st.sidebar.selectbox("Your name", names, key="login_name")
    code = st.sidebar.text_input("Passcode", type="password", key="login_code")

    if st.sidebar.button("Log in",use_container_width=True):
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
def get_bingo_state(player: str) -> dict:
    df = read_tab("bingo")
    state = {person: False for person in BINGO_PEOPLE}

    if df.empty:
        return state

    mine = df[df["player"] == player]
    for _, r in mine.iterrows():
        sid = str(r.get("square_id", "")).strip()
        chk = str(r.get("checked", "FALSE")).upper() == "TRUE"
        if sid in state:
            state[sid] = chk
    return state

def set_bingo_square(sh, player: str, square_id: str, checked: bool):
    ws = sh.worksheet("bingo")
    df = read_tab("bingo")

    target_row = None
    if not df.empty:
        match = df[(df["player"] == player) & (df["square_id"] == square_id)]
        if not match.empty:
            target_row = int(match.index[0]) + 2

    row_values = [utc_iso(), player, square_id, "TRUE" if checked else "FALSE"]

    if target_row:
        ws.update(f"A{target_row}:D{target_row}", [row_values])
    else:
        ws.append_row(row_values)

    st.cache_data.clear()
# ----------------------------
# GUESS SAVE (UPSERT-LIKE)
# ----------------------------
def upsert_guess(sh, player: str, giver_guess: str, receiver_guess: str, confidence: int, reason: str):
    ws = sh.worksheet("guesses")

    # Use cached guesses to find row (avoids extra API read)
    df = read_tab("guesses")

    target_row = None
    if not df.empty:
        match = df[(df["player"] == player) & (df["receiver_guess"] == receiver_guess)]
        if not match.empty:
            # find the row index in the sheet: header is row 1, df row 0 corresponds to sheet row 2
            df_index = match.index[0]
            target_row = int(df_index) + 2

    row_values = [utc_iso(), player, giver_guess, receiver_guess, int(confidence), reason]

    if target_row:
        ws.update(f"A{target_row}:F{target_row}", [row_values])
    else:
        ws.append_row(row_values)

    st.cache_data.clear()
    
def get_my_guesses(sh, player: str) -> pd.DataFrame:
    df = read_tab("guesses")
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
    st.write(f"- Locked: **{is_locked()}**")

def page_admin(sh):
    require_login()
    st.title("🔒 Admin")

    admin_code = st.text_input("Admin code", type="password", help="Only the host should have this.")
    if admin_code != st.secrets.get("ADMIN_CODE", ""):
        st.info("Enter the admin code to unlock admin controls.")
        return

    locked_now = is_locked()
    st.write(f"Current lock status: **{'LOCKED 🔒' if locked_now else 'UNLOCKED ✅'}**")

    if st.button("Toggle Lock", use_container_width=True):
        new_val = toggle_locked(sh)
        st.success(f"Locked set to {new_val}")
        st.rerun()

    st.divider()
    st.caption("When locked is TRUE, nobody can save or edit guesses.")

def page_guess_board(sh):
    require_login()
    player = st.session_state["player"]

    locked = is_locked()
    st.title("🎁 Guess Board 🎁 ")
    if locked:
        st.error("Guesses are LOCKED 🔒 (no more edits)")
    else:
        st.caption("Submit your guesses. You can edit until the host locks the game.")

    players_df = read_tab("players")
    names = players_df["name"].tolist()

    st.subheader("Make a guess")
    with st.form("guess_form"):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            giver_guess = st.selectbox("I think the Secret Santa is…", names, index=0, disabled=locked)
        with col2:
            receiver_guess = st.selectbox("…for this person:", names, index=0, disabled=locked)
        with col3:
            confidence = st.slider("Confidence", 1, 5, 3, disabled=locked)

        reason = st.text_input("Reason (optional)", placeholder="e.g., They were being suspicious at dinner", disabled=locked)

        submitted = st.form_submit_button("Save / Update Guess", disabled=locked)
    
    if submitted: 
        if giver_guess == receiver_guess:
            st.warning("That guess is interesting... You can do it, but are you sure? 😭")
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

    locked = is_locked()
    if locked:
        st.warning("Guesses are locked, but you can still post clues.")

    with st.form("post_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            anonymous = st.checkbox("Post anonymous", value=False, key="clue_anon")
        with col2:
            content = st.text_input("Your clue / theory", placeholder="Clue: My santa secret loves shrimp", key="clue_text")

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

def page_bingo(sh):
    require_login()
    player = st.session_state["player"]

    st.title("🎯 Bingo")
    st.caption("Stamp squares as you figure things out during gift opening.")

    compact = st.toggle("📱 Phone-friendly view", value=True)
    cols_n = 1 if compact else 3
    # header B I N G O
    st.markdown("""
    <div class="bingo-header">
      <span>B</span><span>I</span><span>N</span><span>G</span><span>O</span>
    </div>
    """, unsafe_allow_html=True)

    state = get_bingo_state(player)

    st.markdown('<div class="bingo-card">', unsafe_allow_html=True)

    # 3x3 grid (row-major)
    for r in range(3):
        cols = st.columns(cols_n)
        for c in range(3):
            idx = r*3 + c
            person = BINGO_PEOPLE[idx]
            stamped = state.get(person, False)

            with cols[c % cols_n]:
                # Square “card” look
                cls = "square stamped" if stamped else "square"
                st.markdown(
                    f"""
                    <div class="{cls}">
                      <div>
                        <div class="label">{person}</div>
                        <div class="status">{'✅ STAMPED' if stamped else '⬜ not yet'}</div>
                      </div>
                      <div class="small-note">Tap below to toggle</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Button stamp (real interaction)
                btn_label = "Unstamp" if stamped else "Stamp"
                if st.button(btn_label, key=f"stamp_{player}_{person}", use_container_width=True):
                    set_bingo_square(sh, player, person, not stamped)
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # Bingo detection
    current = [get_bingo_state(player).get(p, False) for p in BINGO_PEOPLE]
    wins = [
        (0,1,2),(3,4,5),(6,7,8),
        (0,3,6),(1,4,7),(2,5,8),
        (0,4,8),(2,4,6),
    ]
    if any(all(current[i] for i in line) for line in wins):
        st.success("🎉 BINGO!!!")
        st.balloons()
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
if st.sidebar.button("Log out", use_container_width=True):
    st.session_state.clear()
    st.rerun()

page = st.sidebar.radio("Go to", ["Guess Board", "Bingo", "Clue Wall", "Admin"], index=0)
if page == "Guess Board":
    page_guess_board(sh)
elif page == "Bingo":
    page_bingo(sh)
elif page == "Clue Wall":
    page_clue_wall(sh)
else:
    page_admin(sh)
