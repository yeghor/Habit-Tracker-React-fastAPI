from fastapi import HTTPException, Body, Header, Depends, APIRouter, Request
from typing import Annotated, Dict, List
from schemas import TokenSchema, AddHabitSchema, HabitIdProvidedSchema  
from uuid import uuid4
import datetime
from models import Users, JWTTable, Habits, HabitCompletions
from sqlalchemy.orm import Session
from depends_utils import (
    get_user_depends,
    get_habit_depends,
)
from db_utils import get_db, get_merged_user, get_merged_habit
from GeneratingAuthUtils.jwt_token_handling import extract_payload
from ValidationUtils.validate_entries import validate_string, validate_reset_time
import datetime
import os
from dotenv import load_dotenv
import random
from schemas import HabitSchema, HabitCompletionSchema
from sqlalchemy.exc import SQLAlchemyError
import asyncio
from periodic_tasks import get_seconds_from_midnight
from user_xp_level_util import get_level_by_xp
from rate_limiter import limiter

habit_router = APIRouter()
load_dotenv()


XP_AFTER_COMPLETION = int(os.getenv("XP_AFTER_COMPLETION"))
XP_RANDOM_FACTOR = int(os.getenv("XP_RANDOM_FACTOR"))

MAX_HABITS = int(os.getenv("MAX_HABITS"))

# Providing Request object to every root because slowAPI requires it.

@habit_router.post("/add_habit")
@limiter.limit("20/minute")
async def add_habit(
    request: Request,
    habit: AddHabitSchema = Body(...),
    user: Users = Depends(get_user_depends),
    db: Session = Depends(get_db),
) -> HabitSchema:
    user = get_merged_user(user=user, db=db)

    if len(user.habits) + 1 > MAX_HABITS:
        raise HTTPException(status_code=400, detail="You can't add more habits. Each user can have up to 10 habits.")

    if not validate_string(habit.habit_name) or not validate_string(habit.habit_desc):
        raise HTTPException(status_code=400, detail="Invalid habit name or description")
    if not validate_reset_time(habit.reset_at):
        raise HTTPException(status_code=400, detail="Invalid resetting time")

    reset_at_final = {}
    for reset_time in habit.reset_at:
        reset_at_final[reset_time] = False

    habit_id = str(uuid4())

    try:
        new_habit = Habits(
            habit_id=habit_id,
            habit_name=habit.habit_name,
            habit_desc=habit.habit_desc,
            user_id=user.user_id,
            date_created=datetime.datetime.today(),
            reset_at=reset_at_final,
            owner=user,
        )

        user.habits.append(new_habit)

        db.commit()
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Error while working with database")

    return new_habit


@habit_router.get("/get_habits")
# @limiter.limit("20/minute")
async def get_habits(
    request: Request,
    user: Users = Depends(get_user_depends),
    db: Session = Depends(get_db)
) -> List[HabitSchema]:
    user = get_merged_user(user=user, db=db)
    return user.habits


@habit_router.post("/habit_completion")
@limiter.limit("20/minute")
async def habit_completion(
    request: Request,
    habit: Habits = Depends(get_habit_depends),
    user: Users = Depends(get_user_depends),
    db: Session = Depends(get_db),
) -> None:
    user = get_merged_user(user=user, db=db)
    habit = get_merged_habit(habit=habit, db=db)

    if user.user_id != habit.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized. You're not owner of this habit")

    if habit.completed:
        raise HTTPException(
            status_code=409,
            detail="This habit is already completed. Wait until it's resetting time",
        )
    try:
        xp_for_completion = int(XP_AFTER_COMPLETION * random.randrange(1, XP_RANDOM_FACTOR + 1))

        habit_completion = HabitCompletions(
            completion_id=str(uuid4()),
            habit_id=habit.habit_id,
            habit_name=habit.habit_name,
            user_id=user.user_id,
            completed_at=datetime.datetime.today().timestamp(),
            xp_given=xp_for_completion,
            owner=user,
            habit=habit,
        )

        from_midnight_unix = get_seconds_from_midnight()
        reset_at = habit.reset_at
        reset_at_sorted = dict(sorted(reset_at.items()))
        for time, flag in reset_at_sorted.items():
            if from_midnight_unix > int(time) and not flag:
                reset_at_sorted[time] = True

        try:
            user.completions.append(habit_completion)
            habit.completions.append(habit_completion)

            user.xp += int(xp_for_completion)

            habit.completed = True

        except SQLAlchemyError:
            raise HTTPException(status_code=500, detail="Error while working with database")
    finally:
        db.commit()
        db.refresh(habit_completion)
        db.refresh(user)


@habit_router.post("/uncomplete_habit")
@limiter.limit("20/minute")
async def uncomplete_habit(
    request: Request,
    habit: Habits = Depends(get_habit_depends),
    user: Users = Depends(get_user_depends),
    db: Session = Depends(get_db),
):
    user = get_merged_user(user=user, db=db)
    habit = get_merged_habit(habit=habit, db=db)

    if user.user_id != habit.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized. You're not owner of this habit")

    try:
        habit_completion = db.query(HabitCompletions).order_by(HabitCompletions.completed_at).first()

    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Error while worrking with database")

    if not habit_completion:
        raise HTTPException(status_code=400, detail="No habit completion entries were made")

    if not habit.completed:
        raise HTTPException(status_code=400, detail="This habit is not completed, make a completion to be able to uncomplete habit")
      
    try:
        db.delete(habit_completion)
        habit.completed = False

        user.xp -= int(habit_completion.xp_given)
        level, xp_needed = get_level_by_xp(user.xp)
        user.level = level
        
        db.commit()
        db.refresh(user)
        db.refresh(habit)

    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Error while worrking with database")

@habit_router.post("/delete_habit")
@limiter.limit("20/minute")
async def delete_habit(
    request: Request,
    habit = Depends(get_habit_depends),
    user: Users = Depends(get_user_depends),
    db: Session = Depends(get_db),
) -> None:
    user = get_merged_user(user=user, db=db)
    habit = get_merged_habit(habit=habit, db=db)

    if habit.user_id != user.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized. You're not owner of this habit")

    db.delete(habit)
    db.commit()


@habit_router.post("/get_habit_completions")
@limiter.limit("20/minute")
async def get_completions(
    request: Request,
    habit = Depends(get_habit_depends),
    user: Users = Depends(get_user_depends),
    db: Session = Depends(get_db),
) -> List[HabitCompletionSchema]:
    user = get_merged_user(user=user, db=db)
    habit = get_merged_habit(habit=habit, db=db)

    if habit.user_id != user.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized. You're not owner of this habit")

    return habit.completions

@habit_router.get("/get_all_completions")
@limiter.limit("20/minute")
async def get_all_completions(
    request: Request,
    user: Users = Depends(get_user_depends),
    db: Session = Depends(get_db)
) -> List[HabitCompletionSchema]:
    user = get_merged_user(user=user, db=db)
    
    list_to_return = []

    for completion in user.completions:
        list_to_return.append(HabitCompletionSchema(
            completion_id=completion.completion_id,
            habit_id=completion.habit_id,
            habit_name=completion.habit.habit_name,
            completed_at=str(completion.completed_at)
        ))
    
    return reversed(list_to_return)