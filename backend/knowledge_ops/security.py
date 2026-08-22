from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_ops.models import CollectionAccess, User

ROLES = {"admin", "editor", "reviewer", "viewer"}
WRITE_ROLES = {"admin", "editor"}
REVIEW_ROLES = {"admin", "reviewer"}


@dataclass(frozen=True)
class Identity:
    id: str
    username: str
    display_name: str
    role: str


def demo_username(x_demo_user: str = Header(default="viewer", alias="X-Demo-User")) -> str:
    """Resolve a local demo identity.

    This header is intentionally not production authentication. The API rejects unknown
    identities and the README documents the OIDC/SSO replacement boundary.
    """

    return x_demo_user.strip().lower()


def resolve_identity(db: Session, username: str) -> Identity:
    user = db.scalar(select(User).where(User.username == username, User.active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown demo user")
    return Identity(user.id, user.username, user.display_name, user.role)


def require_roles(identity: Identity, allowed: set[str]) -> None:
    if identity.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


def can_access_collection(
    db: Session, identity: Identity, collection_id: str, *, write: bool = False
) -> bool:
    if identity.role == "admin":
        return True
    grant = db.scalar(
        select(CollectionAccess).where(
            CollectionAccess.collection_id == collection_id,
            CollectionAccess.user_id == identity.id,
        )
    )
    if grant is None:
        return False
    return grant.can_write or not write


def require_collection_access(
    db: Session, identity: Identity, collection_id: str, *, write: bool = False
) -> None:
    if not can_access_collection(db, identity, collection_id, write=write):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Collection access denied",
        )
