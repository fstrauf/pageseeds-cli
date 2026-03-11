# Unified Sync & Optimize Tool Specification

## Tool Name
`seo_ops_sync_and_optimize`

## Purpose
A unified orchestration tool that treats the production repository as the single source of truth, automatically syncing content, analyzing issues, fixing dates, and preparing files for deployment. This replaces the manual process of calling multiple tools in sequence.

## Design Philosophy
- **Production repo is always the source of truth**
- **Automation repo is the working directory**
- **One command does the entire workflow**
- **Returns structured data for agent parsing and decision-making**
- **Read-only by default, with optional auto-fix mode**

---

## Parameters

```typescript
interface SyncAndOptimizeParams {
  website_id: string;           // From WEBSITES_REGISTRY.json (e.g., "days_to_expiry")
  auto_fix?: boolean;            // Default: false (preview only)
  spacing_days?: number;         // Default: 2 (days between articles)
  max_recent_days?: number;      // Default: 7 (only fix articles created in last N days)
  dry_run?: boolean;             // Default: true (show what would happen)
}
```

### Parameter Details

- **`website_id`** (required): The website identifier from `WEBSITES_REGISTRY.json`
  - Example: `"days_to_expiry"`, `"coffee"`, `"expense"`
  
- **`auto_fix`** (optional, default: `false`): 
  - `false`: Preview mode - show what would be done without making changes
  - `true`: Apply mode - actually sync, fix dates, and update files
  
- **`spacing_days`** (optional, default: `2`): 
  - Number of days to space between redistributed articles
  - Only affects recent articles within `max_recent_days`
  
- **`max_recent_days`** (optional, default: `7`):
  - Only articles created/modified in last N days are eligible for date redistribution
  - Historical articles are never touched
  
- **`dry_run`** (optional, default: `true`):
  - Safety check that overrides `auto_fix` if true
  - Useful for testing the workflow

---

## Workflow Phases

The tool executes these phases in sequence:

### Phase 1: Import & Sync from Production
**Goal**: Pull latest dates/metadata from production repo to automation

**Actions**:
- Read production repo content files (from `source_repo_local_path` + `source_content_dir`)
- Extract frontmatter dates & metadata
- Compare with automation `articles.json`
- Update automation `articles.json` with production values
- Generate sync report

**Output**:
```json
{
  "phase": "import_sync",
  "status": "completed",
  "imported_articles": 62,
  "new_articles": 3,
  "updated_dates": 58,
  "skipped_articles": 20
}
```

### Phase 2: Date Analysis
**Goal**: Identify date issues in the now-synced automation repo

**Actions**:
- Scan all articles for date problems:
  - Future dates
  - Overlapping dates (multiple articles same day)
  - Poor distribution in recent articles
- Identify "mutable" articles (created within `max_recent_days`)
- Identify "immutable" articles (historical, untouchable)

**Output**:
```json
{
  "phase": "date_analysis",
  "status": "completed",
  "total_articles": 89,
  "mutable_articles": 8,
  "immutable_articles": 81,
  "issues": {
    "future_dates": [
      {"id": 81, "date": "2026-01-30"}
    ],
    "overlapping_dates": [
      {"date": "2026-01-24", "article_ids": [79, 87]}
    ],
    "poor_distribution": true
  }
}
```

### Phase 3: Date Optimization (Conditional)
**Goal**: Fix date issues in mutable articles only

**Conditions**:
- Only runs if `auto_fix: true` and `dry_run: false`
- Only affects articles created within `max_recent_days`
- Preserves all historical article dates

**Actions**:
- Redistribute mutable articles evenly across available date range
- Remove future dates
- Eliminate overlapping dates
- Update automation `articles.json`
- Update automation content file frontmatter

**Output**:
```json
{
  "phase": "date_optimization",
  "status": "completed",
  "articles_redistributed": 8,
  "date_range": {
    "start": "2026-01-12",
    "end": "2026-01-26",
    "span_days": 14
  },
  "changes": [
    {"id": 77, "old_date": "2026-01-18", "new_date": "2026-01-14"},
    {"id": 79, "old_date": "2026-01-24", "new_date": "2026-01-16"}
  ]
}
```

### Phase 4: Drift Check
**Goal**: Identify files that differ between automation and production

**Actions**:
- Compare SHA256 hashes of automation content vs production content
- Identify files that exist only in automation (new articles)
- Identify files with content mismatches
- Generate list of files to copy to production

**Output**:
```json
{
  "phase": "drift_check",
  "status": "completed",
  "automation_files": 90,
  "production_files": 80,
  "files_to_push": [
    "82_cash_secured_put_calculator.mdx",
    "83_options_trading_portfolio.mdx",
    "87_options_premium_tracking.mdx"
  ],
  "mismatched_files": [
    "77_0dte_strategy_radar_high_probability_intraday_playbook.mdx",
    "78_options_trading_journal.mdx"
  ]
}
```

### Phase 5: Validation
**Goal**: Ensure automation content is valid and ready for deployment

**Actions**:
- Validate `articles.json` structure
- Check content files exist
- Verify dates are properly formatted
- Check for duplicate title headings

