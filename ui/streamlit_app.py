import json

import pandas as pd
import streamlit as st

from app.db.dal import get_incident, get_latest_report, list_incidents, list_steps


def _text(value):
    return str(value) if value not in (None, "") else "n/a"


def _render_key_value_table(rows):
    if not rows:
        st.write("No additional details available.")
        return
    st.table(pd.DataFrame(rows, columns=["Field", "Value"]))


st.set_page_config(page_title="OnCallAI", layout="wide")
st.title("OnCallAI")
st.caption("AI-assisted incident triage workspace for reviewing alerts, agent activity, and RCA reports.")

toolbar_left, toolbar_right = st.columns([3, 1])
with toolbar_left:
    st.caption("Use the filters to narrow the queue and inspect ingested alert context alongside agent output.")
with toolbar_right:
    if st.button("Refresh Data", width="stretch"):
        st.rerun()

incidents = list_incidents(limit=200)
if not incidents:
    st.info("No incidents yet. Seed or ingest an alert and refresh the page.")
    st.stop()

incident_df = pd.DataFrame(incidents)

with st.sidebar:
    st.header("Filters")
    statuses = sorted(incident_df["status"].dropna().unique().tolist())
    services = sorted(incident_df["service"].dropna().unique().tolist())
    severities = sorted(incident_df["severity"].dropna().unique().tolist())
    environments = sorted(incident_df["environment"].dropna().unique().tolist())
    sources = sorted(incident_df["source"].dropna().unique().tolist())

    selected_statuses = st.multiselect("Status", statuses, default=statuses)
    selected_services = st.multiselect("Service", services, default=services)
    selected_severities = st.multiselect("Severity", severities, default=severities)
    selected_environments = st.multiselect("Environment", environments, default=environments)
    selected_sources = st.multiselect("Source", sources, default=sources)
    search = st.text_input("Search incidents", placeholder="id, service, alarm, severity")

