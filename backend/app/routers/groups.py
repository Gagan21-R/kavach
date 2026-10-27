"""Rule groups: named sets of answers for some websites ("Shopping", "Work", "Social").

In a group the user only chooses what is OK and what Kavach should ask about; everything else is denied for the
sites in it. A website that isn't in any group uses the general rules from sign-up. Creating or widening a group,
deleting one, or moving a site can loosen protection, so these need recent re-authentication (signing in counts).
"""
from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.acquire.catalogue import service_for_domain
from app.acquire.discover import normalize_domain
from app.acquire.tracking import site_domain
from app.auth.deps import UserContext, current_user, require_step_up
from app.db import get_db
from app.errors import APIError, not_found
from app.models import ConsentRule, GroupSite, PolicySource, RuleGroup, SiteVisit, User
from app.preferences import DATA_GROUPS, USES, rules_from_choices
from app.schemas.api import Strict

router = APIRouter(prefix="/rule-groups", tags=["rule groups"])


def _clean(choices: dict) -> dict:
    """Keep only OK / ASK answers for known data and uses: anything else is denied by being absent."""
    out = {}
    for g, per_use in (choices or {}).items():
        if g not in DATA_GROUPS:
            raise APIError(422, "INVALID_CHOICE", f"unknown kind of data: {g}")
        for u, a in (per_use or {}).items():
            if u not in USES or a not in ("OK", "ASK", "NEVER"):
                raise APIError(422, "INVALID_CHOICE", "answers must be OK, ASK or NEVER for a known use")
            if a in ("OK", "ASK"):
                out.setdefault(g, {})[u] = a
    return out


def _write_rules(db: Session, user: User, group: RuleGroup) -> int:
    now = clock.utcnow()
    for r in db.execute(select(ConsentRule).where(ConsentRule.group_id == group.id, ConsentRule.active.is_(True))).scalars():
        r.active, r.revoked_at = False, now
    specs = rules_from_choices(group.choices)
    for s in specs:
        user.constitution_version += 1
        db.add(ConsentRule(user_id=user.id, group_id=group.id, effect=s["effect"], data_categories=s["data_categories"],
                           purposes=s["purposes"], recipients=[], actions=[],
                           description=s["description"].replace("Preferences:", f"{group.name} group:"),
                           constitution_version=user.constitution_version))
    db.flush()
    return len(specs)


def _owned(db: Session, user_id: str, group_id: str) -> RuleGroup:
    g = db.get(RuleGroup, group_id)
    if g is None or g.user_id != user_id:
        raise not_found("rule group")
    return g


def _site_name(site: str) -> str:
    svc = service_for_domain(site)
    return svc["name"] if svc else site


def _out(db: Session, g: RuleGroup) -> dict:
    sites = db.execute(select(GroupSite.domain).where(GroupSite.group_id == g.id).order_by(GroupSite.domain)).scalars()
    flat = [a for per in g.choices.values() for a in per.values()]
    return {"id": g.id, "name": g.name, "choices": g.choices, "created_at": g.created_at,
            "sites": [{"domain": d, "name": _site_name(d)} for d in sites],
            "allowed": flat.count("OK"), "ask": flat.count("ASK")}


