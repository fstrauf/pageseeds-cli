---
name: landing-page-keyword-research
description: Research keywords for landing page opportunities and create detailed specifications for high-intent, conversion-focused pages.
---

# Landing Page Keyword Research

⚠️ **EXECUTION MANDATE**: Do NOT ask questions, summarize, or provide options. Execute this workflow immediately and completely.

## Purpose

This workflow finds **landing page opportunities** - keywords with commercial/transactional intent that deserve dedicated landing pages rather than blog articles.

Landing pages differ from blog articles:
- **Focus**: Product/solution positioning, not educational content
- **Intent**: Transactional/commercial (user wants to buy, compare, or take action)
- **Structure**: Hero section, value props, features, social proof, CTAs
- **Goal**: Conversion, not just traffic

## Hard Rules (No MCP Server)

- Do NOT run ad-hoc terminal commands/scripts.
- Use only the `seo-cli` and `seo-content-cli` commands listed in this skill.
- Do not call any tool functions/integrations directly. Only run the `seo-cli|seo-content-cli ...` commands.

## Terminal Execution Rules (MANDATORY)

**All commands MUST run in the foreground.** The agent waits for each command to finish and reads its output before proceeding.

Specifically:
- **NEVER** background a command with `&`
- **NEVER** redirect output to temp files (`> /tmp/...`, `> output.json`)
- **NEVER** use `sleep`, `ps`, `tail`, `wc -l`, or `jobs` to poll for completion
- **NEVER** use `2>&1 &` or `nohup`
- **ALWAYS** run each command and wait for it to return

## Landing Page Keyword Criteria

When evaluating keywords for landing pages, prioritize:

| Criteria | Target | Why |
|----------|--------|-----|
| **Intent** | Transactional/Commercial | User wants to buy, compare, or take action |
| **Keyword Difficulty** | <40 (ideally <30) | Can realistically rank |
| **Search Volume** | 200+ monthly | Worth the investment |
| **Specificity** | 2-4 word phrases | Balance volume + intent |
| **Product Fit** | High alignment | Your product solves this |
| **Competition Gap** | Weak landing pages | Opportunity to outrank |

### High-Intent Patterns (Prioritize These)

- "best [product] for [use case]"
- "[product] alternative" or "[competitor] alternative"
- "[product] vs [competitor]"
- "[category] software/tool/platform"
- "[solution] for [audience]"
- "compare [products]"
- "top [category] tools"

### Avoid (Blog Content Instead)

- "how to [do something]" → informational
- "what is [concept]" → informational
- "guide to [topic]" → informational
- "tips for [activity]" → informational

## Tooling Requirements

### Primary Commands

```bash
# Get current articles summary (to avoid duplication)
seo-content-cli --workspace-root automation articles-summary --website-path .

# Research keywords for landing page themes
seo-content-cli --workspace-root automation research-keywords \
  --website-path . \
  --themes 'theme1' 'theme2' 'theme3' \
  --country us \
  --analyze-difficulty --top-n 10 \
  --auto-append --min-volume 200 --max-kd 40
```

**Note**: Use `--min-volume 200` (lower than articles) because landing pages have higher conversion value.

### Individual Keyword Check

```bash
seo-cli keyword-difficulty --keyword '<keyword>' --country us
```

## Workflow

### 1) Extract Current State

Read existing content to understand:
- Existing landing pages (if any)
- Product positioning and key value props
- Target audiences and use cases
- Competitors mentioned

### 2) Generate Landing Page Themes

Based on product positioning, create themes targeting commercial intent:

**Theme Categories:**

1. **Alternative Pages** (High Priority)
   - "[Competitor] alternative" - capture users comparison shopping
   - "[Competitor] vs [Your Product]" - direct comparison

2. **Use Case Pages** (High Priority)
   - "[Solution] for [Specific Audience]"
   - "[Solution] for [Use Case]"

3. **Category Pages** (Medium Priority)
   - "Best [Category] Software"
   - "Top [Category] Tools"

4. **Feature-Specific Pages** (Medium Priority)
   - "[Feature] Software"
   - "[Capability] Tool"

### 3) Research Keywords

Run `research-keywords` with landing page criteria:

