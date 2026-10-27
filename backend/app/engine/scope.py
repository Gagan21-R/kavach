"""Which of the user's rules apply to a website.

A site the user placed in a rule group is judged only by that group's rules, and anything the group doesn't allow
or mark "ask me" is denied. Every other site is judged by the general rules (sign-up answers plus any rule added
in the ledger), where anything not covered needs the user's approval.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.acquire.discover import normalize_domain
from app.acquire.tracking import site_domain
from app.models import ConsentRule, GroupSite, RuleGroup


@dataclass
class Scope:
    rules: list[ConsentRule]
    group: RuleGroup | None

    @property
    def deny_unlisted(self) -> str | None:
        return self.group.name if self.group else None

    @property
    def label(self) -> str:
        return f"{self.group.name} group" if self.group else "General rules"


def group_for(db: Session, user_id: str, destination: str) -> RuleGroup | None:
    host = normalize_domain(destination) or destination
    gs = db.execute(select(GroupSite).where(GroupSite.user_id == user_id, GroupSite.domain == site_domain(host))).scalar_one_or_none()
    return db.get(RuleGroup, gs.group_id) if gs else None


def scope_for(db: Session, user_id: str, destination: str) -> Scope:
    group = group_for(db, user_id, destination)
    q = select(ConsentRule).where(ConsentRule.user_id == user_id, ConsentRule.active.is_(True))
    q = q.where(ConsentRule.group_id == group.id) if group else q.where(ConsentRule.group_id.is_(None))
    return Scope(list(db.execute(q).scalars()), group)
