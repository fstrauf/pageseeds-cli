---
name: reddit-analysis-optimization
description: Run Reddit Stage 3: update engagement metrics for posted replies and analyze statistics to refine future searches and reply patterns.
---

# Reddit Analysis & Optimization (Stage 3)

## Workflow

### 1) Load Posted Opportunities

- `pageseeds reddit posted --project '<project>' --days 30 --limit 20`

### 2) Gather Engagement Data

For each opportunity, open the stored `reply_url` and record:

- reply upvotes
- reply comments

### 3) Update Performance Metrics

- `pageseeds reddit update-performance --post-id '<id>' --reply-upvotes <n> --reply-replies <n>`

### 4) Analyze Patterns

- `pageseeds reddit stats --project '<project>'`

Look for:

- best subreddits
- best topics
- reply structure patterns
- timing patterns

### 5) Feed insights back into Stage 1

Adjust seed queries (in config) and your scoring intuition based on what worked.
