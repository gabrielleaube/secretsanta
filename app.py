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
.podium-wrap{max-width:920px;margin:0 auto;}
.podium{display:flex;gap:14px;align-items:flex-end;justify-content:center;margin:18px 0 6px 0;}
.pcol{flex:1;min-width:0}
.pcard{
  border-radius:18px;padding:14px 14px 12px 14px;
  border:1px solid rgba(255,255,255,0.18);
  background: rgba(255,255,255,0.03);
  text-align:center;
}
.pname{font-weight:900;font-size:18px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.pscore{font-size:34px;font-weight:900;margin-top:4px;}
.prank{opacity:.75;font-size:13px;margin-top:6px;}
.bar{border-radius:18px 18px 6px 6px; margin-top:10px; border:1px solid rgba(255,255,255,0.18);
     background: rgba(255,255,255,0.05);}
.bar.one{height:220px;}
.bar.two{height:160px;}
.bar.three{height:130px;}
@media (max-width: 768px){
  .podium{flex-direction:column;align-items:stretch}
  .bar.one,.bar.two,.bar.three{height:72px;}
}
</style>
""", unsafe_allow_html=True)
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

@st.cache_data(ttl=180, show_spinner=False)  # 3 minutes
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
    
    else:
        ws.append_row([key, value])
      
def toggle_locked(sh):
    new_val = "FALSE" if is_locked() else "TRUE"
    set_state(sh, "locked", new_val)
    return new_val

def add_post(sh, player: str, content: str):
    ws = sh.worksheet("posts")
    ws.append_row([utc_iso(), player, content])

    
def get_posts(sh, limit: int = 100) -> pd.DataFrame:
    df = read_tab("posts")
    if df.empty:
        return df
    # newest first if timestamp exists
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", ascending=False)
    return df.head(limit)
def get_assignments_df() -> pd.DataFrame:
    df = read_tab("assignments")
    # expects receiver, giver
    if df.empty:
        return df
    df["receiver"] = df["receiver"].astype(str).str.strip()
    df["giver"] = df["giver"].astype(str).str.strip()
    return df

def compute_scores() -> pd.DataFrame:
    guesses = read_tab("guesses")
    assign = get_assignments_df()
    players = read_tab("players")

    if guesses.empty or assign.empty or players.empty:
        return pd.DataFrame(columns=["player", "correct", "total", "accuracy"])

    # normalize
    for col in ["player", "giver_guess", "receiver_guess"]:
        guesses[col] = guesses[col].astype(str).str.strip()

    # For each player+receiver, keep the most recent guess (prevents double counting)
    if "timestamp" in guesses.columns:
        guesses = guesses.sort_values("timestamp").drop_duplicates(
            subset=["player", "receiver_guess"], keep="last"
        )

    # join guesses to truth on receiver
    merged = guesses.merge(assign, left_on="receiver_guess", right_on="receiver", how="left")

    # correct if giver_guess == true giver
    merged["is_correct"] = merged["giver_guess"].fillna("") == ""

    # if receiver not found in assignments, treat as not scorable
    merged["is_scorable"] = merged["giver"].notna()
    merged["is_correct"] = merged["is_scorable"] & (merged["giver_guess"] == merged["giver"])

    # score by player
    score = merged.groupby("player").agg(
        correct=("is_correct", "sum"),
        total=("is_scorable", "sum")
    ).reset_index()

    score["accuracy"] = score.apply(lambda r: (r["correct"] / r["total"]) if r["total"] else 0.0, axis=1)

    # include players with 0s
    all_names = players["name"].astype(str).str.strip().unique().tolist()
    score = pd.DataFrame({"player": all_names}).merge(score, on="player", how="left").fillna(0)
    score["correct"] = score["correct"].astype(int)
    score["total"] = score["total"].astype(int)

    # rank
    score = score.sort_values(["correct", "accuracy"], ascending=[False, False]).reset_index(drop=True)
    return score

def get_active_superlatives() -> pd.DataFrame:
    df = read_tab("superlatives")
    if df.empty:
        return df
    df["active"] = df["active"].astype(str).str.upper()
    df = df[df["active"] == "TRUE"].copy()
    return df

def upsert_vote(sh, voter: str, category: str, nominee: str):
    ws = sh.worksheet("votes")
    df = read_tab("votes")

    target_row = None
    if not df.empty:
        df["voter"] = df["voter"].astype(str).str.strip()
        df["category"] = df["category"].astype(str).str.strip()
        match = df[(df["voter"] == voter) & (df["category"] == category)]
        if not match.empty:
            target_row = int(match.index[0]) + 2

    row_values = [utc_iso(), voter, category, nominee]

    if target_row:
        ws.update(f"A{target_row}:D{target_row}", [row_values])
    else:
        ws.append_row(row_values)

def compute_superlative_results() -> pd.DataFrame:
    votes = read_tab("votes")
    if votes.empty:
        return pd.DataFrame(columns=["category", "nominee", "votes"])

    votes["category"] = votes["category"].astype(str).str.strip()
    votes["nominee"] = votes["nominee"].astype(str).str.strip()

    res = votes.groupby(["category", "nominee"]).size().reset_index(name="votes")
    res = res.sort_values(["category", "votes"], ascending=[True, False]).reset_index(drop=True)
    return res
# ----------------------------
# APP STATE (LOCK)
# ----------------------------
@st.cache_data(ttl=60, show_spinner=False)
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

def reveal_scores_on() -> bool:
    return get_state("reveal_scores", "FALSE").upper() == "TRUE"

def set_reveal_scores(sh, val: bool):
    set_state(sh, "reveal_scores", "TRUE" if val else "FALSE")
    
def reveal_superlatives_on() -> bool:
    return get_state("reveal_superlatives", "FALSE").upper() == "TRUE"

def set_reveal_superlatives(sh, val: bool):
    set_state(sh, "reveal_superlatives", "TRUE" if val else "FALSE")
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
    
    st.subheader("🏁 End Game")
    reveal_now = reveal_scores_on()
    st.write(f"Reveal scores: **{reveal_now}**")

    if st.button("Toggle Reveal Scores"):
        set_reveal_scores(sh, not reveal_now)
        st.success("Updated reveal_scores ✅")
        st.rerun()
        
    st.subheader("😈 Superlatives")
    show_now = reveal_superlatives_on()
    st.write(f"Reveal superlatives: **{show_now}**")

    if st.button("Toggle Reveal Superlatives"):
        set_reveal_superlatives(sh, not show_now)
        st.success("Updated reveal_superlatives ✅")
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
def page_leaderboard():
    require_login()
    st.title("🏆 Leaderboard")

    if not reveal_scores_on():
        st.info("Scores are hidden until the host reveals them.")
        st.stop()

    scores = compute_scores()
    if scores.empty:
        st.warning("No scores yet. Make sure `assignments` is filled and guesses exist.")
        st.stop()

    top = scores.head(3)
    # pad if fewer than 3
    while len(top) < 3:
        top = pd.concat([top, pd.DataFrame([{"player":"—", "correct":0, "total":0, "accuracy":0.0}])], ignore_index=True)

    first, second, third = top.iloc[0], top.iloc[1], top.iloc[2]

    st.markdown('<div class="podium-wrap">', unsafe_allow_html=True)
    st.markdown("""
    <div class="podium">
      <div class="pcol">
        <div class="pcard">
          <div class="pname">🥈 {name}</div>
          <div class="pscore">{score}</div>
          <div class="prank">{acc}</div>
        </div>
        <div class="bar two"></div>
      </div>
      <div class="pcol">
        <div class="pcard">
          <div class="pname">🥇 {name}</div>
          <div class="pscore">{score}</div>
          <div class="prank">{acc}</div>
        </div>
        <div class="bar one"></div>
      </div>
      <div class="pcol">
        <div class="pcard">
          <div class="pname">🥉 {name}</div>
          <div class="pscore">{score}</div>
          <div class="prank">{acc}</div>
        </div>
        <div class="bar three"></div>
      </div>
    </div>
    """.format(
        name=second["player"], score=int(second["correct"]),
        acc=f"{int(round(second['accuracy']*100))}% accuracy" if int(second["total"]) else "—"
    ) + "" , unsafe_allow_html=True)

    # The above format call only filled second; easiest is to render 3 separately:
    st.markdown('</div>', unsafe_allow_html=True)

    # Render properly (simple approach)
    st.markdown('<div class="podium-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="podium">', unsafe_allow_html=True)

    def podium_col(emoji, row, bar_class):
        name = row["player"]
        score = int(row["correct"])
        acc = f"{int(round(row['accuracy']*100))}% accuracy" if int(row["total"]) else "—"
        st.markdown(f"""
        <div class="pcol">
          <div class="pcard">
            <div class="pname">{emoji} {name}</div>
            <div class="pscore">{score}</div>
            <div class="prank">{acc}</div>
          </div>
          <div class="bar {bar_class}"></div>
        </div>
        """, unsafe_allow_html=True)

    # order: 2nd, 1st, 3rd for classic podium look
    podium_col("🥈", second, "two")
    podium_col("🥇", first, "one")
    podium_col("🥉", third, "three")

    st.markdown("</div></div>", unsafe_allow_html=True)

    st.divider()
    st.subheader("Full Rankings")
    show = scores.copy()
    show["accuracy"] = (show["accuracy"] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(show[["player", "correct", "total", "accuracy"]], hide_index=True, use_container_width=True)

def page_superlatives(sh):
    require_login()
    voter = st.session_state["player"]

    st.title("😈 Family Superlatives")
    st.caption("Vote anonymously. You can change your vote anytime until results are revealed.")

    cats = get_active_superlatives()
    players = read_tab("players")
    names = players["name"].astype(str).str.strip().tolist() if not players.empty else []

    if cats.empty:
        st.warning("No active superlatives yet. Add rows in the `superlatives` tab and set active=TRUE.")
        return
    if not names:
        st.warning("Players list is empty.")
        return

    # --- Voting section
    st.subheader("Cast your votes")
    with st.form("superlatives_form"):
        choices = {}
        for _, row in cats.iterrows():
            cat = str(row["category"])
            prompt = str(row.get("prompt", cat))
            # default to blank choice
            choices[cat] = st.selectbox(prompt, ["(choose)"] + names, key=f"vote_{cat}")

        submitted = st.form_submit_button("Submit votes", use_container_width=True)

    if submitted:
        for cat, nominee in choices.items():
            if nominee != "(choose)":
                upsert_vote(sh, voter, cat, nominee)
        st.success("Votes saved ✅ (anonymous)")
        st.rerun()

    st.divider()

    # --- Results section (hidden until reveal)
    st.subheader("Results")
    if not reveal_superlatives_on():
        st.info("Results are hidden until the host reveals them.")
        return

    res = compute_superlative_results()
    if res.empty:
        st.write("No votes yet.")
        return

    # winner per category
    winners = res.sort_values(["category", "votes"], ascending=[True, False]).drop_duplicates("category")

    # pretty winner cards
    for _, w in winners.iterrows():
        cat = w["category"]
        nominee = w["nominee"]
        v = int(w["votes"])
        st.markdown(f"""
        <div style="border:1px solid rgba(255,255,255,0.18); border-radius:18px; padding:14px; margin:10px 0;
                    background: rgba(255,255,255,0.03);">
          <div style="font-weight:900; font-size:18px;">🏅 {cat}</div>
          <div style="font-size:22px; font-weight:900; margin-top:6px;">{nominee}</div>
          <div style="opacity:.8; margin-top:6px;">Votes: <b>{v}</b></div>
        </div>
        """, unsafe_allow_html=True)

        # breakdown table for that category
        with st.expander(f"See full votes for {cat}"):
            sub = res[res["category"] == cat].copy()
            st.dataframe(sub[["nominee", "votes"]], hide_index=True, use_container_width=True)
            
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

page = st.sidebar.radio(
    "Go to",
    ["Guess Board", "Bingo", "Clue Wall", "Leaderboard", "Superlatives", "Admin"],
    index=0
)

if page == "Guess Board":
    page_guess_board(sh)
elif page == "Bingo":
    page_bingo(sh)
elif page == "Clue Wall":
    page_clue_wall(sh)
elif page == "Leaderboard":
    page_leaderboard()
elif page == "Superlatives":
    page_superlatives(sh)
else:
    page_admin(sh)
