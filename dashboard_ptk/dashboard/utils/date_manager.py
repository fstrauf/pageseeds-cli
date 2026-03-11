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
        
        Finds first available slot (2-day gaps) that's not already taken.
        
        Args:
            raise_on_error: If True, raise DateAllocationError on failure
        
        Returns:
            datetime: Next available date
        
        Raises:
            DateAllocationError: If no available date found and raise_on_error=True
        """
        today = datetime.now()
        existing_dates = self.get_all_dates(include_drafts=True)
        
        if not existing_dates:
            return today
        
        # Get latest date
        latest_date = max(existing_dates)
        latest_datetime = datetime.combine(latest_date, datetime.min.time())
        
        # Start from latest + 2 days
        candidate = latest_datetime + timedelta(days=2)
        
        # Find first available slot
        max_attempts = 50
        attempts = 0
        
        while attempts < max_attempts:
            if candidate.date() not in existing_dates:
                return candidate
            candidate = candidate + timedelta(days=2)
            attempts += 1
        
        # Fallback: try to find a gap in the past
        gap = self._find_gap_in_past(existing_dates)
        if gap:
            return gap
        
        if raise_on_error:
            raise DateAllocationError(
                f"No available date in next {max_attempts * 2} days and no gaps in past"
            )
        
        return today
    
    def _find_gap_in_past(self, existing_dates: set) -> Optional[datetime]:
        """Find a gap between existing dates where we can insert."""
        if not existing_dates:
            return None
        
        today = datetime.now().date()
        sorted_dates = sorted(existing_dates)
        
        # Look for gaps (iterate backwards - most recent first)
        for i in range(len(sorted_dates) - 1, 0, -1):
            curr_date = sorted_dates[i]
            prev_date = sorted_dates[i - 1]
            
            # Only gaps before today
            if curr_date >= today:
                continue
            
            # Check for 4+ day gap (room for new article)
            gap_days = (curr_date - prev_date).days
            if gap_days >= 4:
                insert_date = prev_date + timedelta(days=2)
                if insert_date < curr_date and insert_date <= today:
                    if insert_date not in existing_dates:
                        return datetime.combine(insert_date, datetime.min.time())
        
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
