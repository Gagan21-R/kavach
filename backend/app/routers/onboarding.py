"""First-run preferences: what data the user is OK sharing, for which uses, and which services they use.

Answers become Constitution rules. Saving any "OK" (an ALLOW rule) or replacing earlier answers loosens
protection, so it needs recent re-authentication, like any other loosening change. Chosen services are fetched
and analysed in the background so the user is not kept waiting.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import audit_log, clock
from app.acquire.catalogue import BY_ID, SERVICES
from app.acquire.tracking import track_service
from app.auth.deps import UserContext, current_user, require_step_up
from app.db import get_db
from app.errors import APIError
from app.models import ConsentRule, User
from app.preferences import DATA_GROUPS, USES, default_choices, rules_from_choices
from app.schemas.api import Strict

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
log = logging.getLogger("consent_court.onboarding")
PREFIX = "Preferences:"


def _current_choices(db: Session, user_id: str) -> dict | None:
    rules = list(db.execute(select(ConsentRule).where(ConsentRule.user_id == user_id, ConsentRule.active.is_(True),
                                                      ConsentRule.group_id.is_(None), ConsentRule.description.startswith(PREFIX))).scalars())
    if not rules:
        return None
    answer = {"ALLOW": "OK", "REQUIRE_APPROVAL": "ASK", "DENY": "NEVER"}
    out = {g: {} for g in DATA_GROUPS}
    for r in rules:
        use = next((u for u, spec in USES.items() if set(spec["purposes"]) == set(r.purposes)), None)
        for g, spec in DATA_GROUPS.items():
            if use and set(spec["categories"]) <= set(r.data_categories):
                out[g][use] = answer[r.effect]
    return out


@router.get("")
def state(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    return {
        "onboarded": ctx.user.onboarded_at is not None,
        "groups": [{"id": g, "label": s["label"]} for g, s in DATA_GROUPS.items()],
        "uses": [{"id": u, "label": s["label"]} for u, s in USES.items()],
        "defaults": default_choices(),
        "current": _current_choices(db, ctx.user.id),
        "services": [{"id": s["id"], "name": s["name"], "domain": s["domain"], "region": s["region"]} for s in SERVICES],
    }


class PreferencesIn(Strict):
    choices: dict[str, dict[str, str]] = Field(default_factory=dict)
    services: list[str] = Field(default_factory=list, max_length=25)
    skip: bool = False


def _track_in_background(factory: sessionmaker, user_id: str, service_ids: list[str]) -> None:
    for sid in service_ids:
        with factory() as db:
            try:
                track_service(db, db.get(User, user_id), sid, actor="system")
                db.commit()
            except Exception:
                db.rollback()
                log.exception("background tracking failed for %s", sid)


@router.post("")
def save(body: PreferencesIn, background: BackgroundTasks, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    user = ctx.user
    unknown = [s for s in body.services if s not in BY_ID]
    if unknown:
        raise APIError(422, "UNKNOWN_SERVICE", f"unknown services: {', '.join(unknown)}")
    created = []
    if not body.skip:
        for g, per_use in body.choices.items():
            if g not in DATA_GROUPS or any(u not in USES or a not in ("OK", "ASK", "NEVER") for u, a in per_use.items()):
                raise APIError(422, "INVALID_CHOICE", "each answer must be OK, ASK or NEVER for a known data type and use")
        specs = rules_from_choices(body.choices)
        old = list(db.execute(select(ConsentRule).where(ConsentRule.user_id == user.id, ConsentRule.active.is_(True),
                                                        ConsentRule.group_id.is_(None), ConsentRule.description.startswith(PREFIX))).scalars())
        if old or any(s["effect"] == "ALLOW" for s in specs):
            require_step_up(ctx)
        now = clock.utcnow()
        for r in old:
            r.active, r.revoked_at = False, now
        for s in specs:
            user.constitution_version += 1
            rule = ConsentRule(user_id=user.id, effect=s["effect"], data_categories=s["data_categories"], purposes=s["purposes"],
                               recipients=[], actions=[], description=s["description"], constitution_version=user.constitution_version)
            db.add(rule)
            created.append(rule)
        db.flush()
        audit_log.record(db, "preferences.saved", user_id=user.id, actor_type="user", actor_id=user.id, target_type="user",
                         target_id=user.id, details={"rules_created": [r.id for r in created], "rules_replaced": [r.id for r in old],
                                                     "services": body.services})
    user.onboarded_at = user.onboarded_at or clock.utcnow()
    db.commit()
    if body.services:
        background.add_task(_track_in_background, sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False),
                            user.id, list(dict.fromkeys(body.services)))
    return {"onboarded": True, "rules_created": len(created), "tracking": body.services}
