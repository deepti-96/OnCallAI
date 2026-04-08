# import streamlit as st
# from sqlalchemy import create_engine, text
# from app.config import DB_URL
# import pandas as pd

# st.set_page_config(page_title='Incident Responder', layout='wide')
# st.title('🔧 DevOps Incident Responder — MVP')

# engine = create_engine(DB_URL, future=True)

# def load_df(sql, params=None):
#     with engine.begin() as conn:
#         res = conn.execute(text(sql), params or {})
#         rows = [dict(r._mapping) for r in res]
#         return pd.DataFrame(rows)

# tabs = st.tabs(['Incidents','Agent Steps','Reports'])

# with tabs[0]:
#     st.header('Incidents')
#     st.caption('Auto-refresh every ~5s (use Streamlit rerun)')
#     if st.button('Refresh incidents'):
#         st.experimental_rerun()
#     df = load_df('SELECT * FROM incidents ORDER BY id DESC')
#     st.dataframe(df, use_container_width=True)

# with tabs[1]:
#     st.header('Agent Steps')
#     if st.button('Refresh steps'):
#         st.experimental_rerun()
#     df = load_df('SELECT * FROM agent_steps ORDER BY ts DESC, id DESC')
#     st.dataframe(df, use_container_width=True)

# with tabs[2]:
#     st.header('Reports')
#     if st.button('Refresh reports'):
#         st.experimental_rerun()
#     df = load_df('SELECT id, incident_id, substr(report_md,1,120) AS preview, created_at FROM reports ORDER BY id DESC')
#     st.dataframe(df, use_container_width=True)
#     rid = st.text_input('Open report by incident_id')
#     if rid:
#         rdf = load_df('SELECT report_md FROM reports WHERE incident_id = :i', {'i': rid})
#         if not rdf.empty:
#             st.markdown(rdf.iloc[0]['report_md'])
#         else:
#             st.info('No report found.')
# ui/streamlit_app.py
import json
import pandas as pd
import streamlit as st

# Import directly from your single DAL
from app.db.dal import (
    list_incidents,
    get_incident,
    list_steps,
    get_latest_report,
)

st.set_page_config(page_title="Incident Responder", layout="wide")
st.title("Incidents")

# --- Left: incidents list ---
incidents = list_incidents(limit=200)

left, right = st.columns([1, 2], gap="large")

with left:
    st.subheader("All Incidents")
    if not incidents:
        st.info("No incidents yet. Seed one and refresh.")
        st.stop()

    df = pd.DataFrame(incidents)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Build a friendly selector (id — service [status])
    options = [f"{row['id']} — {row['service']} [{row['status']}]" for row in incidents]
    choice = st.selectbox("Select an incident", options, index=0)
    selected_id = int(choice.split(" — ")[0])

# --- Right: details for selected incident ---
with right:
    inc = get_incident(selected_id)
    st.subheader(f"Incident #{selected_id}")
    st.caption(
        f"Service: {inc['service']} • Env: {inc['environment']} • "
        f"Severity: {inc['severity']} • Created: {inc['created_at']}"
    )

    # Steps timeline
    st.markdown("### Agent Steps")
    steps = list_steps(selected_id)
    if steps:
        steps_df = pd.DataFrame([
            {
                "id": s["id"],
                "agent": s["agent"],
                "phase": s["phase"],
                "status": s.get("status"),
                "message": s["message"],
                "ts": s["ts"],
                "data": s.get("data", {}),
            }
            for s in steps
        ])
        st.dataframe(steps_df, use_container_width=True, hide_index=True, height=320)
    else:
        st.info("No steps yet for this incident.")

    # Report
    st.markdown("### Report")
    rep = get_latest_report(selected_id)
    if rep:
        st.markdown(rep["report_md"])
        # Downloads
        st.download_button(
            "Download report.json",
            data=json.dumps(rep["report"], indent=2),
            file_name=f"incident_{selected_id}_report.json",
            mime="application/json",
        )
        st.download_button(
            "Download report.md",
            data=rep["report_md"],
            file_name=f"incident_{selected_id}_report.md",
            mime="text/markdown",
        )
    else:
        st.info("No report generated yet.")

