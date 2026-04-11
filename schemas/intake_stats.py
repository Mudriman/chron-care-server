# app/schemas/intake_stats.py
from pydantic import BaseModel
from typing import List


class PeriodStats(BaseModel):
    days: int
    total_taken: int
    total_scheduled: int
    adherence_rate: float
    best_streak: int
    current_streak: int


class TodayStats(BaseModel):
    taken: int
    scheduled: int
    progress: float


class ChartDataPoint(BaseModel):
    date: str
    taken: int
    scheduled: int
    adherence: float


class IntakeStatsResponse(BaseModel):
    period: PeriodStats
    today: TodayStats
    chart: List[ChartDataPoint]