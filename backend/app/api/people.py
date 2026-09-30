from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.person import PersonCreate, PersonOut, PersonUpdate
from app.services import people_service

router = APIRouter(prefix="/api/people", tags=["people"])


@router.get("", response_model=list[PersonOut])
def list_people(include_archived: bool = False, db: Session = Depends(get_db)) -> list[PersonOut]:
    return people_service.list_people(db, include_archived=include_archived)


@router.post("", response_model=PersonOut, status_code=201)
def create_person(payload: PersonCreate, db: Session = Depends(get_db)) -> PersonOut:
    return people_service.create_person(db, payload)


@router.patch("/{person_id}", response_model=PersonOut)
def update_person(person_id: int, payload: PersonUpdate, db: Session = Depends(get_db)) -> PersonOut:
    person = people_service.get_person(db, person_id)
    return people_service.update_person(db, person, payload)


@router.delete("/{person_id}", status_code=204)
def delete_person(person_id: int, db: Session = Depends(get_db)) -> None:
    person = people_service.get_person(db, person_id)
    people_service.delete_person(db, person)
