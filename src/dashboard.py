import streamlit as st
import sqlite3
import pandas as pd
import os
import datetime

# --- Config ---
st.set_page_config(page_title="Second Brain Dashboard", page_icon="🧠", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "..", "db", "brain.db")

def get_connection():
    return sqlite3.connect(DB_FILE)

# --- Sidebar Filters ---
st.sidebar.title("🧠 Filters")
status_options = ["New", "Review", "Done"]
selected_status = st.sidebar.multiselect("Status", status_options, default=["New"])
domain_options = ["Work", "Home"]
selected_domain = st.sidebar.multiselect("Domain", domain_options, default=domain_options)
type_options = ["Task", "Project", "Idea", "Log"]
selected_types = st.sidebar.multiselect("Type", type_options, default=type_options)

# --- Main Logic ---
if not selected_status:
    st.warning("Please select at least one Status.")
else:
    conn = get_connection()
    
    # 1. Fetch Data
    status_placeholders = ','.join(['?'] * len(selected_status))
    domain_placeholders = ','.join(['?'] * len(selected_domain))
    type_placeholders = ','.join(['?'] * len(selected_types))
    
    query = f"""
        SELECT 
            id, type, domain, status, target_date, summary, details
        FROM entries 
        WHERE status IN ({status_placeholders})
        AND domain IN ({domain_placeholders})
        AND type IN ({type_placeholders})
        ORDER BY 
            CASE WHEN target_date IS NULL THEN 1 ELSE 0 END, 
            target_date ASC, 
            id DESC
    """
    params = selected_status + selected_domain + selected_types
    df = pd.read_sql_query(query, conn, params=params)
    
    # --- FIX 1: Convert SQLite Strings to Python Date Objects ---
    # Streamlit crashes if you pass Strings to a DateColumn
    df["target_date"] = pd.to_datetime(df["target_date"], errors='coerce')
    df["target_date"] = df["target_date"].apply(lambda x: x.date() if pd.notnull(x) else None)
    
    conn.close()

    # --- Metrics ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Items", len(df))
    col2.metric("Work Items", len(df[df['domain']=='Work']))
    col3.metric("Home Items", len(df[df['domain']=='Home']))

    st.markdown("### 📋 Active Entries (Editable)")
    
    # 2. Editable Data Editor
    if not df.empty:
        edited_df = st.data_editor(
            df,
            key="task_editor",
            use_container_width=True,
            hide_index=True,
            disabled=["id", "timestamp"], 
            column_config={
                "status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["New", "Review", "Done"],
                    required=True,
                    width="small"
                ),
                "domain": st.column_config.SelectboxColumn(
                    "Domain",
                    options=["Work", "Home"],
                    width="small"
                ),
                "type": st.column_config.SelectboxColumn(
                    "Type",
                    options=["Task", "Project", "Idea", "Log"],
                    width="small"
                ),
                "target_date": st.column_config.DateColumn(
                    "Target Date",
                    format="YYYY-MM-DD",
                    width="medium"
                ),
                "summary": st.column_config.TextColumn(
                    "Summary",
                    width="large"
                ),
            }
        )

        # 3. Save Changes Logic
        if not df.equals(edited_df):
            conn = get_connection()
            cursor = conn.cursor()
            
            data_to_update = edited_df.to_dict('records')
            
            for row in data_to_update:
                # --- FIX 2: Convert Date Objects back to Strings for SQLite ---
                t_date = row['target_date']
                if isinstance(t_date, (datetime.date, datetime.datetime)):
                    t_date = t_date.isoformat()
                
                cursor.execute("""
                    UPDATE entries 
                    SET status=?, domain=?, type=?, target_date=?, summary=?, details=?
                    WHERE id=?
                """, (
                    row['status'], 
                    row['domain'], 
                    row['type'], 
                    t_date, 
                    row['summary'], 
                    row['details'],
                    row['id']
                ))
            
            conn.commit()
            conn.close()
            
    else:
        st.info("No entries found matching filters.")

    # --- Quick Add ---
    with st.expander("➕ Quick Add (Manual)"):
        with st.form("quick_add"):
            c1, c2 = st.columns([3, 1])
            new_summary = c1.text_input("Summary")
            new_domain = c2.selectbox("Domain", ["Home", "Work"])
            submitted = st.form_submit_button("Add Task")
            if submitted and new_summary:
                conn = get_connection()
                c = conn.cursor()
                c.execute("INSERT INTO entries (type, domain, summary, status) VALUES (?, ?, ?, ?)", 
                          ("Task", new_domain, new_summary, "New"))
                conn.commit()
                conn.close()
                st.rerun()