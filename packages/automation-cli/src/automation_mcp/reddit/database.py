"""Reddit database operations for automation-mcp"""

import json
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[4]
DATABASE_PATH = REPO_ROOT / "tools" / ".data" / "client_ops.db"


def get_db_path() -> str:
    """Get the database path"""
    db_path = DATABASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


def get_connection() -> sqlite3.Connection:
    """Get database connection"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def validate_reply_text(reply_text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate reply text for Reddit posting.
    
    Returns: (is_valid, error_message)
    """
    if reply_text is None:
        return True, None
    
    reply_text = reply_text.strip()
    
    # Check length
    if not reply_text or len(reply_text) < 10:
        return False, "Reply is too short. Minimum 10 characters."
    
    # Check for URLs
    if "http://" in reply_text or "https://" in reply_text:
        pos = reply_text.find("http")
        return False, f"Reply contains a URL at position {pos}. Please remove all links."
    
    # Check for markdown links
    if re.search(r'\[.+?\]\(.+?\)', reply_text):
        return False, "Reply contains a markdown link. Please remove all links and use plain text."
    
    # Check sentence count
    sentences = re.split(r'[.!?]+', reply_text)
    sentence_count = len([s for s in sentences if s.strip()])
    
    if sentence_count < 3:
        return False, f"Reply has {sentence_count} sentences. Minimum 3 sentences required."
    
    if sentence_count > 5:
        return False, f"Reply has {sentence_count} sentences. Maximum 5 sentences allowed."
    
    # Check word count
    word_count = len(reply_text.split())
    if word_count < 30:
        return False, f"Reply has {word_count} words. Minimum 30 words recommended."
    
    if word_count > 250:
        return False, f"Reply has {word_count} words. Maximum 250 words recommended."
    
    return True, None


def ensure_reddit_table():
    """Ensure reddit_opportunity table exists"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reddit_opportunity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            post_id TEXT UNIQUE NOT NULL,
            title TEXT,
            url TEXT,
            subreddit TEXT,
            author TEXT,
            posted_date TEXT,
            upvotes INTEGER,
            comment_count INTEGER,
            days_old INTEGER,
            relevance_score REAL,
            engagement_score REAL,
            accessibility_score REAL,
            final_score REAL,
            severity TEXT,
            why_relevant TEXT,
            key_pain_points TEXT,
            website_fit TEXT,
            reply_status TEXT DEFAULT 'pending',
            reply_text TEXT,
            reply_url TEXT,
            posted_at TEXT,
            reply_upvotes INTEGER,
            reply_replies INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


def insert_reddit_opportunity(**kwargs) -> Dict[str, Any]:
    """Insert a Reddit opportunity into the database"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Convert list to JSON
    if 'key_pain_points' in kwargs and isinstance(kwargs['key_pain_points'], list):
        kwargs['key_pain_points'] = json.dumps(kwargs['key_pain_points'])
    
    # Set timestamps
    now = datetime.now().isoformat()
    kwargs['created_at'] = now
    kwargs['updated_at'] = now
    kwargs['reply_status'] = 'pending'
    
    # Check if post already exists
    cursor.execute("SELECT id FROM reddit_opportunity WHERE post_id = ?", (kwargs.get('post_id'),))
    existing = cursor.fetchone()
    
    if existing:
        # Update existing
        update_fields = {k: v for k, v in kwargs.items() if k not in ['id', 'created_at']}
        set_clause = ', '.join([f"{k} = ?" for k in update_fields.keys()])
        values = list(update_fields.values()) + [kwargs.get('post_id')]
        
        cursor.execute(f"UPDATE reddit_opportunity SET {set_clause} WHERE post_id = ?", values)
        conn.commit()
        conn.close()
        return {"success": True, "action": "updated", "post_id": kwargs.get('post_id')}
    else:
        # Insert new
        fields = list(kwargs.keys())
        placeholders = ', '.join(['?' for _ in fields])
        values = [kwargs.get(f) for f in fields]
        
        cursor.execute(f"INSERT INTO reddit_opportunity ({', '.join(fields)}) VALUES ({placeholders})", values)
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return {"success": True, "action": "inserted", "id": new_id, "post_id": kwargs.get('post_id')}


