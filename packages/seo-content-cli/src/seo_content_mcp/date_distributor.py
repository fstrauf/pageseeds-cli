"""Date distribution utilities for SEO articles"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DateIssue:
    """Represents a date-related issue"""
    article_id: int
    issue_type: str  # 'future_date', 'overlap', 'invalid_format'
    description: str
    current_date: str


@dataclass
class DateAnalysisResult:
    """Result of date analysis"""
    project_name: str
    today: datetime
    seven_days_ago: datetime
    total_articles: int
    past_articles: int
    recent_articles: int
    issues: List[DateIssue]
    overlapping_dates: List[Tuple[str, List[int]]]  # (date, [article_ids])
    recent_articles_data: List[Dict[str, Any]]
    
    def has_issues(self) -> bool:
        """Check if there are any issues"""
        return len(self.issues) > 0 or len(self.overlapping_dates) > 0


@dataclass
class DateFixResult:
    """Result of date fixing operation"""
    project_name: str
    articles_fixed: int
    changes: List[Dict[str, Any]]  # List of {article_id, old_date, new_date}
    distribution_info: Dict[str, Any]


class DateDistributor:
    """Analyze and fix article date distributions"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
    
    def analyze_dates(self, website_path: str) -> DateAnalysisResult:
        """
        Analyze article dates to find issues.
        
        Args:
            website_path: Relative path to website (e.g., "general/coffee")
            
        Returns:
            DateAnalysisResult with analysis details
        """
        full_path = os.path.join(self.workspace_root, website_path)
        articles_json_path = os.path.join(full_path, "articles.json")
        
        if not os.path.exists(articles_json_path):
            raise FileNotFoundError(f"articles.json not found at {articles_json_path}")
        
        # Load articles.json
        with open(articles_json_path, 'r', encoding='utf-8') as f:
            articles_data = json.load(f)
        
        # Analyze
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = today - timedelta(days=7)
        
        recent_articles = []
        past_articles = []
        issues = []
        
        for article in articles_data.get('articles', []):
            article_id = article.get('id')
            published_date_str = article.get('published_date', '')
            
            # Handle None or empty dates
            if not published_date_str:
                issues.append(DateIssue(
                    article_id=article_id,
                    issue_type='missing_date',
                    description="Missing published_date",
                    current_date=""
                ))
                continue
            
            try:
                published_date = datetime.strptime(published_date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                issues.append(DateIssue(
                    article_id=article_id,
                    issue_type='invalid_format',
                    description=f"Invalid date format: '{published_date_str}'",
                    current_date=str(published_date_str)
                ))
                continue
            
            # Check if date is in the future
            if published_date > today:
                issues.append(DateIssue(
                    article_id=article_id,
                    issue_type='future_date',
                    description=f"Future date: {published_date_str}",
                    current_date=published_date_str
                ))
                recent_articles.append({
                    'article': article,
                    'published_date': published_date,
                    'issue': 'future_date'
                })
            # Check if recently created (within last 7 days)
            elif published_date >= seven_days_ago:
                recent_articles.append({
                    'article': article,
                    'published_date': published_date,
                    'issue': None
                })
            else:
                past_articles.append({
                    'article': article,
                    'published_date': published_date,
                    'issue': None
                })
        
        # Detect overlapping dates
        overlapping_dates = self._detect_overlapping_dates(recent_articles)
        
        project_name = os.path.basename(website_path)
        
        return DateAnalysisResult(
            project_name=project_name,
            today=today,
            seven_days_ago=seven_days_ago,
            total_articles=len(recent_articles) + len(past_articles),
            past_articles=len(past_articles),
            recent_articles=len(recent_articles),
            issues=issues,
            overlapping_dates=overlapping_dates,
            recent_articles_data=recent_articles
        )
    
    def fix_dates(
        self, 
        website_path: str,
        dry_run: bool = False
    ) -> DateFixResult:
        """
        Fix date issues by redistributing recent articles.
        
        Args:
            website_path: Relative path to website (e.g., "general/coffee")
            dry_run: If True, only calculate fixes without saving
            
        Returns:
            DateFixResult with details of changes made
        """
        full_path = os.path.join(self.workspace_root, website_path)
        articles_json_path = os.path.join(full_path, "articles.json")
        
        # First analyze
        analysis = self.analyze_dates(website_path)
        
        if not analysis.has_issues():
            return DateFixResult(
                project_name=analysis.project_name,
                articles_fixed=0,
                changes=[],
                distribution_info={"message": "No issues found"}
            )
        
        # Load articles data for modification
        with open(articles_json_path, 'r', encoding='utf-8') as f:
            articles_data = json.load(f)
        
        # Calculate fixes
        changes = []
        
        if analysis.recent_articles > 0:
            # Get the date range for recent articles
            recent_dates = [item['published_date'] for item in analysis.recent_articles_data]
            earliest_recent = min(recent_dates)
            latest_recent = min(max(recent_dates), analysis.today)
            
            # Calculate optimal distribution
            optimal_dates = self._calculate_optimal_distribution(
                len(analysis.recent_articles_data),
                earliest_recent,
                latest_recent
            )
            
            # Sort recent articles by ID
            recent_sorted = sorted(
                analysis.recent_articles_data, 
                key=lambda x: x['article']['id']
            )
            
            # Apply changes
            for idx, item in enumerate(recent_sorted):
                article_id = item['article']['id']
                old_date = item['published_date'].strftime('%Y-%m-%d')
                new_date = optimal_dates[idx]
                new_date_str = new_date.strftime('%Y-%m-%d')
                
                if old_date != new_date_str:
                    changes.append({
                        'article_id': article_id,
                        'old_date': old_date,
                        'new_date': new_date_str
                    })
                    
                    if not dry_run:
                        # Update in articles_data
                        for article in articles_data['articles']:
                            if article['id'] == article_id:
                                article['published_date'] = new_date_str
                                break
            
            # Save if not dry run
            if changes and not dry_run:
                with open(articles_json_path, 'w', encoding='utf-8') as f:
                    json.dump(articles_data, f, indent=2, ensure_ascii=False)
            
            # Distribution info
            distribution_info = {
                'earliest_date': optimal_dates[0].strftime('%Y-%m-%d'),
                'latest_date': optimal_dates[-1].strftime('%Y-%m-%d'),
                'total_days': (optimal_dates[-1] - optimal_dates[0]).days,
                'days_per_article': max(1, (optimal_dates[-1] - optimal_dates[0]).days // max(1, len(optimal_dates) - 1)),
                'unique_dates': len(set(optimal_dates)) == len(optimal_dates)
            }
        else:
            distribution_info = {"message": "No recent articles to redistribute"}
        
        return DateFixResult(
            project_name=analysis.project_name,
            articles_fixed=len(changes),
            changes=changes,
            distribution_info=distribution_info
        )
    
    def _detect_overlapping_dates(
        self, 
        recent_articles: List[Dict[str, Any]]
    ) -> List[Tuple[str, List[int]]]:
        """Detect overlapping dates in recent articles"""
        date_to_articles = {}
        
        for item in recent_articles:
            date_str = item['published_date'].strftime('%Y-%m-%d')
            article_id = item['article']['id']
            
            if date_str not in date_to_articles:
                date_to_articles[date_str] = []
            date_to_articles[date_str].append(article_id)
        
        # Return only dates with multiple articles
        overlaps = [
            (date, article_ids) 
            for date, article_ids in date_to_articles.items() 
            if len(article_ids) > 1
        ]
        
        return sorted(overlaps)
    
    def _calculate_optimal_distribution(
        self,
        count: int,
        earliest_date: datetime,
        latest_date: datetime
    ) -> List[datetime]:
        """
        Calculate optimal date distribution.
        Ensures even spacing and no overlaps.
        """
        if count <= 1:
            return [latest_date] if count == 1 else []
        
        time_span = (latest_date - earliest_date).days
        
        # Minimum spacing: 2 days per article
        min_spacing_days = 2
        required_days = count * min_spacing_days
        
        # If we don't have enough days, extend backwards
        if time_span < required_days:
            earliest_date = latest_date - timedelta(days=required_days)
            time_span = required_days
        
        # Calculate days per article
        days_per_article = max(
            min_spacing_days, 
            time_span // (count - 1) if count > 1 else time_span
        )
        
        # Generate dates
        optimal_dates = []
        for i in range(count):
            offset_days = i * days_per_article
            new_date = earliest_date + timedelta(days=offset_days)
            optimal_dates.append(new_date)
        
        # Cap at latest_date
        optimal_dates = [min(date, latest_date) for date in optimal_dates]
        
        # Ensure no duplicates
        seen_dates = set()
        final_dates = []
        for date in optimal_dates:
            while date in seen_dates and date <= latest_date:
                date = date + timedelta(days=1)
            seen_dates.add(date)
            final_dates.append(date)
        
        return final_dates


def format_date_analysis(result: DateAnalysisResult) -> str:
    """Format date analysis result as readable text"""
    lines = [
        f"📅 Date Analysis: {result.project_name}",
        "=" * 60,
        "",
        f"  Today: {result.today.strftime('%Y-%m-%d')}",
        f"  Recent threshold: {result.seven_days_ago.strftime('%Y-%m-%d')} (last 7 days)",
        "",
        "📈 Statistics:",
        f"  • Total articles: {result.total_articles}",
        f"  • Published (past): {result.past_articles}",
        f"  • Recent (last 7 days): {result.recent_articles}",
        ""
    ]
    
    if not result.has_issues():
        lines.extend([
            "✅ No issues detected!",
            "   All dates are valid and properly distributed.",
            ""
        ])
        return "\n".join(lines)
    
    # Show issues
    if result.issues:
        lines.append(f"⚠️  Date Issues ({len(result.issues)}):")
        for issue in result.issues[:10]:  # Show first 10
            lines.append(f"  • Article {issue.article_id}: {issue.description}")
        if len(result.issues) > 10:
            lines.append(f"  ... and {len(result.issues) - 10} more")
        lines.append("")
    
    # Show overlapping dates
    if result.overlapping_dates:
        lines.append(f"⚠️  Overlapping Dates ({len(result.overlapping_dates)} dates):")
        for date_str, article_ids in result.overlapping_dates[:10]:
            ids_str = ", ".join(str(id) for id in article_ids)
            lines.append(f"  • {date_str}: Articles {ids_str}")
        if len(result.overlapping_dates) > 10:
            lines.append(f"  ... and {len(result.overlapping_dates) - 10} more")
        lines.append("")
    
    # Show recent articles if any
    if result.recent_articles > 0:
        recent_dates = sorted([
            item['published_date'] 
            for item in result.recent_articles_data
        ])
        lines.extend([
            "📋 Recent Articles Date Range:",
            f"  • Earliest: {recent_dates[0].strftime('%Y-%m-%d')}",
            f"  • Latest: {recent_dates[-1].strftime('%Y-%m-%d')}",
            f"  • Span: {(recent_dates[-1] - recent_dates[0]).days} days",
            ""
        ])
    
    lines.append("💡 Use seo_fix_dates to redistribute dates and fix issues.")
    
    return "\n".join(lines)


def format_date_fix(result: DateFixResult, dry_run: bool = False) -> str:
    """Format date fix result as readable text"""
    lines = [
        f"🔧 Date Fix {'Preview' if dry_run else 'Report'}: {result.project_name}",
        "=" * 60,
        ""
    ]
    
    if result.articles_fixed == 0:
        lines.extend([
            "✅ No articles needed fixing!",
            "   All dates are already properly distributed.",
            ""
        ])
        return "\n".join(lines)
    
    # Show distribution info
    if 'message' not in result.distribution_info:
        info = result.distribution_info
        lines.extend([
            "📊 New Distribution:",
            f"  • Date range: {info['earliest_date']} → {info['latest_date']}",
            f"  • Total span: {info['total_days']} days",
            f"  • Days per article: ~{info['days_per_article']} days",
            f"  • Unique dates: {'Yes ✓' if info['unique_dates'] else 'No (some overlap)'}",
            ""
        ])
    
    # Show changes
    lines.append(f"📝 Changes {'(Preview - not saved)' if dry_run else '(Applied)'}:")
    lines.append(f"  Articles affected: {result.articles_fixed}")
    lines.append("")
    
    for change in result.changes[:10]:  # Show first 10
        status = "→" if dry_run else "✓"
        lines.append(
            f"  {status} Article {change['article_id']}: "
            f"{change['old_date']} → {change['new_date']}"
        )
    
    if len(result.changes) > 10:
        lines.append(f"  ... and {len(result.changes) - 10} more changes")
    
    lines.append("")
    
    if dry_run:
        lines.append("💡 Run seo_fix_dates without dry_run to apply these changes.")
    else:
        lines.append(f"✅ Successfully updated {result.articles_fixed} article(s)!")
    
    return "\n".join(lines)
