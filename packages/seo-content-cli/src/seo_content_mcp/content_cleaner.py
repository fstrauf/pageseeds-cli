"""Content cleaning utilities for SEO articles"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class CleaningIssue:
    """Represents an issue found during content cleaning"""
    file: str
    issue_type: str
    description: str
    fixed: bool = False


@dataclass
class CleaningResult:
    """Result of a content cleaning operation"""
    project_name: str
    files_checked: int
    issues_found: List[CleaningIssue]
    issues_fixed: int
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the cleaning operation"""
        return {
            "project_name": self.project_name,
            "files_checked": self.files_checked,
            "total_issues": len(self.issues_found),
            "issues_fixed": self.issues_fixed,
            "by_type": self._count_by_type()
        }
    
    def _count_by_type(self) -> Dict[str, int]:
        """Count issues by type"""
        counts = {}
        for issue in self.issues_found:
            counts[issue.issue_type] = counts.get(issue.issue_type, 0) + 1
        return counts


class ContentCleaner:
    """Clean and validate SEO content files"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
    
    def clean_website(self, website_path: str, dry_run: bool = False) -> CleaningResult:
        """
        Clean content in a website folder.
        
        Args:
            website_path: Relative path to website (e.g., "general/coffee")
            dry_run: If True, only report issues without fixing
            
        Returns:
            CleaningResult with details of what was found and fixed
        """
        full_path = os.path.join(self.workspace_root, website_path)
        articles_json_path = os.path.join(full_path, "articles.json")
        content_dir = os.path.join(full_path, "content")
        
        if not os.path.exists(articles_json_path):
            raise FileNotFoundError(f"articles.json not found at {articles_json_path}")
        
        if not os.path.isdir(content_dir):
            raise FileNotFoundError(f"content directory not found at {content_dir}")
        
        # Load articles.json
        with open(articles_json_path, 'r', encoding='utf-8') as f:
            articles_data = json.load(f)
        
        # Process all markdown files
        issues = []
        files_checked = 0

        content_files = sorted(
            list(Path(content_dir).glob("*.mdx")) + list(Path(content_dir).glob("*.md"))
        )

        for md_file in content_files:
            if md_file.name == '.gitkeep':
                continue
                
            files_checked += 1
            file_issues = self._process_markdown_file(
                md_file, 
                articles_data, 
                dry_run
            )
            issues.extend(file_issues)
        
        # Count fixed issues
        issues_fixed = sum(1 for issue in issues if issue.fixed)
        
        project_name = os.path.basename(website_path)
        
        return CleaningResult(
            project_name=project_name,
            files_checked=files_checked,
            issues_found=issues,
            issues_fixed=issues_fixed
        )
    
    def _process_markdown_file(
        self, 
        md_file: Path, 
        articles_data: Dict[str, Any],
        dry_run: bool
    ) -> List[CleaningIssue]:
        """Process a single markdown file for issues"""
        issues = []
        
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            modified = False
            
            # Extract frontmatter
            frontmatter_match = re.match(r'^---\n([\s\S]*?)\n---\n', content)
            
            if not frontmatter_match:
                issues.append(CleaningIssue(
                    file=md_file.name,
                    issue_type="missing_frontmatter",
                    description="No frontmatter found",
                    fixed=False
                ))
                return issues
            
            frontmatter = frontmatter_match.group(1)
            
            # Extract title from frontmatter
            title_match = re.search(r'^title:\s*"([^"]+)"', frontmatter, re.MULTILINE)
            
            if title_match:
                title = title_match.group(1)
                
                # Check for duplicate title heading
                escaped_title = re.escape(title)
                duplicate_pattern = re.compile(
                    f'^---\\n([\\s\\S]*?)\\n---\\n\\n# {escaped_title}\\n\\n',
                    re.MULTILINE
                )
                
                if duplicate_pattern.search(content):
                    issues.append(CleaningIssue(
                        file=md_file.name,
                        issue_type="duplicate_title",
                        description=f"Duplicate title heading: {title}",
                        fixed=not dry_run
                    ))
                    
                    if not dry_run:
                        # Remove duplicate title
                        content = duplicate_pattern.sub(r'---\n\1\n---\n\n', content)
                        modified = True
                
                # Check date synchronization with articles.json
                article = self._find_article_by_filename(articles_data, md_file.name)
                
                if article and article.get('published_date'):
                    current_date_match = re.search(
                        r'^date:\s*"([^"]+)"', 
                        frontmatter, 
                        re.MULTILINE
                    )
                    current_date = current_date_match.group(1) if current_date_match else None
                    expected_date = article['published_date']
                    
                    if current_date != expected_date:
                        issues.append(CleaningIssue(
                            file=md_file.name,
                            issue_type="date_mismatch",
                            description=f"Date mismatch: {current_date or '(missing)'} → {expected_date}",
                            fixed=not dry_run
                        ))
                        
                        if not dry_run:
                            # Update or add date field
                            old_frontmatter = frontmatter_match.group(0)
                            
                            if current_date_match:
                                # Replace existing date
                                new_frontmatter = old_frontmatter.replace(
                                    f'date: "{current_date}"',
                                    f'date: "{expected_date}"'
                                )
                            else:
                                # Add date after title
                                new_frontmatter = re.sub(
                                    r'(title:\s*"[^"]*")',
                                    f'\\1\ndate: "{expected_date}"',
                                    old_frontmatter
                                )
                            
                            content = content.replace(old_frontmatter, new_frontmatter)
                            modified = True
            
            # Write back if modified
            if modified and not dry_run:
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(content)
            
        except Exception as e:
            issues.append(CleaningIssue(
                file=md_file.name,
                issue_type="error",
                description=f"Error processing file: {str(e)}",
                fixed=False
            ))
        
        return issues
    
    def _find_article_by_filename(
        self, 
        articles_data: Dict[str, Any], 
        filename: str
    ) -> Optional[Dict[str, Any]]:
        """Find article in articles.json by matching filename"""
        for article in articles_data.get('articles', []):
            article_file = article.get('file', '')
            # article_file is like "./content/01_article.md"
            if article_file.endswith(filename):
                return article
        return None


def format_cleaning_result(result: CleaningResult) -> str:
    """Format cleaning result as readable text"""
    lines = [
        f"🧹 Content Cleaning Report: {result.project_name}",
        "=" * 60,
        "",
        f"  Files checked: {result.files_checked}",
        f"  Issues found: {len(result.issues_found)}",
        f"  Issues fixed: {result.issues_fixed}",
        ""
    ]
    
    if not result.issues_found:
        lines.extend([
            "✅ No issues found! Content is clean.",
            ""
        ])
        return "\n".join(lines)
    
    # Group by type
    by_type = {}
    for issue in result.issues_found:
        if issue.issue_type not in by_type:
            by_type[issue.issue_type] = []
        by_type[issue.issue_type].append(issue)
    
    # Display by type
    type_labels = {
        "duplicate_title": "📋 Duplicate Title Headings",
        "date_mismatch": "📅 Date Mismatches",
        "missing_frontmatter": "⚠️  Missing Frontmatter",
        "error": "❌ Errors"
    }
    
    for issue_type, type_issues in by_type.items():
        label = type_labels.get(issue_type, issue_type)
        lines.append(f"  {label} ({len(type_issues)}):")
        
        for issue in type_issues[:5]:  # Show first 5
            status = "✓" if issue.fixed else "·"
            lines.append(f"    {status} {issue.file}")
            lines.append(f"      {issue.description}")
        
        if len(type_issues) > 5:
            lines.append(f"    ... and {len(type_issues) - 5} more")
        
        lines.append("")
    
    # Summary
    if result.issues_fixed > 0:
        lines.append(f"✅ Fixed {result.issues_fixed} issue(s)")
    
    return "\n".join(lines)
