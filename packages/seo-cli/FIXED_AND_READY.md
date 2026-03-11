# SEO MCP Server - Fixed and Ready for Production

## What Was Fixed

The SEO MCP server had an issue where Python's `requests` library would hang when called from within the MCP server context. This has been fixed by replacing all `requests` calls with `curl` subprocess calls.

## Changes Made

1. **Added `_capsolver_curl()` helper function** - Uses subprocess to call curl instead of requests library
2. **Updated `get_capsolver_token()`** - Now uses curl subprocess for all API calls
3. **Added timeout protection** - 60-second timeout on CAPTCHA solving with proper polling
4. **Batch processing tool already exists** - `batch_keyword_difficulty()` tool processes multiple keywords

## Available MCP Tools

### 1. `keyword_difficulty(keyword: str, country: str = "us")`
Get keyword difficulty for a single keyword.

**Returns:** Difficulty score (0-100), SERP data, and ranking pages

**Time:** ~10-15 seconds per keyword

### 2. `batch_keyword_difficulty(keywords: List[str], country: str = "us")`
Process multiple keywords in batch.

**Args:**
- `keywords`: List of keywords to analyze (recommend 10-50 at a time)
- `country`: Country code (default: "us")

**Returns:**
```json
{
  "total": 41,
  "successful": 39,
  "failed": 2,
  "results": [
    {"keyword": "options wheel strategy", "difficulty": 4, "serp_count": 10},
    ...
  ],
  "failed_keywords": [...],
  "summary": {
    "avg_difficulty": 23.5,
    "min_difficulty": 0,
    "max_difficulty": 67,
    "distribution": {
      "very_easy": 15,
      "easy": 12,
      "medium": 8,
      "hard": 3,
      "very_hard": 1
    }
  }
}
```

**Time:** ~15 seconds per keyword

### 3. `keyword_generator(keyword: str, country: str = "us")`
Find related keywords and variations.

**Returns:** List of keyword ideas (regular + question-based)

## How to Use in SEO Workflow

### From VS Code Copilot Chat

The MCP tools are automatically available when the MCP server is running. Simply call them:

```
Use batch_keyword_difficulty to analyze these keywords:
- options wheel strategy
- covered call tracker
- portfolio analytics
```

### Example Workflow Integration

When running the SEO keyword research workflow (`1-keyword_research.md`), the workflow will:

1. Generate seed keywords based on project features
2. Use `keyword_generator()` to find variations
3. Dedupe keywords using `seo_filter_new_keywords()`
4. Use `batch_keyword_difficulty()` to analyze all candidates
5. Score and prioritize based on difficulty + relevance

## Testing the Server

Run the test script to verify everything works:

```bash
cd packages/seo-cli
uv run python test_updated_mcp.py
```

Expected output:
- ✓ CAPTCHA solving: ~8 seconds
- ✓ Single keyword: ~2-4 seconds
- ✓ Batch (3 keywords): ~28 seconds

## Performance

- **CAPTCHA solving:** 8-10 seconds
- **Keyword difficulty lookup:** 2-5 seconds
- **Total per keyword:** ~10-15 seconds
- **41 keywords:** ~10-15 minutes total

## Rate Limiting

The batch tool includes:
- 1-second delay between keywords
- Fresh CAPTCHA token for each keyword
- Proper error handling and retries

## CapSolver API

- **Balance:** $8.03 (checked 2026-01-22)
- **Cost:** ~$0.001 per CAPTCHA solve
- **Remaining:** ~8,000 keyword lookups

## Troubleshooting

If you see "The user cancelled the tool call":
- This usually means the tool is taking longer than expected
- Each keyword takes 10-15 seconds
- For large batches (40+ keywords), expect 10-15 minutes total
- VS Code may show this message but the tool is still working

## Future Use

This solution is now **production-ready and reusable**. Every time you run the SEO workflow:

1. The workflow will automatically use `batch_keyword_difficulty()`
2. It will process all candidate keywords in one call
3. Results will be scored and prioritized
4. Low-difficulty opportunities will be identified

No manual intervention needed - just run the workflow prompt!
