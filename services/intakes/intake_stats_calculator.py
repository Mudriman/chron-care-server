# services/intake_stats_calculator.py
from datetime import date, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict

from app.db.models import MedicationIntake, Medication



class IntakeStatsCalculator:
    def __init__(self):
        self.intakes_by_date = defaultdict(list)
        self.taken_by_date = defaultdict(int)
        self.daily_scheduled = defaultdict(int)

    def process_intakes(self, intakes: List[MedicationIntake]) -> None:

        for intake in intakes:
            date_str = intake.intake_date.isoformat()
            self.intakes_by_date[date_str].append(intake)
            if intake.taken:
                self.taken_by_date[date_str] += 1

    def calculate_scheduled_intakes(self, medications: List[Medication],
                                    cutoff_date: date, today: date) -> Tuple[int, Dict]:

        total_scheduled = 0
        daily_scheduled = {}

        for medication in medications:
            med_start = max(medication.start_date, cutoff_date)
            med_end = medication.end_date or today
            med_end = min(med_end, today)

            if med_start <= med_end:
                days_count = (med_end - med_start).days + 1
                total_scheduled += days_count * medication.frequency_per_day

                current = med_start
                while current <= med_end:
                    date_str = current.isoformat()
                    daily_scheduled[date_str] = daily_scheduled.get(date_str, 0) + medication.frequency_per_day
                    current += timedelta(days=1)

        return total_scheduled, daily_scheduled

    def calculate_streaks(self, daily_scheduled: Dict[str, int],
                          taken_by_date: Dict[str, int],
                          today: date, days: int) -> Tuple[int, int]:
        current_streak = 0
        best_streak = 0
        streak = 0

        check_date = today
        for i in range(days):
            date_str = check_date.isoformat()
            scheduled = daily_scheduled.get(date_str, 0)
            taken = taken_by_date.get(date_str, 0)

            if scheduled > 0 and taken >= scheduled:
                streak += 1
                if i == 0:
                    current_streak = streak
            else:
                best_streak = max(best_streak, streak)
                streak = 0

            check_date -= timedelta(days=1)

        best_streak = max(best_streak, streak)
        return current_streak, best_streak

    def prepare_chart_data(self, daily_scheduled: Dict) -> List:
        chart_data = []
        for date_str in sorted(self.intakes_by_date.keys()):
            taken = len(self.intakes_by_date[date_str])
            scheduled = daily_scheduled.get(date_str, 0)
            if scheduled > 0:
                chart_data.append({
                    "date": date_str,
                    "taken": taken,
                    "scheduled": scheduled,
                    "adherence": round((taken / scheduled * 100), 1)
                })
        return chart_data

    def get_today_stats(self, today: date, daily_scheduled: Dict) -> Dict:
        today_str = today.isoformat()
        today_taken = self.taken_by_date.get(today_str, 0)
        today_scheduled = daily_scheduled.get(today_str, 0)

        today_progress = 0
        if today_scheduled > 0:
            today_progress = round((today_taken / today_scheduled * 100), 1)

        return {
            "taken": today_taken,
            "scheduled": today_scheduled,
            "progress": today_progress
        }