"""Data Flow Observatory: labelled assets, lineage, and the record of every instrumented flow.

Only metadata is stored (labels, categories, sources, transformations), never raw values. Visibility ends at the
gateway: flows that do not pass through POST /gateway/execute are outside the monitoring boundary.
"""
from collections import deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import APIError, not_found
from app.models import DataAsset, FlowEvent

COVERAGE = {
    "instrumented": [
        "Protected actions an agent sends through POST /gateway/execute (transfer_data, accept_terms, submit_form, create_account, send_message)",
        "Lineage of data assets registered in Consent Court, including derived assets",
        "Guardian decisions and token use, accepted or rejected",
    ],
    "not_instrumented": [
        "Network calls an agent makes directly, without the gateway",
        "What a recipient does with data after delivery (third-party processing, onward sharing)",
        "Browser extensions, OS-level telemetry and apps outside Consent Court",
        "Encrypted channels Consent Court is not a party to",
    ],
    "note": "In this build every gateway adapter is simulated: no data actually leaves the machine.",
}


def owned_asset(db: Session, user_id: str, asset_id: str) -> DataAsset:
    a = db.get(DataAsset, asset_id)
    if a is None or a.user_id != user_id:
        raise not_found("asset")
    return a


def create_asset(db: Session, user_id: str, *, label: str, categories: list[str], source: str = "",
                 derived_from: list[str] | None = None, transformation: str = "") -> DataAsset:
    parents = [owned_asset(db, user_id, pid) for pid in (derived_from or [])]
    if parents and not transformation:
        raise APIError(422, "TRANSFORMATION_REQUIRED", "describe how this asset was derived from its sources")
    asset = DataAsset(user_id=user_id, label=label, categories=sorted(set(categories)), source=source,
                      derived_from=[p.id for p in parents], transformation=transformation)
    db.add(asset)
    db.flush()
    return asset


def ancestors(db: Session, user_id: str, asset_id: str) -> list[DataAsset]:
    seen, out, queue = set(), [], deque([asset_id])
    while queue and len(seen) < 500:
        aid = queue.popleft()
        if aid in seen:
            continue
        seen.add(aid)
        a = owned_asset(db, user_id, aid)
        out.append(a)
        queue.extend(a.derived_from)
    return out


def effective_categories(db: Session, user_id: str, asset_id: str) -> set[str]:
    """A derived asset carries every category of everything it came from: a neighbourhood inferred from GPS is
    still location data."""
    return set().union(*(set(a.categories) for a in ancestors(db, user_id, asset_id)))


def lineage(db: Session, user_id: str, asset_id: str) -> dict:
    root = owned_asset(db, user_id, asset_id)
    nodes = {a.id: a for a in ancestors(db, user_id, root.id)}
    # descendants
    all_assets = list(db.execute(select(DataAsset).where(DataAsset.user_id == user_id)).scalars())
    frontier = {root.id}
    changed = True
    while changed:
        changed = False
        for a in all_assets:
            if a.id not in nodes and set(a.derived_from) & frontier:
                nodes[a.id] = a
                frontier.add(a.id)
                changed = True
    edges = [{"from": p, "to": a.id, "transformation": a.transformation} for a in nodes.values() for p in a.derived_from if p in nodes]
    flows = list(db.execute(select(FlowEvent).where(FlowEvent.user_id == user_id, FlowEvent.asset_id.in_(list(nodes)))
                            .order_by(FlowEvent.created_at.desc()).limit(100)).scalars())
    return {
        "root": root.id,
        "nodes": [asset_out(db, a) for a in nodes.values()],
        "edges": edges,
        "flows": [flow_out(f) for f in flows],
    }


def asset_out(db: Session, a: DataAsset) -> dict:
    return {"id": a.id, "label": a.label, "categories": a.categories,
            "effective_categories": sorted(effective_categories(db, a.user_id, a.id)), "source": a.source,
            "derived_from": a.derived_from, "transformation": a.transformation, "created_at": a.created_at}


def flow_out(f: FlowEvent) -> dict:
    return {"id": f.id, "agent_id": f.agent_id, "asset_id": f.asset_id, "action": f.action, "destination": f.destination,
            "purpose": f.purpose, "declared_categories": f.declared_categories, "effective_categories": f.effective_categories,
            "decision": f.decision, "outcome": f.outcome, "code": f.code, "reason": f.reason, "token_id": f.token_id,
            "records": f.records, "created_at": f.created_at}
