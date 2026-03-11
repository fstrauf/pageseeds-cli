---
name: automation0-status
description: Check whether the installed automation payload in the current repo is out of sync.
argument-hint: ""
agent: agent
---

Check whether this repo's automation payload is out of sync with the source.

```bash
pageseeds automation repo status
```

If `out_of_sync` is true, run:

```bash
pageseeds automation repo update
```

