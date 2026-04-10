import json

import pandas as pd
import streamlit as st

from app.db.dal import get_incident, get_latest_report, list_incidents, list_steps

st.set_page_config(page_title="OnCallAI", layout="wide")
st.title("OnCallAI")
st.caption("AI-assisted incident triage workspace for reviewing incidents, agent activity, and RCA reports.")

incidents = list_incidents(limit=200)
if not incidents:
    st.info("No incidents yet. Seed an incident and refresh the page.")
    st.stop()

incident_df = pd.DataFrame(incidents)

with st.sidebar:
    st.header("Filters")
    statuses = sorted(incident_df["status"].dropna().unique().tolist())
    services = sorted(incident_df["service"].dropna().unique().tolist())
    severities = sorted(incident_df["severity"].dropna().unique().tolist())

    selected_statuses = st.multiselect("Status", statuses, default=statuses)
    selected_services = st.multiselect("Service", services, default=services)
    selected_severities = st.multiselect("Severity", severities, default=severities)
    search = st.text_input("Search incidents", placeholder="id, service, severity")

filtered_df = incident_df[
    incident_df["status"].isin(selected_statuses)
    & incident_df["service"].isin(selected_services)
    & incident_df["severity"].isin(selected_severities)
].copy()

if search:
    query = search.lower()
    filtered_df = filtered_df[
        filtered_df.apply(
            lambda row: query in " ".join(str(value).lower() for value in row.values),
            axis=1,
        )
    ]

if filtered_df.empty:
    st.warning("No incidents match the current filters.")
    st.stop()

total_incidents = int(len(filtered_df))
open_incidents = int((filtered_df["status"] == "OPEN").sum())
critical_incidents = int((filtered_df["severity"] == "CRITICAL").sum())
services_impacted = int(filtered_df["service"].nunique())

metric_cols = st.columns(4)
metric_cols[0].metric("Visible Incidents", total_incidents)
metric_cols[1].metric("Open", open_incidents)
metric_cols[2].metric("Critical", critical_incidents)
metric_cols[3].metric("Services", services_impacted)

left, right = st.columns([1.05, 1.95], gap="large")

with left:
    st.subheader("Incident Queue")
    st.caption("Filtered list of incidents ordered by most recent creation time.")
    st.dataframe(
        filtered_df[["id", "status", "service", "environment", "severity", "created_at"]],
        use_container_width=True,
        hide_index=True,
        height=380,
    )

    options = {
        f"{row['service']} | {row['severity']} | {row['status']} | {row['created_at']}": row["id"]
        for row in filtered_df.to_dict(orient="records")
    }
    selected_label = st.selectbox("Active Incident", list(options.keys()), index=0)
    selected_id = options[selected_label]

with right:
    incident = get_incident(selected_id)
    report = get_latest_report(selected_id)
    steps = list_steps(selected_id)

    st.subheader(f"Incident {selected_id}")
    info_cols = st.columns(4)
    info_cols[0].metric("Service", incident["service"])
    info_cols[1].metric("Environment", incident["environment"])
    info_cols[2].metric("Severity", incident["severity"])
    info_cols[3].metric("Status", incident["status"])
    st.caption(f"Created at {incident['created_at']}")

    payload = incident.get("payload") or {}
    with st.expander("Incident Payload", expanded=bool(payload)):
        if payload:
            st.json(payload)
        else:
            st.write("No structured payload recorded for this incident.")

    st.markdown("### Agent Timeline")
    if steps:
        for step in steps:
            label = f"{step['agent'].upper()} · {step['phase']} · {step.get('status') or 'N/A'}"
            with st.expander(label, expanded=step == steps[-1]):
                st.write(step["message"])
                st.caption(step["ts"])
                if step.get("data"):
                    st.json(step["data"])
    else:
        st.info("No agent steps recorded yet.")

    st.markdown("### Final Report")
    if report:
        report_body = report.get("report") or {}
        summary_cols = st.columns(3)
        summary_cols[0].metric("Issue", report_body.get("issue", "Unknown"))
        summary_cols[1].metric("Confidence", str(report_body.get("confidence", "n/a")))
        summary_cols[2].metric("Mitigations", len(report_body.get("mitigations", [])))

        st.markdown(report["report_md"])
        if report_body:
            with st.expander("Structured Report JSON"):
                st.json(report_body)

        download_cols = st.columns(2)
        download_cols[0].download_button(
            "Download JSON",
            data=json.dumps(report_body, indent=2),
            file_name=f"incident_{selected_id}_report.json",
            mime="application/json",
            use_container_width=True,
        )
        download_cols[1].download_button(
            "Download Markdown",
            data=report["report_md"],
            file_name=f"incident_{selected_id}_report.md",
            mime="text/markdown",
            use_container_width=True,
        )
    else:
        st.info("No report generated yet for this incident.")
