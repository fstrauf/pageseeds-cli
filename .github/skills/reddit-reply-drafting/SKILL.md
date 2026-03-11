---
name: reddit-reply-drafting
description: Draft 3–5 sentence Reddit replies using generic standards + project-specific config (product name, mention stance, topic triggers).
---

# Reddit Reply Drafting

## Pre-Drafting Requirements

Before drafting any reply, you MUST read:

1. **`projects/reddit/_reply_standards.md`** → Generic rules that apply to ALL projects
2. **`general/<project>/reddit_config.md`** → Product name + mention stance (REQUIRED/RECOMMENDED/OPTIONAL/OMIT) + trigger topics
3. **`general/<project>/<project>.md`** → Project description
4. **`general/brandvoice.md`** → Tone and voice

## Workflow

### Step 1: Determine Product Mention Stance

Read `general/<project>/reddit_config.md` and extract:
- **Product name:** Exact text to use in replies
- **Stance:** REQUIRED / RECOMMENDED / OPTIONAL / OMIT
- **Trigger topics:** Which post topics require/allow product mention

Compare the Reddit post against trigger topics → determine if product mention applies.

### Step 2: Draft the Reply

Follow the formula from `_reply_standards.md`:

**[Acknowledge] → [Educate] → [Tool/Product (if applicable)] → [Engage]**

Requirements:
- 3–5 sentences exactly
- Plain text only (no Markdown)
- No links
- Product mention follows stance from Step 1
- End with genuine question

### Step 3: Run the Critique Pass

**Mandatory for every reply:**

> Act as an old copy editor at a respected newspaper who believes deeply in respecting your reader's time. Review your drafted reply:
> 1. Is every sentence earning its place?
> 2. Can any words be cut?
> 3. Is the tone conversational?
> 
> Revise based on this critique.

### Step 4: Final Validation

Check against the Quality Checklist from `_reply_standards.md`:
- [ ] 3–5 sentences
- [ ] No links
- [ ] No Markdown
- [ ] Product mention matches stance
- [ ] Ends with real question
- [ ] Reader gets value without clicking anything

## Product Mention Quick Reference

| Stance | Behavior | Example trigger topics |
|--------|----------|------------------------|
| **REQUIRED** | MUST include product name | Post is about core product functionality |
| **RECOMMENDED** | Include unless forced | Post aligns well with product use case |
| **OPTIONAL** | Include only if natural | Loose connection to product |
| **OMIT** | Do not mention | Post is off-topic or culturally inappropriate |

## Varied Mention Patterns (Rotate These)

Don't use the same pattern every time. Rotate through:

**Pattern A – Habit:** "I use [Product] to..." / "I typically check [Product] when..."
**Pattern B – Casual:** "With [Product], I can..." / "[Product] lets me..."
**Pattern C – Context:** "When I'm [activity], I'll sanity-check in [Product]..."
**Pattern D – Soft:** "My workflow involves [Product] for..."

## Common Mistakes to Avoid

- **Vague product references:** "a dedicated tool", "a platform", "the app", "my tracker" → Use EXACT product name
- Feature lists ("Product X has backtesting, pricing, and integrations")
- Disconnected mentions ("I don't use tools, but Product X is great!")
- CTAs ("Check it out!" / "Sign up!")
- Corporate jargon ("solution", "platform", "leverage")
- Generic advice without specific framework

### When Stance is REQUIRED

You MUST include the exact product name. **Never substitute with vague language.**

**✅ CORRECT:** "I use Days to Expiry to track my positions."
**❌ WRONG:** "I use a dedicated tool to track my positions."
**❌ WRONG:** "I built a tool for this." (unless you literally built it yourself)

## Reference Files

| File | Purpose |
|------|---------|
| `projects/reddit/_reply_standards.md` | Generic rules for ALL projects |
| `general/<project>/reddit_config.md` | Project-specific: name, stance, triggers |
| `general/<project>/<project>.md` | Project description |
| `general/brandvoice.md` | Tone and voice |
