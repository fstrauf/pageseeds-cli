# Keyword Research Agent Skill

## Purpose
Conduct intelligent keyword research by analyzing project context, existing content, and finding new opportunities.

## Workflow

### Step 1: Read Project Context
Read these files to understand the project:
- `general/{project_id}/{project_id}.md` - Project overview, features, target keywords
- `general/{project_id}/manifest.json` - Website metadata, statistics
- `general/{project_id}/articles.json` - Existing articles and their target keywords

### Step 2: Analyze Existing Keywords
From `articles.json`, extract:
- All `target_keyword` values already in use
- Content clusters covered
- Content gaps (missing clusters)

### Step 3: Identify Opportunities
Look for:
1. **Untapped keywords** from project overview "Search Keywords" sections
2. **Long-tail variations** of existing keywords
3. **Competitor gaps** - keywords mentioned but no article created
4. **Trending topics** related to project themes

### Step 4: Research New Keywords
Use the keyword research tool:
```bash
pageseeds automation seo keyword-research --theme "your theme" --output output/keyword_findings.json
```

Or use the Python API:
```python
from seo_mcp.keywords import get_keyword_ideas
results = get_keyword_ideas("your seed keyword", country="us")
```

### Step 5: Validate & Prioritize
For each candidate keyword, check:
- **Difficulty (KD)**: Target < 30 for new sites, < 15 for quick wins
- **Volume**: Minimum 50-100 monthly searches
- **Relevance**: Must match project offering
- **Competition**: Avoid saturated SERPs with high DR sites

### Step 6: Output Findings
Create findings in this format:
```json
{
  "findings": [
    {
      "source": "keywords",
      "type": "keyword_opportunity",
      "keyword": "target keyword phrase",
      "title": "Article Title Idea",
      "difficulty": 5,
      "volume": 200,
      "cluster": "cluster_name",
      "severity": "critical|high|medium|low",
      "description": "Why this keyword is valuable",
      "content_gap": true
    }
  ]
}
```

## Example Prompt

Given:
- Project: coffee (BrewedLate)
- Existing articles: 27 articles covering subscriptions, pricing, origins
- Target: Find 5 new keyword opportunities

You would:
1. Read `general/coffee/coffee.md` → extract "Search Keywords" sections
2. Read `general/coffee/articles.json` → list existing target keywords
3. Compare → find gaps (keywords mentioned but no article)
4. Research → validate volume/difficulty for 5 gaps
5. Output → structured findings

## Output Format

Write findings to:
`.github/automation/campaigns/{run_id}/artifacts/keyword_research_agent.json`

## Notes

- Use existing project knowledge - don't suggest duplicate keywords
- Focus on buyer intent keywords for commercial projects
- Prioritize zero/low competition opportunities (KD < 5)
- Consider seasonal trends for timing
