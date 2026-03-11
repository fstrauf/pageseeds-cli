"""Reddit API operations for automation-mcp"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# Load .env file if present
try:
    from dotenv import load_dotenv
    # Try to load from various locations
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parents[4] / ".env",  # automation repo root
        Path.home() / ".config" / "automation" / "secrets.env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    pass


# Reddit OAuth credentials
# For read-only search: no credentials needed (uses redditwarp)
# For authenticated posting: set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars
# Get your own credentials at: https://www.reddit.com/prefs/apps
CLIENT_ID = os.environ.get('REDDIT_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET', '')
USER_AGENT = 'PageSeeds/1.0'



@dataclass
class Post:
    id: str
    title: str
    author: str
    score: int
    subreddit: str
    url: str
    created_at: str
    comment_count: int
    content: Optional[str] = None
    
    def model_dump(self):
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "score": self.score,
            "subreddit": self.subreddit,
            "url": self.url,
            "created_at": self.created_at,
            "comment_count": self.comment_count,
            "content": self.content
        }


@dataclass
class Comment:
    id: str
    author: str
    body: str
    score: int
    replies: List['Comment']
    
    def model_dump(self):
        return {
            "id": self.id,
            "author": self.author,
            "body": self.body,
            "score": self.score,
            "replies": [r.model_dump() for r in self.replies]
        }


@dataclass
class PostDetail:
    post: Post
    comments: List[Comment]
    
    def model_dump(self):
        return {
            "post": self.post.model_dump(),
            "comments": [c.model_dump() for c in self.comments]
        }


class RedditAPI:
    """Reddit API wrapper - supports both anonymous (read) and authenticated (post) access"""
    
    def __init__(self):
        # Import redditwarp here to avoid hard dependency
        try:
            import redditwarp.SYNC
            self.client = redditwarp.SYNC.Client()
        except ImportError:
            self.client = None
        
        # PRAW client for authenticated posting (if refresh token available)
        self.praw_client = None
        self.auth_error: str | None = None
        self._init_praw()
    
    def _init_praw(self):
        """Initialize PRAW client if refresh token is available."""
        refresh_token = os.environ.get('REDDIT_REFRESH_TOKEN')
        if not refresh_token:
            self.auth_error = "Missing REDDIT_REFRESH_TOKEN environment variable."
            return
        
        try:
            import praw
            self.praw_client = praw.Reddit(
                client_id=CLIENT_ID or 'placeholder',
                client_secret=CLIENT_SECRET or 'placeholder',
                user_agent=USER_AGENT,
                refresh_token=refresh_token
            )
            # Verify authentication works
            user = self.praw_client.user.me()
            if user is None:
                self.praw_client = None
                self.auth_error = "Reddit OAuth authentication failed: user lookup returned no account."
                return
            self.auth_error = None
        except Exception as e:
            self.praw_client = None
            self.auth_error = f"Reddit OAuth authentication failed: {e}"
    
    def is_authenticated(self) -> bool:
        """Check if we have authenticated posting capability."""
        return self.praw_client is not None

    def auth_status(self) -> dict:
        """Return authentication diagnostics for posting workflows."""
        status = {
            "success": True,
            "authenticated": self.is_authenticated(),
            "error": self.auth_error,
        }
        if self.praw_client:
            try:
                me = self.praw_client.user.me()
                status["username"] = str(me) if me else None
            except Exception as e:
                status["username"] = None
                status["error"] = f"Authenticated client check failed: {e}"
                status["authenticated"] = False
        return status
    
    def search_submissions(self, query: str, subreddit: str = "", limit: int = 10, 
                          sort: str = "relevance", time: str = "all") -> List[Post]:
        """Search for submissions/posts"""
        if not self.client:
            return []
        
        posts = []
        try:
            for submission in self.client.p.submission.search(subreddit, query, limit, sort=sort, time=time):
                posts.append(self._build_post(submission))
        except Exception as e:
            print(f"Error searching submissions: {e}")
        
        return posts
    
    def get_post_content(
        self,
        post_id: str,
        comment_limit: int = 10,
        comment_depth: int = 3,
        comment_sort: str = "top",
    ) -> Optional[PostDetail]:
        """Get detailed content of a specific post including comments"""
        if not self.client:
            return None
        
        try:
            submission = self.client.p.submission.fetch(post_id)
            post = self._build_post(submission)
            comments = self.get_post_comments(post_id, comment_limit, comment_depth, sort=comment_sort)
            return PostDetail(post=post, comments=comments)
        except Exception as e:
            print(f"Error getting post content: {e}")
            return None
    
    def get_post_comments(self, post_id: str, limit: int = 10, depth: int = 3, sort: str = "top") -> List[Comment]:
        """Get comments from a post"""
        if not self.client:
            return []
        
        comments = []
        try:
            tree_node = self.client.p.comment_tree.fetch(post_id, sort=sort, limit=limit)
            for node in tree_node.children:
                comment = self._build_comment_tree(node, depth)
                if comment:
                    comments.append(comment)
        except Exception as e:
            print(f"Error getting comments: {e}")
        
        return comments
    
    def _build_post(self, submission) -> Post:
        """Build Post object from submission"""
        content = None
        if hasattr(submission, 'body'):
            content = submission.body
        elif hasattr(submission, 'permalink'):
            content = submission.permalink
        
        return Post(
            id=getattr(submission, 'id36', getattr(submission, 'id', '')),
            title=getattr(submission, 'title', ''),
            author=getattr(submission, 'author_display_name', '[deleted]') or '[deleted]',
            score=getattr(submission, 'score', 0),
            subreddit=getattr(submission.subreddit, 'name', '') if hasattr(submission, 'subreddit') else '',
            url=getattr(submission, 'permalink', ''),
            created_at=getattr(submission, 'created_at', '').isoformat() if hasattr(submission, 'created_at') and hasattr(submission.created_at, 'isoformat') else str(getattr(submission, 'created_at', '')),
            comment_count=getattr(submission, 'comment_count', 0),
            content=content
        )
    
    def _build_comment_tree(self, node, depth: int = 3) -> Optional[Comment]:
        """Recursively build comment tree"""
        if depth <= 0 or not node or not hasattr(node, 'value'):
            return None
        
        comment = node.value
        replies = []
        
        if hasattr(node, 'children'):
            for child in node.children:
                child_comment = self._build_comment_tree(child, depth - 1)
                if child_comment:
                    replies.append(child_comment)
        
        return Comment(
            id=getattr(comment, 'id36', getattr(comment, 'id', '')),
            author=getattr(comment, 'author_display_name', '[deleted]') or '[deleted]',
            body=getattr(comment, 'body', ''),
            score=getattr(comment, 'score', 0),
            replies=replies
        )
    
    def submit_comment(self, post_id: str, text: str) -> dict:
        """Submit a comment/reply to a post.
        
        Args:
            post_id: The Reddit post ID (e.g., '1abc123')
            text: The comment text
            
        Returns:
            dict with success status and comment info
        """
        # Check if we have authenticated access via PRAW
        if not self.praw_client:
            return {
                "success": False, 
                "error": "Not authenticated. Set REDDIT_REFRESH_TOKEN environment variable."
            }
        
        import sys
        print(f"DEBUG: Posting to post_id={post_id}", flush=True, file=sys.stderr)
        print(f"DEBUG: Text length={len(text)}", flush=True, file=sys.stderr)
        
        try:
            # Use PRAW for authenticated posting
            submission = self.praw_client.submission(id=post_id)
            print(f"DEBUG: Fetched submission: {submission.title[:50]}...", flush=True, file=sys.stderr)
            print(f"DEBUG: Subreddit: {submission.subreddit.display_name}", flush=True, file=sys.stderr)
            print(f"DEBUG: Locked: {getattr(submission, 'locked', 'N/A')}", flush=True, file=sys.stderr)
            print(f"DEBUG: Archived: {getattr(submission, 'archived', 'N/A')}", flush=True, file=sys.stderr)
            print(f"DEBUG: Allow comments: {getattr(submission, 'allow_comments', 'N/A')}", flush=True, file=sys.stderr)
            
            # Check if post is too old (older than 6 months = archived)
            from datetime import datetime, timezone
            created_utc = getattr(submission, 'created_utc', None)
            if created_utc:
                age_days = (datetime.now(timezone.utc).timestamp() - created_utc) / 86400
                print(f"DEBUG: Post age: {age_days:.1f} days", flush=True, file=sys.stderr)
                if age_days > 180:
                    return {"success": False, "error": "Post is archived (>6 months old)"}
            
            # Submit reply
            comment = submission.reply(text)
            
            result = {
                "success": True,
                "comment_id": comment.id,
                "permalink": comment.permalink,
                "body": comment.body[:200]
            }
            print(f"DEBUG: Success: {result}", flush=True, file=sys.stderr)
            return result
        except Exception as e:
            error_msg = str(e)
            print(f"DEBUG: Error type: {type(e).__name__}", flush=True, file=sys.stderr)
            print(f"DEBUG: Error: {error_msg}", flush=True, file=sys.stderr)
            
            # Check for specific error types
            if "403" in error_msg:
                return {"success": False, "error": "Forbidden - post may be locked or subreddit requires higher karma/account age"}
            elif "404" in error_msg:
                return {"success": False, "error": "Post not found"}
            elif "429" in error_msg:
                return {"success": False, "error": "Rate limited - please wait before posting again"}
            elif "500" in error_msg:
                return {"success": False, "error": "Reddit server error (500) - post may be locked or subreddit restricted"}
            
            import traceback
            traceback.print_exc()
            return {"success": False, "error": error_msg}
