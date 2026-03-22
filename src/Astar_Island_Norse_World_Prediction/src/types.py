from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NUM_CLASSES = 6
NUM_SEEDS = 5

# Grid values from Astar Island docs
GRID_EMPTY = 0
GRID_SETTLEMENT = 1
GRID_PORT = 2
GRID_RUIN = 3
GRID_FOREST = 4
GRID_MOUNTAIN = 5
GRID_OCEAN = 10
GRID_PLAINS = 11


def grid_value_to_class_index(value: int) -> int:
    if value in (GRID_EMPTY, GRID_OCEAN, GRID_PLAINS):
        return 0
    if value == GRID_SETTLEMENT:
        return 1
    if value == GRID_PORT:
        return 2
    if value == GRID_RUIN:
        return 3
    if value == GRID_FOREST:
        return 4
    if value == GRID_MOUNTAIN:
        return 5
    return 0


@dataclass
class ViewportRequest:
    round_id: str
    seed_index: int
    viewport_x: int
    viewport_y: int
    viewport_w: int = 15
    viewport_h: int = 15

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "seed_index": self.seed_index,
            "viewport_x": self.viewport_x,
            "viewport_y": self.viewport_y,
            "viewport_w": self.viewport_w,
            "viewport_h": self.viewport_h,
        }