filtered_df = incident_df[
    incident_df["status"].isin(selected_statuses)
    & incident_df["service"].isin(selected_services)
    & incident_df["severity"].isin(selected_severities)
    & incident_df["environment"].isin(selected_environments)
    & incident_df["source"].isin(selected_sources)
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

metric_cols = st.columns(5)
metric_cols[0].metric("Visible Incidents", int(len(filtered_df)))
metric_cols[1].metric("Open", int((filtered_df["status"] == "OPEN").sum()))
metric_cols[2].metric("Critical", int((filtered_df["severity"] == "CRITICAL").sum()))
metric_cols[3].metric("CloudWatch", int((filtered_df["source"] == "cloudwatch").sum()))
metric_cols[4].metric("Services", int(filtered_df["service"].nunique()))

left, right = st.columns([1.05, 1.95], gap="large")

with left:
    st.subheader("Incident Queue")
    st.caption("Filtered incidents ordered by most recent creation time.")
    st.dataframe(
        filtered_df[
            ["id", "status", "service", "environment", "severity", "source", "created_at"]
        ],
        width="stretch",
        hide_index=True,
        height=400,
    )

    options = {
        (
            f"{row['service']} | {row['severity']} | {row['status']} | "
            f"{_text(row['alarm_name'])} | {row['created_at']}"
        ): row["id"]
        for row in filtered_df.to_dict(orient="records")
    }
    selected_label = st.selectbox("Active Incident", list(options.keys()), index=0)
    selected_id = options[selected_label]

with right:
    incident = get_incident(selected_id)
    report = get_latest_report(selected_id)
    steps = list_steps(selected_id)
    payload = incident.get("payload") or {}
    enrichment = payload.get("enrichment") or {}
    raw_alert = payload.get("raw_alert") or {}
    severity = incident["severity"]
    status = incident["status"]

    st.subheader(f"Incident {selected_id}")
    summary_cols = st.columns(5)
    summary_cols[0].metric("Service", incident["service"])
    summary_cols[1].metric("Environment", incident["environment"])
    summary_cols[2].metric("Severity", incident["severity"])
    summary_cols[3].metric("Status", incident["status"])
    summary_cols[4].metric("Source", payload.get("source", "manual"))
    st.caption(f"Created at {incident['created_at']}")

    if severity == "CRITICAL":
        st.error(f"Critical incident for {incident['service']} is currently {status}.")
    elif status == "OPEN":
        st.warning(f"Open incident for {incident['service']} awaiting or undergoing response.")
    else:
        st.success(f"Incident status is {status}.")

    overview_tab, timeline_tab, report_tab, raw_tab = st.tabs(["Overview", "Timeline", "Report", "Raw Data"])

    with overview_tab:
        st.markdown("### Alert Summary")
        alert_cols = st.columns(4)
        alert_cols[0].metric("Alert Type", payload.get("alert_type", "incident"))
        alert_cols[1].metric("Alarm State", payload.get("state", "n/a"))
        alert_cols[2].metric("Region", payload.get("region", "n/a"))
        alert_cols[3].metric("Alarm Name", payload.get("alarm_name", "n/a"))

        _render_key_value_table(
            [
                ("Alarm Name", _text(payload.get("alarm_name"))),
                ("Alarm ARN", _text(payload.get("alarm_arn"))),
                ("Reason", _text(payload.get("reason"))),
                ("Source", _text(payload.get("source"))),
                ("Alert Type", _text(payload.get("alert_type"))),
                ("Region", _text(payload.get("region"))),
                ("State", _text(payload.get("state"))),
            ]
        )

        st.markdown("### Service Context")
        _render_key_value_table(
            [
                ("Owner Team", _text(enrichment.get("owner_team"))),
                ("Primary Contact", _text(enrichment.get("primary_contact"))),
                ("Runbook", _text(enrichment.get("runbook_url"))),
                ("Dashboard", _text(enrichment.get("dashboard_url"))),
                ("Service Tier", _text(enrichment.get("service_tier"))),
                ("Escalation Policy", _text(enrichment.get("escalation_policy"))),
                ("Deploy Hint", _text(enrichment.get("recent_deploy_hint")))
            ]
        )

    with timeline_tab:
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

    with report_tab:
        st.markdown("### Final Report")
        if report:
            report_body = report.get("report") or {}
            report_cols = st.columns(4)
            report_cols[0].metric("Issue", report_body.get("issue", "Unknown"))
            report_cols[1].metric("Confidence", str(report_body.get("confidence", "n/a")))
            report_cols[2].metric("Mitigations", len(report_body.get("mitigations", [])))
            report_cols[3].metric("Evidence Items", len(report_body.get("evidence", [])))

            evidence = report_body.get("evidence", [])
            mitigations = report_body.get("mitigations", [])
            retrieved_examples = report_body.get("retrieved_examples", [])

            insight_left, insight_right = st.columns(2, gap="large")
            with insight_left:
                st.markdown("#### Recommended Mitigations")
                if mitigations:
                    for item in mitigations:
                        st.write(f"- {item}")
                else:
                    st.write("No mitigations recorded.")

                st.markdown("#### Evidence")
                if evidence:
                    for item in evidence:
                        st.write(f"- {item}")
                else:
                    st.write("No evidence recorded.")

                st.markdown("#### Service Context")
                if enrichment:
                    st.write(f"- Owner team: {enrichment.get('owner_team', 'n/a')}")
                    st.write(f"- Primary contact: {enrichment.get('primary_contact', 'n/a')}")
                    st.write(f"- Runbook: {enrichment.get('runbook_url', 'n/a')}")
                else:
                    st.write("No service enrichment available.")

            with insight_right:
                st.markdown("#### Retrieved Context")
                if retrieved_examples:
                    for example in retrieved_examples:
                        st.write(
                            f"- `{example.get('pattern', 'unknown')}` -> {example.get('root_cause', 'unknown cause')}"
                        )
                else:
                    st.write("No retrieved context available.")

                st.markdown("#### Markdown Report")
                st.markdown(report["report_md"])

            with st.expander("Structured Report JSON", expanded=False):
                st.json(report_body)

            download_cols = st.columns(2)
            download_cols[0].download_button(
                "Download JSON",
                data=json.dumps(report_body, indent=2),
                file_name=f"incident_{selected_id}_report.json",
                mime="application/json",
                width="stretch",
            )
            download_cols[1].download_button(
                "Download Markdown",
                data=report["report_md"],
                file_name=f"incident_{selected_id}_report.md",
                mime="text/markdown",
                width="stretch",
            )
        else:
            st.info("No report generated yet for this incident.")

    with raw_tab:
        st.markdown("### Incident Payload")
        if payload:
            st.json(payload)
        else:
            st.write("No structured payload recorded for this incident.")

        if raw_alert:
            st.markdown("### Raw Alert JSON")
            st.json(raw_alert)
        else:
            st.caption("No raw alert payload available for this incident.")
