from app.db.dal import record_step, save_report, mark_done
from markdown2 import markdown

def compile_report(incident, analysis):
    # analysis is expected from analyst: {'issue':..., 'root_cause':..., 'mitigations':[...],'evidence':[...]}
    report_md = f"""
# Incident {incident['id']} — {incident.get('service','unknown')}

**Issue**: {analysis.get('issue','TBD')}

**Root Cause**: {analysis.get('root_cause','TBD')}

**Suggested Mitigations**
{chr(10).join([f'- {m}' for m in analysis.get('mitigations',[])]) or '- TBD'}

**Evidence**
{chr(10).join([f'- {e}' for e in analysis.get('evidence',[])]) or '- TBD'}
"""
    report_json = analysis
    return report_json, report_md

def supervisor_orchestrate(incident, analysis):
    record_step(incident['id'], 'supervisor', 'summarize', 'Compiling final report')
    report_json, report_md = compile_report(incident, analysis)
    save_report(incident['id'], report_json, report_md)
    mark_done(incident['id'])
    record_step(incident['id'], 'supervisor', 'done', 'Incident processing complete')