def get_pending_opportunities(project_name: str, severity: str = "") -> List[Dict[str, Any]]:
    """Get pending opportunities for a project"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if severity:
        cursor.execute("""
            SELECT * FROM reddit_opportunity 
            WHERE project_name = ? AND reply_status = 'pending' AND severity = ?
            ORDER BY final_score DESC
        """, (project_name, severity))
    else:
        cursor.execute("""
            SELECT * FROM reddit_opportunity 
            WHERE project_name = ? AND reply_status = 'pending'
            ORDER BY final_score DESC
        """, (project_name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    opportunities = []
    for row in rows:
        opp = dict(row)
        # Parse JSON
        if opp.get('key_pain_points'):
            try:
                opp['key_pain_points'] = json.loads(opp['key_pain_points'])
            except:
                pass
        opportunities.append(opp)
    
    return opportunities


def get_posted_opportunities(project_name: str, days: int = 30) -> List[Dict[str, Any]]:
    """Get posted opportunities for performance tracking"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM reddit_opportunity 
        WHERE project_name = ? AND reply_status = 'posted'
        AND posted_at >= datetime('now', '-{} days')
        ORDER BY posted_at DESC
    """.format(days), (project_name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    opportunities = []
    for row in rows:
        opp = dict(row)
        if opp.get('key_pain_points'):
            try:
                opp['key_pain_points'] = json.loads(opp['key_pain_points'])
            except:
                pass
        opportunities.append(opp)
    
    return opportunities


def mark_opportunity_posted(post_id: str, reply_text: str, reply_url: str = "") -> Dict[str, Any]:
    """Mark an opportunity as posted"""
    conn = get_connection()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE reddit_opportunity 
        SET reply_status = 'posted', reply_text = ?, reply_url = ?, posted_at = ?, updated_at = ?
        WHERE post_id = ?
    """, (reply_text, reply_url, now, now, post_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "action": "marked_posted", "post_id": post_id}


def mark_opportunity_skipped(post_id: str, reason: str = "") -> Dict[str, Any]:
    """Mark an opportunity as skipped"""
    conn = get_connection()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE reddit_opportunity 
        SET reply_status = 'skipped', updated_at = ?
        WHERE post_id = ?
    """, (now, post_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "action": "marked_skipped", "post_id": post_id}


def get_reddit_statistics(project_name: str) -> Dict[str, Any]:
    """Get statistics for a project"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Count by status
    cursor.execute("""
        SELECT reply_status, COUNT(*) as count
        FROM reddit_opportunity
        WHERE project_name = ?
        GROUP BY reply_status
    """, (project_name,))
    
    status_counts = {row['reply_status']: row['count'] for row in cursor.fetchall()}
    
    # Count by severity (pending only)
    cursor.execute("""
        SELECT severity, COUNT(*) as count
        FROM reddit_opportunity
        WHERE project_name = ? AND reply_status = 'pending'
        GROUP BY severity
    """, (project_name,))
    
    severity_counts = {row['severity']: row['count'] for row in cursor.fetchall()}
    
    # Average scores
    cursor.execute("""
        SELECT AVG(final_score) as avg_score, MAX(final_score) as max_score
        FROM reddit_opportunity
        WHERE project_name = ? AND reply_status = 'pending'
    """, (project_name,))
    
    score_stats = cursor.fetchone()
    
    conn.close()
    
    return {
        "project_name": project_name,
        "total_opportunities": sum(status_counts.values()),
        "by_status": status_counts,
        "pending_by_severity": severity_counts,
        "average_score": score_stats['avg_score'] if score_stats else 0,
        "max_score": score_stats['max_score'] if score_stats else 0
    }


def update_opportunity_performance(post_id: str, reply_upvotes: int = 0, 
                                   reply_replies: int = 0) -> Dict[str, Any]:
    """Update performance metrics for a posted opportunity"""
    conn = get_connection()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE reddit_opportunity 
        SET reply_upvotes = ?, reply_replies = ?, updated_at = ?
        WHERE post_id = ?
    """, (reply_upvotes, reply_replies, now, post_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "action": "updated_performance", "post_id": post_id}
