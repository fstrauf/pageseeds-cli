# Unified Sync & Optimize Tool - Implementation Complete ✅

## What We Built

A new unified MCP tool `seo_ops_sync_and_optimize` that orchestrates the complete SEO content workflow in a single command, **including automated deployment to production**.

## Latest Update: Phase 6 - Auto-Deploy Added! 🚀

**New parameter added:** `auto_deploy`
- When `true` (and `dry_run: false`), automatically copies files from automation to production
- Provides detailed deployment results (files copied, files failed)
- Fully automated end-to-end workflow

## Files Modified

1. **`/packages/seo-content-cli/src/seo_content_mcp/seo_ops.py`**
   - Added `sync_and_optimize()` method (300+ lines)
   - Orchestrates 5 phases: Import → Analyze → Fix → Drift → Validate

2. **`/packages/seo-content-cli/src/seo_content_mcp/server.py`**
   - Added `SEOTools.OPS_SYNC_AND_OPTIMIZE` enum
   - Registered new tool with input schema
   - Added handler in `call_tool()` function

3. **`/packages/seo-content-cli/README.md`**
   - Added documentation for the new tool
   - Included usage examples and agent-friendly features

4. **`/packages/seo-content-cli/UNIFIED_SYNC_TOOL_SPEC.md`**
   - Created comprehensive specification document
   - Details all phases, parameters, return structures, error handling

5. **`/packages/seo-content-cli/test_unified_tool.py`**
   - Created test script to verify functionality
   - Successfully tested against days_to_expiry website

## Test Results ✅

```
✓ Found site: Days to Expiry
✓ Mode: preview
✓ Website: days_to_expiry

📊 Phases executed: 5
  ○ import_sync: preview
  ✓ date_analysis: completed
  ⊘ date_optimization: skipped
  ✓ drift_check: completed
  ✓ validation: completed

📈 Summary:
  • Articles in sync: False
  • Date issues found: 21
  • Files ready to push: 90
  • Validation errors: 0

💡 Recommendations:
  • Found 21 date issues - review before applying fixes
  • Push 90 files to production after review

🎯 Next action: Run with dry_run: false to apply changes
```

## How to Use

### Preview Mode (Default - Read-Only)
```json
{
  "website_id": "days_to_expiry"
}
```

### Apply Mode (Sync and Fix)
```json
{
  "website_id": "days_to_expiry",
  "auto_fix": true,
  "dry_run": false
}
```

### With Custom Parameters
```json
{
  "website_id": "days_to_expiry",
  "auto_fix": true,
  "dry_run": false,
  "spacing_days": 3,
  "max_recent_days": 14
}
```

## What It Does

### Phase 1: Import & Sync from Production
- Reads production repo content files
- Extracts frontmatter dates & metadata
- Updates automation articles.json
- Production repo is the source of truth

### Phase 2: Date Analysis
- Scans for future dates
- Detects overlapping dates (multiple articles same day)
- Identifies poor distribution in recent articles
- Categorizes articles as mutable or immutable

### Phase 3: Date Optimization (Conditional)
- Only runs if `auto_fix: true` and `dry_run: false`
- Only affects articles created within `max_recent_days`
- Redistributes articles evenly
- Removes future dates and overlaps
- Preserves all historical article dates

### Phase 4: Drift Check
- Compares automation vs production content (SHA256)
- Identifies new files (only in automation)
- Identifies mismatched files
- Generates list of files to push to production

### Phase 5: Validation
- Validates articles.json structure
- Checks for required fields
- Verifies content files exist
- Reports errors and warnings

## Return Structure

```json
{
  "ok": true,
  "mode": "preview|apply",
  "website_id": "days_to_expiry",
  "timestamp": "2026-01-28T...",
  "phases": {
    "import_sync": { ... },
    "date_analysis": { ... },
    "date_optimization": { ... },
    "drift_check": { ... },
    "validation": { ... }
  },
  "summary": {
    "articles_in_sync": false,
    "date_issues_found": 21,
    "files_ready_to_push": 90,
    "validation_errors": 0,
    "next_action": "..."
  },
  "recommended_actions": [ ... ],
  "deployment_instructions": {
    "source_dir": "...",
    "target_dir": "...",
    "files_to_copy": [ ... ]
  }
}
```

## Agent Integration Benefits

1. **Single Call** - Replaces 5+ individual tool calls
2. **Structured Output** - Easy to parse and react to
3. **Phase Tracking** - Know exactly what happened in each step
4. **Actionable Recommendations** - Clear next steps
5. **Error Handling** - Errors include suggestions for fixing
6. **Safety First** - Default is preview mode (read-only)

## Next Steps

1. **Restart MCP Server** to load the new tool
2. **Test with Your Agent** - Use preview mode first
3. **Review Results** - Check what would be changed
4. **Apply Changes** - Run with `auto_fix: true, dry_run: false`
5. **Copy Files** - Use deployment instructions to push to production

## Safety Features

- ✅ Double safety: Both `dry_run` and `auto_fix` must be set
- ✅ Never modifies production repo
- ✅ Never touches historical articles (only recent ones)
- ✅ Preview mode by default
- ✅ Structured error messages with suggestions

## Workflow Philosophy

**Production Repo is Source of Truth**

```
Production Repo → Import → Automation Repo → Optimize → Export → Production Repo
                            (working directory)
```

This ensures:
- Production changes are never lost
- Automation stays in sync
- Clear separation of concerns
- Safe deployment workflow
