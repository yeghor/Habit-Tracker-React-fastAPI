from os import getenv
from dotenv import load_dotenv
from typing import Tuple, Annotated

load_dotenv()

BASE_LEVEL_XP = int(getenv("BASE_LEVEL_XP"))
XP_GROWTH_RATE = float(getenv("XP_GROWTH_RATE"))


def get_level_by_xp(current_xp: int) -> Tuple[int, int]:
    level = 1
    total_xp = 0

    while True:
        xp_needed_to_next_level = int(
            BASE_LEVEL_XP * (XP_GROWTH_RATE ** (level - 1)))
        if current_xp < total_xp + xp_needed_to_next_level:
            break
        total_xp += xp_needed_to_next_level
        level += 1

    next_level_total_cost = int(
        BASE_LEVEL_XP * (XP_GROWTH_RATE ** (level - 1)))
    xp_remaining = total_xp + next_level_total_cost - current_xp

    return int(level), int(xp_remaining)


def get_xp_nedeed_by_level(level: int) -> int:
    if level == 1:
        return 50
    elif level == 0:
        return 0

    current_xp = BASE_LEVEL_XP
    for i in range(1, level+1):
        if i == 1:
            continue
        current_xp = current_xp * XP_GROWTH_RATE
    return int(current_xp)
