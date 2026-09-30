from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.goals import Goal
from app.schemas.goal import GoalCreate, GoalOut, GoalUpdate
from app.services import goal_service

router = APIRouter(prefix="/api/goals", tags=["goals"])


def _to_out(db: Session, goal: Goal) -> GoalOut:
    out = GoalOut.model_validate(goal)
    out.current_value_gbp = round(goal_service.scoped_current_value(db, goal), 2)
    out.progress = (
        max(0.0, min(1.0, out.current_value_gbp / goal.target_gbp)) if goal.target_gbp else 0.0
    )
    out.projected_hit_date = goal_service.projected_hit_date(db, goal)
    return out


@router.get("", response_model=list[GoalOut])
def list_goals(db: Session = Depends(get_db)) -> list[GoalOut]:
    return [_to_out(db, g) for g in goal_service.list_goals(db)]


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)) -> GoalOut:
    goal = goal_service.create_goal(db, payload)
    return _to_out(db, goal)


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, payload: GoalUpdate, db: Session = Depends(get_db)) -> GoalOut:
    goal = goal_service.get_goal(db, goal_id)
    goal = goal_service.update_goal(db, goal, payload)
    return _to_out(db, goal)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int, db: Session = Depends(get_db)) -> None:
    goal = goal_service.get_goal(db, goal_id)
    goal_service.delete_goal(db, goal)
