import os
import json
import datetime
import requests
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

__version__ = "1.0.0"

st.set_page_config(page_title="Third Brain Dashboard", page_icon="🧠", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, "..", "config.json")

with open(config_path) as f:
    config = json.load(f)
    app_env = config.get("environment", "PROD").upper()

env_filename = ".third_brain_dev.env" if app_env == "DEV" else ".third_brain.env"
load_dotenv(os.path.expanduser(f"~/{env_filename}"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}


@st.cache_data(ttl=30)
def fetch_thoughts():
    url = f"{SUPABASE_URL}/rest/v1/thoughts"
    params = {"select": "id,content,metadata,created_at", "order": "created_at.desc"}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def save_thought(thought_id: str, metadata: dict):
    url = f"{SUPABASE_URL}/rest/v1/thoughts?id=eq.{thought_id}"
    resp = requests.patch(url, headers=HEADERS, json={"metadata": metadata}, timeout=10)
    resp.raise_for_status()


def flatten(raw: list) -> pd.DataFrame:
    rows = []
    for item in raw:
        meta = item.get("metadata", {})
        topics = meta.get("topics", [])
        rows.append({
            "id": item["id"],
            "created": item.get("created_at", "")[:10],
            "type": meta.get("type", ""),
            "domain": meta.get("domain", ""),
            "status": meta.get("status", "New"),
            "target_date": meta.get("target_date"),
            "topics": ", ".join(topics) if isinstance(topics, list) else str(topics),
            "content": item.get("content", ""),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["target_date"] = pd.to_datetime(df["target_date"], errors="coerce").apply(
            lambda x: x.date() if pd.notnull(x) else None
        )
    return df


# --- Sidebar ---
st.sidebar.title("🧠 Filters")
selected_status = st.sidebar.multiselect("Status", ["New", "Review", "Done"], default=["New", "Review"])
selected_domain = st.sidebar.multiselect("Domain", ["Work", "Home"], default=["Work", "Home"])
selected_types = st.sidebar.multiselect("Type", ["Task", "Project", "Admin", "Idea"], default=["Task", "Project", "Admin", "Idea"])

if st.sidebar.button("Refresh"):
    st.cache_data.clear()
    st.rerun()

# --- Load Data ---
try:
    raw = fetch_thoughts()
except Exception as e:
    st.error(f"Failed to load from Supabase: {e}")
    st.stop()

df = flatten(raw)

if df.empty:
    st.info("No thoughts in the database yet.")
    st.stop()

# --- Apply Filters ---
mask = (
    df["status"].isin(selected_status) &
    df["domain"].isin(selected_domain) &
    df["type"].isin(selected_types)
)
filtered = df[mask].copy().reset_index(drop=True)

# --- Metrics ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Shown", len(filtered))
col2.metric("Work", len(filtered[filtered["domain"] == "Work"]))
col3.metric("Home", len(filtered[filtered["domain"] == "Home"]))
col4.metric("Review", len(df[df["status"] == "Review"]))

st.markdown("### 📋 Thoughts (Editable)")

if filtered.empty:
    st.info("No entries match the current filters.")
    st.stop()

edited = st.data_editor(
    filtered,
    key="thought_editor",
    use_container_width=True,
    hide_index=True,
    disabled=["id", "created"],
    column_order=["created", "type", "domain", "status", "target_date", "topics", "content", "id"],
    column_config={
        "id": st.column_config.TextColumn("ID", width="small"),
        "created": st.column_config.TextColumn("Created", width="small"),
        "status": st.column_config.SelectboxColumn(
            "Status", options=["New", "Review", "Done"], required=True, width="small"
        ),
        "domain": st.column_config.SelectboxColumn(
            "Domain", options=["Work", "Home"], width="small"
        ),
        "type": st.column_config.SelectboxColumn(
            "Type", options=["Task", "Project", "Admin", "Idea"], width="small"
        ),
        "target_date": st.column_config.DateColumn(
            "Target Date", format="YYYY-MM-DD", width="medium"
        ),
        "topics": st.column_config.TextColumn("Topics", width="medium"),
        "content": st.column_config.TextColumn("Content", width="large"),
    },
)

# --- Save Changes ---
orig_by_id = {row["id"]: row for _, row in filtered.iterrows()}
changed = []
for _, row in edited.iterrows():
    orig = orig_by_id.get(row["id"])
    if orig is None:
        continue
    if (
        row["status"] != orig["status"]
        or row["domain"] != orig["domain"]
        or row["type"] != orig["type"]
        or str(row["target_date"]) != str(orig["target_date"])
        or row["topics"] != orig["topics"]
        or row["content"] != orig["content"]
    ):
        changed.append(row)

if changed:
    errors = []
    for row in changed:
        t_date = row["target_date"]
        if isinstance(t_date, (datetime.date, datetime.datetime)):
            t_date = t_date.isoformat()
        elif str(t_date) in ("None", "NaT", "nan"):
            t_date = None

        metadata = {
            "type": row["type"],
            "domain": row["domain"],
            "status": row["status"],
            "target_date": t_date,
            "topics": [t.strip() for t in row["topics"].split(",") if t.strip()] if row["topics"] else [],
        }
        try:
            save_thought(row["id"], metadata)
        except Exception as e:
            errors.append(f"{str(row['id'])[:8]}: {e}")

    if errors:
        st.error(f"Failed to save: {'; '.join(errors)}")
    else:
        st.cache_data.clear()
        st.rerun()