**Output**:
```json
{
  "phase": "validation",
  "status": "completed",
  "articles_validated": 89,
  "errors": [],
  "warnings": [
    {"id": 82, "warning": "Missing estimated_traffic_monthly"}
  ]
}
```

---

## Return Structure

### Preview Mode (auto_fix: false or dry_run: true)

```json
{
  "ok": true,
  "mode": "preview",
  "website_id": "days_to_expiry",
  "timestamp": "2026-01-28T10:30:00Z",
  "phases": {
    "import_sync": { /* Phase 1 output */ },
    "date_analysis": { /* Phase 2 output */ },
    "date_optimization": {
      "phase": "date_optimization",
      "status": "skipped",
      "reason": "preview_mode",
      "would_fix": 8
    },
    "drift_check": { /* Phase 4 output */ },
    "validation": { /* Phase 5 output */ }
  },
  "summary": {
    "articles_in_sync": true,
    "date_issues_found": 2,
    "files_ready_to_push": 10,
    "validation_errors": 0,
    "next_action": "Run with auto_fix: true to apply changes"
  },
  "recommended_actions": [
    "Review date redistribution changes before applying",
    "Push 10 files to production after applying fixes",
    "Verify article 82 has estimated_traffic_monthly"
  ]
}
```

### Apply Mode (auto_fix: true and dry_run: false)

```json
{
  "ok": true,
  "mode": "apply",
  "website_id": "days_to_expiry",
  "timestamp": "2026-01-28T10:35:00Z",
  "phases": {
    "import_sync": {
      "phase": "import_sync",
      "status": "completed",
      "imported_articles": 62,
      "files_updated": [
        "${WORKSPACE_ROOT}/general/days_to_expiry/articles.json"
      ]
    },
    "date_analysis": { /* Phase 2 output */ },
    "date_optimization": {
      "phase": "date_optimization",
      "status": "completed",
      "articles_redistributed": 8,
      "files_updated": [
        "${WORKSPACE_ROOT}/general/days_to_expiry/articles.json",
        "${WORKSPACE_ROOT}/general/days_to_expiry/content/77_0dte_strategy_radar.mdx",
        "${WORKSPACE_ROOT}/general/days_to_expiry/content/78_options_trading_journal.mdx"
      ]
    },
    "drift_check": { /* Phase 4 output */ },
    "validation": { /* Phase 5 output */ }
  },
  "summary": {
    "changes_applied": true,
    "articles_synced": 62,
    "dates_fixed": 8,
    "files_modified": 9,
    "files_ready_to_push": 10,
    "validation_errors": 0
  },
  "deployment_instructions": {
    "source_dir": "${WORKSPACE_ROOT}/general/days_to_expiry/content",
    "target_dir": "${PRODUCTION_REPO_ROOT}/webapp/content/blog",
    "files_to_copy": [
      "77_0dte_strategy_radar_high_probability_intraday_playbook.mdx",
      "78_options_trading_journal.mdx",
      "79_options_portfolio_management.mdx",
      "80_selling_options_strategy.mdx",
      "81_options_wheel_strategy_analytics.mdx",
      "82_cash_secured_put_calculator.mdx",
      "86_interactive_brokers_portfolio_analysis.mdx",
      "87_options_premium_tracking.mdx",
      "88_options_trading_dashboard.mdx",
      "89_interactive_brokers_flex_query.mdx"
    ],
    "command": "cp [source_dir]/[file] [target_dir]/[file]"
  }
}
```

---

## Error Handling

### Errors should be structured and actionable:

```json
{
  "ok": false,
  "error": {
    "phase": "import_sync",
    "type": "repository_not_found",
    "message": "Production repository not found at ${PRODUCTION_REPO_ROOT}",
    "suggestions": [
      "Check WEBSITES_REGISTRY.json has correct source_repo_local_path",
      "Verify production repository exists on filesystem",
      "Run 'git clone [repo]' to get production repository"
    ]
  }
}
```

### Common Error Types:
- `repository_not_found`: Production repo path invalid
- `registry_not_found`: WEBSITES_REGISTRY.json missing
- `website_not_found`: website_id not in registry
- `articles_json_invalid`: Malformed articles.json
- `permission_denied`: Cannot write to automation files
- `validation_failed`: Content validation errors prevent deployment

---

## Usage Examples

### Example 1: Preview Mode (Default)
```json
{
  "website_id": "days_to_expiry"
}
```
**Result**: Shows what would be synced, analyzed, and fixed without making changes

### Example 2: Apply Sync and Fixes
```json
{
  "website_id": "days_to_expiry",
  "auto_fix": true,
  "dry_run": false,
  "spacing_days": 2
}
```
**Result**: Actually syncs from production, fixes dates, updates files

### Example 3: Conservative Apply (Only Import)
```json
{
  "website_id": "days_to_expiry",
  "auto_fix": false,
  "dry_run": false
}
```
**Result**: Only imports from production, no date fixes applied

