# backend/app/services/college_service.py
"""Colleges and the email domains each one accepts at registration.

ALLOWED_COLLEGES is the fixed list of colleges. Their accepted domains come from
DEFAULT_COLLEGE_EMAIL_DOMAINS, overridden per college by the COLLEGE_EMAIL_DOMAINS
setting (a JSON object). sync_colleges() runs at startup and makes the colleges
table match: the setting is the source of truth for domains. A college with no
domains has registration closed.
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import user_model

logger = logging.getLogger(__name__)

ALLOWED_COLLEGES = [
    "DJSCE",
    "SPIT",
    "VJTI",
    "KJ SOMAIYA COLLEGE OF ENGINEERING",
    "THAKUR COLLEGE OF ENGINEERING",
    "ST. FRANCIS COLLEGE OF ENGINEERING",
]

DEFAULT_COLLEGE_EMAIL_DOMAINS: dict[str, list[str]] = {
    "DJSCE": ["djsce.ac.in"],
}


def normalize_domain(domain: str) -> str:
    return domain.strip().lower().lstrip("@").rstrip(".")


def _normalize_domains(domains) -> list[str]:
    seen: list[str] = []
    for domain in domains or []:
        if not isinstance(domain, str):
            continue
        value = normalize_domain(domain)
        if value and value not in seen:
            seen.append(value)
    return seen


def configured_domains() -> dict[str, list[str]]:
    """Effective name -> domains mapping for ALLOWED_COLLEGES (defaults + setting)."""
    mapping = {name: list(DEFAULT_COLLEGE_EMAIL_DOMAINS.get(name, [])) for name in ALLOWED_COLLEGES}
    overrides = settings.COLLEGE_EMAIL_DOMAINS or {}
    by_upper = {name.upper(): name for name in ALLOWED_COLLEGES}
    for raw_name, domains in overrides.items():
        name = by_upper.get(str(raw_name).strip().upper())
        if name is None:
            logger.warning("COLLEGE_EMAIL_DOMAINS names an unknown college; ignoring that entry")
            continue
        mapping[name] = _normalize_domains(domains)
    return {name: _normalize_domains(domains) for name, domains in mapping.items()}


def canonical_college_name(name: str | None) -> str | None:
    """The ALLOWED_COLLEGES spelling of ``name`` (case-insensitive), or None."""
    if not name:
        return None
    wanted = name.strip().upper()
    for allowed in ALLOWED_COLLEGES:
        if allowed.upper() == wanted:
            return allowed
    return None


def get_or_create_college(db: Session, college_name: str) -> user_model.College:
    """Fetch a college by name, creating it (with its configured domains) if missing."""
    college = db.query(user_model.College).filter(user_model.College.name == college_name).first()
    if college is not None:
        return college
    domains = configured_domains().get(college_name, [])
    college = user_model.College(name=college_name, email_domains=domains)
    db.add(college)
    try:
        db.commit()
    except IntegrityError:  # created concurrently
        db.rollback()
        return db.query(user_model.College).filter(user_model.College.name == college_name).one()
    db.refresh(college)
    return college


def sync_colleges(db: Session) -> list[user_model.College]:
    """Upsert every ALLOWED_COLLEGES row with its configured domains. Idempotent."""
    try:
        return _sync_colleges_once(db)
    except IntegrityError:  # another process inserted the same college concurrently
        db.rollback()
        return _sync_colleges_once(db)


def _sync_colleges_once(db: Session) -> list[user_model.College]:
    mapping = configured_domains()
    existing = {
        c.name: c
        for c in db.query(user_model.College).filter(user_model.College.name.in_(ALLOWED_COLLEGES)).all()
    }
    rows = []
    for name in ALLOWED_COLLEGES:
        domains = mapping[name]
        row = existing.get(name)
        if row is None:
            row = user_model.College(name=name, email_domains=domains)
            db.add(row)
        elif list(row.email_domains or []) != domains:
            row.email_domains = domains
        rows.append(row)
    db.commit()
    return rows


def open_colleges(db: Session) -> list[user_model.College]:
    """Colleges that currently accept registrations (at least one domain), by id."""
    rows = db.query(user_model.College).order_by(user_model.College.id).all()
    return [row for row in rows if _normalize_domains(row.email_domains)]


def email_domain(email: str) -> str:
    return email.rpartition("@")[2]


def accepts_email(college: user_model.College, email: str) -> bool:
    return email_domain(email) in _normalize_domains(college.email_domains)
