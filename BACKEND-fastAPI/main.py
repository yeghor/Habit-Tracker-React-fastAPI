from fastapi import FastAPI, Request, HTTPException
from database import engine
from models import Base, Users, JWTTable, HabitCompletions, Habits
from apscheduler.schedulers.background import BackgroundScheduler
from auth_router import auth_router
from dotenv import load_dotenv
import os
from habit_router import habit_router
from periodic_tasks import update_jwts, reset_all_habits, reset_potential_habit
from fastapi.middleware.cors import CORSMiddleware
from utils_router import utils_router
import time
from typing import Any
import hashlib
from rate_limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import Limiter, _rate_limit_exceeded_handler

load_dotenv()

def periodic_task():
    update_jwts()
    reset_potential_habit()


def periodic_habit_resetting():
    reset_all_habits()


scheduler_interval = BackgroundScheduler()
scheduler_interval.add_job(
    periodic_task, "interval", seconds=int(os.getenv("PERIODIC_TASK_INTERVAL_SECONDS"))
)
scheduler_interval.add_job(
    periodic_habit_resetting,
    "cron",
    hour=int(os.getenv("HABIT_RESETTING_HOURS")),
    minute=0,
)
    
scheduler_interval.start()

app = FastAPI()

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)
app.include_router(habit_router)
app.include_router(utils_router)

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)

# temporary
def clear_tables():
    Users.__table__.drop(engine)
    JWTTable.__table__.drop(engine)
    Habits.__table__.drop(engine)
    HabitCompletions.__table__.drop(engine)

# clear_tables()