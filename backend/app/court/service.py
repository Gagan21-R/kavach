from sqlalchemy.orm import Session

from app import audit_log
from app.court.pipeline import run_trial
from app.models import AnalysisRun, PolicySnapshot, PolicySource


def analyze(db: Session, policy: PolicySource, snapshot: PolicySnapshot, actor_type: str = "system", actor_id: str | None = None) -> AnalysisRun:
    """Runs the court on one snapshot and makes it the policy's current analysis. Caller commits."""
    result = run_trial(snapshot.text, snapshot_id=snapshot.id, policy_hash=snapshot.content_hash, app_name=policy.name)
    s = result["summary"]
    run = AnalysisRun(
        user_id=policy.user_id,
        source_id=policy.id,
        snapshot_id=snapshot.id,
        snapshot_version=snapshot.version,
        status=result["status"],
        recommendation=s["recommendation"],
        audit_verdict=s["audit_verdict"],
        risk_score=s["risk_score"],
        sentinel_suspicious=s["sentinel_suspicious"],
        headline=s["headline"],
        result=result,
    )
    db.add(run)
    db.flush()
    policy.current_analysis_id = run.id
    audit_log.record(
        db, "policy.analyzed", user_id=policy.user_id, actor_type=actor_type, actor_id=actor_id,
        target_type="policy", target_id=policy.id, decision=s["recommendation"],
        details={"analysis_id": run.id, "version": snapshot.version, "status": run.status, "audit_verdict": run.audit_verdict,
                 "risk_score": run.risk_score, "sentinel_suspicious": run.sentinel_suspicious},
    )
    return run
