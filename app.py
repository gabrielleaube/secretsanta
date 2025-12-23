import os
import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timezone

# ----------------------------
# CONFIG
# ----------------------------
st.set_page_config(page_title="Secret Santa Detective", page_icon="🎄", layout="wide")

# Secrets: set these in Streamlit Cloud (or .env locally)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", os.getenv("SUPABASE_ANON_KEY", ""))
ADMIN_CODE = st.secrets.get("ADMIN_CODE", os.getenv("ADMIN_CODE", "ADMIN123"))

NAMES = [
    "Diego", "Gabby", "Person 3", "Person 4", "Person 5",
    "Person 6", "Person 7", "Person 8", "Person 9"
]

PAGES = ["🎁 Guess Board", "✅ Bingo", "🕵️ Clue Wall", "🏆 Leaderboard", "🔒 Admin / Reveal"]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

@st.cache_resource
def get_db() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

db = get_db()

# ----------------------------
# AUTH (simple passcode)
# ----------------------------
def login_box():
    st.sidebar.header("🔐 Login")
    name = st.sidebar.selectbox("Your name", NAMES, index=0)
    code = st.sidebar.text_input("Passcode", type="password", help="Ask the host for your code.")
    if st.sidebar.button("Log in"):
        st.session_state["player"] = name
        st.session_state["code"] = code
        st.toast(f"Welcome, {name} 🎄", icon="🎄")

def require_login():
    if "player" not in st.session_state or "code" not in st.session_state:
        login_box()
        st.info("Log in on the left to play.")
        st.stop()

# ----------------------------
# PLACEHOLDER PAGES
# ----------------------------
def page_guess_board():
    require_login()
    st.title("🎁 Guess Board")
    st.caption("Make your guesses. Change them anytime until the lock.")

    st.warning("Next step: we’ll connect this to Supabase + save guesses.")

    st.subheader("Example UI")
    giver = st.selectbox("I think the Secret Santa is…", NAMES)
    receiver = st.selectbox("…for this person:", NAMES)
    confidence = st.slider("Confidence", 1, 5, 3)
    reason = st.text_input("Reason (optional)", placeholder="e.g., They kept asking what I wanted 😭")

    st.button("Save guess (coming next)")

def page_bingo():
    require_login()
    st.title("✅ Bingo")
    st.caption("Your personal chaos card.")

    st.warning("Next step: we’ll persist bingo checks per user.")

    squares = [
        "Accused an innocent person",
        "Changed a guess 3+ times",
        "Used “evidence” in your reason",
        "Posted a clue",
        "Got baited by a fake clue",
        "Guessed your own Santa (lol)",
        "Confidence 5 and still wrong",
        "Called someone “too obvious”",
        "Made a guess in under 10 seconds",
    ]
    cols = st.columns(3)
    for i, s in enumerate(squares):
        with cols[i % 3]:
            st.checkbox(s, key=f"bingo_{i}")

    st.button("Check for BINGO (coming next)")

def page_clue_wall():
    require_login()
    st.title("🕵️ Clue Wall")
    st.caption("Drop clues, theories, and chaotic accusations.")

    st.warning("Next step: store & display posts from Supabase.")

    post = st.text_area("Write a clue/theory", placeholder="Clue: My Santa definitely owns a Stanley cup.")
    st.button("Post (coming next)")

    st.divider()
    st.subheader("Feed (coming next)")
    st.write("• Example: “I think Diego has Person 6 because…”")

def page_leaderboard():
    require_login()
    st.title("🏆 Leaderboard")
    st.caption("We’ll score this on reveal day (and optionally do ‘Most chaotic’ live).")
    st.warning("Next step: compute stats from saved guesses/posts/bingo.")

def page_admin():
    require_login()
    st.title("🔒 Admin / Reveal")
    admin_try = st.text_input("Admin code", type="password")
    if admin_try != ADMIN_CODE:
        st.info("Enter the admin code to unlock reveal tools.")
        return

    st.success("Admin unlocked.")
    st.warning("Next step: set lock/reveal mode + upload the true pairs safely.")
    st.button("Toggle LOCK (coming next)")
    st.button("Toggle REVEAL MODE (coming next)")

# ----------------------------
# NAV
# ----------------------------
st.sidebar.title("🎄 Secret Santa Detective")
if "player" not in st.session_state:
    login_box()
else:
    st.sidebar.success(f"Logged in as: {st.session_state['player']}")
    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()

page = st.sidebar.radio("Navigate", PAGES, index=0)

if page == "🎁 Guess Board":
    page_guess_board()
elif page == "✅ Bingo":
    page_bingo()
elif page == "🕵️ Clue Wall":
    page_clue_wall()
elif page == "🏆 Leaderboard":
    page_leaderboard()
else:
    page_admin()