```bash
seo-content-cli --workspace-root automation research-keywords \
  --website-path . \
  --themes '[competitor] alternative' '[use case] software' 'best [category] tools' \
  --country us \
  --analyze-difficulty --top-n 10 \
  --auto-append --min-volume 200 --max-kd 40
```

### 4) Filter for Landing Page Suitability

From the results, manually filter for landing page candidates:

**Keep if:**
- Transactional/commercial intent
- User is comparing solutions or ready to buy
- Can naturally lead to product pitch

**Skip if:**
- Purely informational intent
- Better suited as blog content
- Would require forced product mention

### 5) Create Landing Page Specifications

For each approved keyword, create a detailed specification (NOT the actual page).

The specification should be saved to:
```
{target_repo}/.github/automation/specs/landing_page_{keyword_slug}.md
```

## Specification Template

Each landing page spec must include:

```markdown
# Landing Page Specification: [Page Title]

## Target Keyword
[Exact keyword phrase]

## Search Intent
- **Type**: [Transactional/Commercial/Comparison]
- **User Goal**: [What they're trying to achieve]
- **Conversion Goal**: [What we want them to do]

## Page Strategy

### Positioning
[How this page positions the product]

### Key Value Propositions
1. [Primary value prop]
2. [Secondary value prop]
3. [Tertiary value prop]

### Target Audience
[Specific audience segment this targets]

## Page Structure

### 1. Hero Section
- **Headline**: [H1 - must include target keyword]
- **Subheadline**: [Supporting value prop]
- **Primary CTA**: [Button text + destination]
- **Visual**: [Recommended image/illustration type]

### 2. Problem/Solution Section
- **Problem Statement**: [The pain point]
- **Solution Intro**: [How we solve it]
- **Transition**: [Bridge to features]

### 3. Key Features (3-4)
- **Feature 1**: [Name + benefit-focused description]
- **Feature 2**: [Name + benefit-focused description]
- **Feature 3**: [Name + benefit-focused description]

### 4. Social Proof
- **Type**: [Testimonials/logos/stats/case studies]
- **Content**: [Specific quotes or data to include]

### 5. Comparison Section (if applicable)
- **Comparison Table**: [What to compare]
- **Our Advantage**: [Why we're better]

### 6. FAQ Section (2-3 questions)
- **Q1**: [Question including keyword variant]
- **A1**: [Answer with natural keyword usage]

### 7. Final CTA Section
- **Headline**: [Urgency or benefit-focused]
- **CTA Button**: [Action-oriented text]

## SEO Requirements

### Title Tag
[60 characters max, include keyword]

### Meta Description
[150-160 characters, include keyword + CTA]

### URL Slug
/recommended-slug-with-keyword

### Internal Links
- **Link to**: [Related pages to link to]
- **Link from**: [Existing pages that should link here]

## Content Guidelines

### Tone
[Professional/friendly/technical/etc.]

### Messaging Do's
- [Specific messaging guidance]

### Messaging Don'ts
- [What to avoid]

## Design Notes
- **Layout**: [Single column/two column/etc.]
- **Colors**: [Any specific brand color usage]
- **Component Needs**: [Special components required]

## Acceptance Criteria
- [ ] All sections completed
- [ ] Keyword appears in H1, title, first paragraph
- [ ] At least 2 CTAs present
- [ ] Mobile-responsive design
- [ ] Page speed optimized
- [ ] Conversion tracking in place
```

## Output Requirements

1. **Create specification file** for each landing page opportunity
2. **Do NOT write the actual landing page** - only the spec
3. **Save to**: `.github/automation/specs/landing_page_{slug}.md`
4. **Create a task** in `task_list.json` for each spec:
   ```json
   {
     "id": "XXX-NNN",
     "type": "landing_page_spec",
     "title": "Landing page: [keyword]",
     "phase": "implementation",
     "status": "todo",
     "spec_file": "specs/landing_page_{slug}.md"
   }
   ```

## Re-run Logic

- **Monthly**: Check for new competitor/alternative keywords
- **Quarterly**: Refresh KD/volume data
- **After product updates**: New features → new use case pages
- **After competitor launches**: New alternative pages

## Success Metrics

A landing page specification is successful if:
- Target keyword has clear commercial intent
- KD < 40 with volume > 200
- Page structure supports conversion
- Differentiation from existing content is clear
- Implementation is feasible for the dev team
