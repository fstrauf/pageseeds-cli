"""
Date management for article scheduling.

Handles date allocation, collision detection, and gap filling.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from rich.console import Console

from .errors import (
    ArticlesJsonError,
    DateAllocationError,
)

console = Console()


class DateManager:
    """Manages article dates and scheduling."""
    
    def __init__(self, articles_json_path: Path):
        self.articles_json_path = articles_json_path
    
    def get_all_dates(self, include_drafts: bool = True) -> set:
        """Get all existing article dates as a set of date objects."""
        dates = set()
        
        try:
            data = json.loads(self.articles_json_path.read_text())
            articles = data.get("articles", [])
            
            for article in articles:
                status = article.get("status")
                if status not in ["published", "draft"]:
                    continue
                if status == "draft" and not include_drafts:
                    continue
                
                date_str = article.get("published_date")
                if date_str:
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        dates.add(dt.date())
                    except ValueError:
                        pass
        except json.JSONDecodeError:
            pass  # Return empty set
        except Exception:
            pass
        
        return dates
    
    def get_latest_date(self, include_drafts: bool = True) -> tuple[Optional[datetime], list]:
        """Get the most recent article date."""
        try:
            data = json.loads(self.articles_json_path.read_text())
            articles = data.get("articles", [])
            
            dated_articles = []
            for article in articles:
                status = article.get("status")
                if status not in ["published", "draft"]:
                    continue
                if status == "draft" and not include_drafts:
                    continue
                    
                date_str = article.get("published_date")
                if date_str:
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        dated_articles.append({**article, "_parsed_date": dt})
                    except ValueError:
                        pass
            
            if dated_articles:
                dated_articles.sort(key=lambda x: x["_parsed_date"], reverse=True)
                return dated_articles[0]["_parsed_date"], dated_articles[:5]
        except json.JSONDecodeError:
            pass
        except Exception:
            pass
        
        return None, []
    
    def is_date_available(self, date_str: str) -> bool:
        """Check if a specific date is available (not already taken)."""
        try:
            proposed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            existing_dates = self.get_all_dates(include_drafts=True)
            return proposed_date not in existing_dates
        except ValueError:
            return False
    
    def get_next_available_date(self, raise_on_error: bool = False) -> datetime:
        """
        Get the next available date for scheduling.
        
        STRATEGY: Always prefer dates in the past over future dates.
        This ensures content appears as "backdated" rather than "scheduled future".
        
        1. First, look for gaps in the past (between existing articles)
        2. Only if no past gaps exist, look at future dates
        
        Args:
            raise_on_error: If True, raise DateAllocationError on failure
        
        Returns:
            datetime: Next available date (preferably in the past)
        
        Raises:
            DateAllocationError: If no available date found and raise_on_error=True
        """
        today = datetime.now()
        today_date = today.date()
        existing_dates = self.get_all_dates(include_drafts=True)
        
        if not existing_dates:
            return today
        
        # STEP 1: Look for gaps in the past FIRST (preferred)
        gap_in_past = self._find_gap_in_past(existing_dates)
        if gap_in_past:
            return gap_in_past
        
        # STEP 2: If latest date is already in the future, continue from there
        latest_date = max(existing_dates)
        if latest_date > today_date:
            latest_datetime = datetime.combine(latest_date, datetime.min.time())
            candidate = latest_datetime + timedelta(days=2)
            
            # Find first available slot in the future
            max_attempts = 50
            attempts = 0
            
            while attempts < max_attempts:
                if candidate.date() not in existing_dates:
                    return candidate
                candidate = candidate + timedelta(days=2)
                attempts += 1
        
        # STEP 3: Latest date is in the past, but no gaps found
        # This means articles are densely packed. Add to the end (future).
        latest_datetime = datetime.combine(latest_date, datetime.min.time())
        candidate = latest_datetime + timedelta(days=2)
        
        # But warn that we're creating a future date
        console.print(f"[dim]Note: No gaps in past {len(existing_dates)} articles. Using future date.[/dim]")
        
        while candidate.date() in existing_dates:
            candidate = candidate + timedelta(days=2)
        
        return candidate
    
    def _find_gap_in_past(self, existing_dates: set) -> Optional[datetime]:
        """
        Find a gap between existing dates where we can insert.
        
        Looks for 2+ day gaps (minimum spacing) and returns the first available
        slot in the most recent gap. Prefers gaps closer to today.
        """
        if not existing_dates:
            return None
        
        today = datetime.now().date()
        sorted_dates = sorted(existing_dates)
        
        # Look for gaps (iterate backwards - most recent gaps first)
        for i in range(len(sorted_dates) - 1, 0, -1):
            curr_date = sorted_dates[i]
            prev_date = sorted_dates[i - 1]
            
            # Only consider gaps that end before today (past only)
            if curr_date > today:
                continue
            
            # Check for 2+ day gap (minimum spacing for new article)
            gap_days = (curr_date - prev_date).days
            if gap_days >= 2:
                # Try to insert at prev_date + 2 days
                insert_date = prev_date + timedelta(days=2)
                
                # Must be: after prev_date, before or at curr_date, and not taken
                if prev_date < insert_date <= curr_date and insert_date not in existing_dates:
                    return datetime.combine(insert_date, datetime.min.time())
                
                # If that slot is taken, try to find another slot in this gap
                test_date = insert_date + timedelta(days=1)
                while test_date < curr_date and test_date <= today:
                    if test_date not in existing_dates:
                        return datetime.combine(test_date, datetime.min.time())
                    test_date += timedelta(days=1)
        
        return None
    
    def get_available_slots(self, count: int = 4) -> list[str]:
        """Get the next N available date slots."""
        slots = []
        existing_dates = self.get_all_dates(include_drafts=True)
        
        # Start from latest or today
        if existing_dates:
            latest = max(existing_dates)
            candidate = datetime.combine(latest, datetime.min.time()) + timedelta(days=2)
        else:
            candidate = datetime.now()
        
        while len(slots) < count:
            if candidate.date() not in existing_dates:
                slots.append(candidate.strftime("%Y-%m-%d"))
            candidate = candidate + timedelta(days=2)
        
        return slots
