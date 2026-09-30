from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.accounts import AccountOwner
from app.models.people import Person
from app.schemas.person import PersonCreate, PersonUpdate


def list_people(db: Session, include_archived: bool = False) -> list[Person]:
    query = select(Person)
    if not include_archived:
        query = query.where(Person.is_archived.is_(False))
    query = query.order_by(Person.sort_order, Person.name)
    return list(db.scalars(query).all())


def get_person(db: Session, person_id: int) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise NotFoundError(f"Person {person_id} not found")
    return person


def create_person(db: Session, payload: PersonCreate) -> Person:
    person = Person(**payload.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)

    from app.services import projection_service

    projection_service.bump_data_version()
    return person


def update_person(db: Session, person: Person, payload: PersonUpdate) -> Person:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)

    from app.services import projection_service

    projection_service.bump_data_version()
    return person


def delete_person(db: Session, person: Person) -> None:
    owns_account = (
        db.scalars(select(AccountOwner.account_id).where(AccountOwner.person_id == person.id).limit(1)).first()
        is not None
    )
    if owns_account:
        raise ConflictError("Delete or reassign this person's accounts before deleting them")
    db.delete(person)
    db.commit()