### Example 4: Longer Spacing
```json
{
  "website_id": "days_to_expiry",
  "auto_fix": true,
  "dry_run": false,
  "spacing_days": 3,
  "max_recent_days": 14
}
```
**Result**: Fixes articles created in last 14 days with 3-day spacing

---

## Agent Integration Examples

### Agent Decision Tree:

```python
# Agent pseudocode
result = call_tool("seo_ops_sync_and_optimize", {
    "website_id": "days_to_expiry"
})

if not result["ok"]:
    handle_error(result["error"])
    return

summary = result["summary"]

if summary["date_issues_found"] > 0:
    print(f"Found {summary['date_issues_found']} date issues")
    if ask_user("Apply fixes?"):
        result = call_tool("seo_ops_sync_and_optimize", {
            "website_id": "days_to_expiry",
            "auto_fix": True,
            "dry_run": False
        })

if summary["files_ready_to_push"] > 0:
    files = result["deployment_instructions"]["files_to_copy"]
    print(f"Ready to push {len(files)} files to production")
    if ask_user("Copy files to production?"):
        for file in files:
            copy_file(source_dir + file, target_dir + file)
```

### Agent Reactive Parsing:

```python
# Agent automatically reacts to results
result = call_tool("seo_ops_sync_and_optimize", {
    "website_id": "days_to_expiry",
    "auto_fix": True,
    "dry_run": False
})

# Parse phases to understand what happened
for phase_name, phase_data in result["phases"].items():
    if phase_data["status"] == "completed":
        print(f"✓ {phase_name}: {phase_data.get('summary', 'Done')}")
    elif phase_data["status"] == "skipped":
        print(f"- {phase_name}: Skipped ({phase_data['reason']})")
    elif phase_data["status"] == "error":
        print(f"✗ {phase_name}: {phase_data['error']}")

# Check recommendations
for action in result.get("recommended_actions", []):
    print(f"→ {action}")
```

---

## Implementation Notes

### Dependencies (Existing Tools)
This tool orchestrates these existing MCP tools:
1. `seo_ops_import_apply` - Sync from production
2. `seo_ops_dates_analyze` - Analyze dates
3. `seo_ops_schedule_apply` - Fix dates
4. `seo_ops_drift` - Check differences
5. `seo_ops_validate_index` - Validate content

### Performance Considerations
- Should complete in < 10 seconds for typical websites (100 articles)
- Can cache production file hashes to speed up drift detection
- Should report progress if running interactively

### Safety Features
- **Double safety**: Both `dry_run` and `auto_fix` must be set correctly
- **No production writes**: This tool NEVER writes to production repo
- **Immutable articles**: Historical articles are never touched
- **Backup recommendation**: Should suggest git commit before running with auto_fix

---

## Migration Path

### Current Workflow (Manual)
```
1. seo_ops_import_preview
2. seo_ops_import_apply
3. seo_analyze_dates
4. seo_fix_dates
5. seo_ops_drift
```

### New Workflow (Unified)
```
1. seo_ops_sync_and_optimize (preview)
2. seo_ops_sync_and_optimize (apply if happy with preview)
```

### Backward Compatibility
- All existing tools remain available
- Agents can choose to use unified tool or individual tools
- Registry structure unchanged

---

## Testing Strategy

### Unit Tests
- Test each phase independently
- Mock filesystem operations
- Verify phase output structure

### Integration Tests
- Test full workflow with test repositories
- Verify no production files are modified
- Test error conditions (missing registry, invalid paths)

### Safety Tests
- Verify historical articles are never modified
- Test dry_run prevents changes even with auto_fix: true
- Verify rollback if any phase fails

---

## Documentation Requirements

### README Update
Add usage examples and workflow diagram

### Tool Help Text
Clear description of parameters and modes

### Error Messages
All errors should include actionable suggestions

---

## Future Enhancements

### Phase 6: Auto-Deploy (Optional)
Could add optional `deploy: true` parameter that actually copies files to production repo and creates a git commit.

**Risks**: More dangerous, requires git integration
**Benefits**: Fully automated workflow

### Phase 7: Analytics
Track sync frequency, date issue patterns, deployment success rate

### Configuration Presets
```json
{
  "presets": {
    "conservative": {"auto_fix": false, "max_recent_days": 3},
    "normal": {"auto_fix": true, "max_recent_days": 7, "spacing_days": 2},
    "aggressive": {"auto_fix": true, "max_recent_days": 14, "spacing_days": 1}
  }
}
```

---

## Questions for Implementation

1. Should we log all operations to a history file for auditing?
2. Should there be a rollback mechanism if validation fails after fixes?
3. Do we need email/webhook notifications when issues are detected?
4. Should drift check compare content semantically (not just SHA256)?
5. Do we want a "force" mode that can modify historical articles (dangerous)?

---

## Success Metrics

### For Agents
- Reduces tool calls from 5+ to 1-2
- Provides structured data for parsing/decision-making
- Clear next actions in every response

### For Workflows
- Sync operation goes from ~5 min to ~30 seconds
- Date issues automatically detected and fixed
- Production repo stays as source of truth

### For Content Quality
- No more manual date conflicts
- Consistent spacing between articles
- All files validated before deployment
