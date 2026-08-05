# Code Instructions

## 🧠 Memory Log

At the **start of every session**, do this silently:
1. Check if `.memory/MEMORY_LOG.md` exists
2. If it does, read the last entry and note what was in progress
3. Briefly tell me: *"Last session: [date] — [one line summary of what we were doing]"*
4. If it doesn't exist yet, create the `.memory/` folder and initialize `MEMORY_LOG.md` with the template below

At the **end of a session**, or whenever I say any of the following:
- "update memory log"
- "log this session"
- "save what we did"
- "update my log"

...append a new dated entry to `.memory/MEMORY_LOG.md` using the format below.
**Never overwrite or delete previous entries. Append only.**

### Entry Format

```
## [YYYY-MM-DD] — [Short title, e.g. "Corge: swap UI animation + Zustand fix"]

### Project Status & Decisions
- 

### Tech Stack & Tools
- 

### Problems Solved / Lessons Learned
- [Problem]: [Solution]

### Goals & Next Steps
- 

---
```

### Initial File Template (if `.memory/MEMORY_LOG.md` doesn't exist)

```
# 🧠 Memory Log
> Append-only. Never delete or edit previous entries.
> Initialized: [DATE]

---
```

### Rules
- Be **specific** — file names, function names, error messages, decisions + reasoning
- One entry per session, even if I ask multiple times
- If the session was trivial (quick question, no real work), ask me before logging
- Always confirm after writing: *"Memory log updated ✓ — [one-line summary]"*

---

## 👤 About This Workspace

**Developer:** Wale 

### General Preferences
- Prefers cutting-edge UI/UX — avoid generic, avoid overuse of gradients, plain designs
- Likes 3D graphics (React Three Fiber) when needed, loves fluid and clean animations
- Blockchain/Web3 native — familiar with DeFi, NFTs, smart contracts
- Always use modern patterns: hooks, composition, clean component architecture
