from app.db.dal import record_step, save_report, mark_done
from app.models.escalation_policy import compute_escalation_guidance

def compile_report(incident, analysis):
    # analysis is expected from analyst: {'issue':..., 'root_cause':..., 'mitigations':[...],'evidence':[...]}
    enrichment = (incident.get("payload") or {}).get("enrichment", {})
    escalation = compute_escalation_guidance(incident)
    retrieved_examples = analysis.get("retrieved_examples", [])
    retrieved_section = "\n".join(
        [
            f"- Pattern: `{example.get('pattern', 'unknown')}` -> {example.get('root_cause', 'unknown cause')}"
            for example in retrieved_examples
        ]
    ) or "- No retrieved examples"
    enrichment_section = "\n".join(
        [
            f"- Owner team: {enrichment.get('owner_team', 'n/a')}",
            f"- Primary contact: {enrichment.get('primary_contact', 'n/a')}",
            f"- Runbook: {enrichment.get('runbook_url', 'n/a')}",
            f"- Dashboard: {enrichment.get('dashboard_url', 'n/a')}",
            f"- Deploy hint: {enrichment.get('recent_deploy_hint', 'n/a')}"
        ]
    )
    escalation_section = "\n".join(
        [
            f"- Priority: {escalation.get('priority', 'n/a')}",
            f"- Action: {escalation.get('action', 'n/a')}",
            f"- Target: {escalation.get('target', 'n/a')}",
            f"- Reason: {escalation.get('reason', 'n/a')}",
        ]
    )
    report_md = f"""
# Incident {incident['id']} — {incident.get('service','unknown')}

**Issue**: {analysis.get('issue','TBD')}

**Root Cause**: {analysis.get('root_cause','TBD')}

**Confidence**: {analysis.get('confidence', 'n/a')}

**Suggested Mitigations**
{chr(10).join([f'- {m}' for m in analysis.get('mitigations',[])]) or '- TBD'}

**Evidence**
{chr(10).join([f'- {e}' for e in analysis.get('evidence',[])]) or '- TBD'}

**Service Context**
{enrichment_section}

**Escalation Guidance**
{escalation_section}

**Retrieved Context**
{retrieved_section}
"""
    report_json = dict(analysis)
    report_json["escalation"] = escalation
    return report_json, report_md

def supervisor_orchestrate(incident, analysis):
    record_step(incident['id'], 'supervisor', 'summarize', 'Compiling final report')
    report_json, report_md = compile_report(incident, analysis)
    save_report(incident['id'], report_json, report_md)
    mark_done(incident['id'])
    record_step(incident['id'], 'supervisor', 'done', 'Incident processing complete')
