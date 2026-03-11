---
name: reddit-opportunity-search
description: Run Reddit Stage 1 - search seed subreddits/queries, score posts, draft replies, save to markdown, auto-create reply tasks.
---

# Reddit Opportunity Search (Stage 1)

## Core Principle: Auto-Create Tasks

1. Search Reddit for opportunities
2. Score and draft replies
3. Save results to markdown file
4. **Automatically create reply tasks for each opportunity**

## Inputs (in target repo)

All config files are read from `{repo}/.github/automation/`:

| File | Purpose |
|------|---------|
| `{project}.md` | Website/product description (e.g., `expense.md`) |
| `reddit_config.md` | Seed subreddits, queries, product mention rules |
| `brandvoice.md` | Tone and voice guidelines |
| `reddit/_reply_guardrails.md` | Reply formatting rules |

## Workflow

### 1) Read Config

Extract from reddit_config.md:
- Product name
- Seed subreddits
- Seed queries
- When to mention product

### 2) Search Reddit

For each subreddit + query:
```
automation-cli reddit search-submissions --query '<term>' --subreddit '<subreddit>' --limit 30 --sort relevance --time week
```

**EXCLUDED SUBREDDITS (Never Search):**
Read `reddit_config.md` for project-specific excluded subreddits. Common exclusions:
- personalfinance (banned or too broad)

**HARD RULE - 14 Day Filter:**
- Skip any post older than 14 days
- Check `posted_date` before scoring  
- Only include posts from the last 2 weeks (older posts feel awkward to reply to)

### 3) Score Posts (0-10 each)

- **Relevance**: How well it matches
- **Engagement**: min(10, upvotes / days_old / 10)
- **Accessibility**: <10 comments=10, 10-30=8, 30-100=6, 100+=2
- **Final Score**: Average

### 4) Assign Severity

- CRITICAL: 8.5+
- HIGH: 7.0-8.4
- MEDIUM: 5.0-6.9

### 5) Draft Replies (MEDIUM+)

- 3-5 sentences, plain text, no links
- Formula: Acknowledge → Educate → Product (if natural) → Engage
- Vary product mention phrasing
- **Critique pass**: Act as old copy editor who respects reader's time

### 6) Save & Create Tasks

Save to: `artifacts/reddit/search_{project}_{timestamp}.md`

Then **automatically create a reddit_reply task for each opportunity** so they appear in the dashboard ready to work on.

## Output Format (Markdown)

```markdown
# Reddit Opportunities: {project}

Search Date: YYYY-MM-DD
Total Found: X

## Summary
- CRITICAL: X
- HIGH: X
- MEDIUM: X

---

## Opportunity 1

**Post:** [actual post title]
**Subreddit:** r/[name]
**Severity:** [LEVEL]
**Score:** X.X/10
**URL:** [full permalink]
**Why Relevant:** [one sentence]

**Drafted Reply:**
[actual 3-5 sentence reply]

---

[repeat...]
```

**Important**: The system will automatically create individual reply tasks from this file. Human can then bulk-process them.