@router.get("")
def list_groups(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    groups = list(db.execute(select(RuleGroup).where(RuleGroup.user_id == ctx.user.id).order_by(RuleGroup.created_at)).scalars())
    grouped = set(db.execute(select(GroupSite.domain).where(GroupSite.user_id == ctx.user.id)).scalars())
    known = {site_domain(p.domain) for p in db.execute(select(PolicySource).where(PolicySource.user_id == ctx.user.id)).scalars()}
    known |= set(db.execute(select(SiteVisit.domain).where(SiteVisit.user_id == ctx.user.id)).scalars())
    return {
        "groups": [_out(db, g) for g in groups],
        "general_sites": [{"domain": d, "name": _site_name(d)} for d in sorted(known - grouped)],
        "data": [{"id": k, "label": v["label"]} for k, v in DATA_GROUPS.items()],
        "uses": [{"id": k, "label": v["label"]} for k, v in USES.items()],
    }


class GroupIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    choices: dict[str, dict[str, str]] = Field(default_factory=dict)
    sites: list[str] = Field(default_factory=list, max_length=200)  # websites to put in the group right away


class GroupPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    choices: dict[str, dict[str, str]] | None = None
    sites: list[str] | None = Field(default=None, max_length=200)  # the group's full list; left-out sites go back to general


def _set_sites(db: Session, user: User, group: RuleGroup, sites: list[str]) -> None:
    wanted = set()
    for raw in sites:
        host = normalize_domain(raw)
        if host is None:
            raise APIError(422, "INVALID_DOMAIN", f"not a website: {raw}")
        wanted.add(site_domain(host))
    for gs in list(db.execute(select(GroupSite).where(GroupSite.group_id == group.id)).scalars()):
        if gs.domain not in wanted:
            assign(db, user, gs.domain, None)
    current = set(db.execute(select(GroupSite.domain).where(GroupSite.group_id == group.id)).scalars())
    for site in sorted(wanted - current):
        assign(db, user, site, group.id)


@router.post("", status_code=201)
def create_group(body: GroupIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    choices = _clean(body.choices)
    if any(a == "OK" for per in choices.values() for a in per.values()):
        require_step_up(ctx)
    if db.execute(select(RuleGroup).where(RuleGroup.user_id == ctx.user.id, RuleGroup.name == body.name.strip())).first():
        raise APIError(409, "GROUP_EXISTS", "you already have a group with that name")
    g = RuleGroup(user_id=ctx.user.id, name=body.name.strip(), choices=choices)
    db.add(g)
    db.flush()
    n = _write_rules(db, ctx.user, g)
    if body.sites:
        require_step_up(ctx)
        _set_sites(db, ctx.user, g, body.sites)
    audit_log.record(db, "rule_group.created", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="rule_group", target_id=g.id, details={"name": g.name, "rules": n})
    db.commit()
    return _out(db, g)


@router.put("/{group_id}")
def update_group(group_id: str, body: GroupPatch, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    g = _owned(db, ctx.user.id, group_id)
    if body.choices is not None:
        require_step_up(ctx)  # may widen what the group's sites are allowed to do
        g.choices = _clean(body.choices)
        _write_rules(db, ctx.user, g)
    if body.name is not None:
        g.name = body.name.strip()
    if body.sites is not None:
        require_step_up(ctx)
        _set_sites(db, ctx.user, g, body.sites)
    audit_log.record(db, "rule_group.updated", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="rule_group", target_id=g.id, details={"name": g.name, "choices_changed": body.choices is not None})
    db.commit()
    return _out(db, g)


@router.delete("/{group_id}")
def delete_group(group_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """The group's sites go back to the general rules, which may allow more, so this needs re-authentication."""
    g = _owned(db, ctx.user.id, group_id)
    require_step_up(ctx)
    now = clock.utcnow()
    for r in db.execute(select(ConsentRule).where(ConsentRule.group_id == g.id, ConsentRule.active.is_(True))).scalars():
        r.active, r.revoked_at = False, now
    moved = [gs.domain for gs in db.execute(select(GroupSite).where(GroupSite.group_id == g.id)).scalars()]
    for gs in db.execute(select(GroupSite).where(GroupSite.group_id == g.id)).scalars():
        db.delete(gs)
    ctx.user.constitution_version += 1
    db.flush()
    db.delete(g)
    audit_log.record(db, "rule_group.deleted", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="rule_group", target_id=group_id, details={"sites_moved_to_general": moved})
    db.commit()
    return {"deleted": group_id, "sites_moved_to_general": moved}


class AssignIn(Strict):
    domain: str = Field(min_length=3, max_length=2048)
    group_id: str | None = Field(default=None, max_length=32)  # None: back to the general rules


def assign(db: Session, user: User, raw_domain: str, group_id: str | None) -> tuple[str, RuleGroup | None]:
    host = normalize_domain(raw_domain)
    if host is None:
        raise APIError(422, "INVALID_DOMAIN", "enter a website like spotify.com")
    site = site_domain(host)
    group = _owned(db, user.id, group_id) if group_id else None
    current = db.execute(select(GroupSite).where(GroupSite.user_id == user.id, GroupSite.domain == site)).scalar_one_or_none()
    if current is not None:
        db.delete(current)
        db.flush()
    if group is not None:
        db.add(GroupSite(user_id=user.id, group_id=group.id, domain=site))
    user.constitution_version += 1
    db.flush()
    audit_log.record(db, "rule_group.site_assigned", user_id=user.id, actor_type="user", actor_id=user.id,
                     target_type="site", target_id=site, details={"group_id": group.id if group else None,
                                                                 "group": group.name if group else "General rules"})
    return site, group


@router.post("/assign")
def assign_site(body: AssignIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Put a website in a group (or back in the general rules). Can loosen protection, so it needs re-authentication."""
    require_step_up(ctx)
    site, group = assign(db, ctx.user, body.domain, body.group_id)
    db.commit()
    return {"domain": site, "group_id": group.id if group else None, "label": f"{group.name} group" if group else "General rules"}


class AssignManyIn(Strict):
    domains: list[str] = Field(min_length=1, max_length=200)
    group_id: str | None = Field(default=None, max_length=32)


@router.post("/assign-many")
def assign_many(body: AssignManyIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Move several selected websites into a group (or back to the general rules) at once."""
    require_step_up(ctx)
    moved = [assign(db, ctx.user, d, body.group_id)[0] for d in body.domains]
    db.commit()
    return {"moved": moved, "group_id": body.group_id}
