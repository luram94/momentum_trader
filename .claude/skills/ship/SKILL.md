---
name: ship
description: Branch/PR/merge workflow for this repo, including deploy verification on Streamlit Cloud
---

# Shipping changes in momentum_trader

## Rules
- Push and open PRs **only to `origin`** (github.com/luram94/momentum_trader),
  never to any `dev` remote.
- Never commit directly to `main` except for emergency hotfixes the user
  explicitly asks for (precedent: the fileWatcherType/segfault hotfixes).
- One logical change per PR; merge one PR at a time. Merge style used here:
  merge commits (`gh pr merge <n> --merge --delete-branch`).

## Flow
1. `git checkout -b <type>/<slug>` off up-to-date `main`
   (types in use: `fix/`, `feat/`, `refactor/`, `perf/`).
2. Implement; verify with the **verify** skill (pytest + AppTest; Docker if
   the change touches the image).
3. Commit with an imperative summary line; body explains the why and any
   measured results.
4. `git push -u origin <branch>` then `gh pr create` with Summary +
   Verification sections.
5. Merge (only when the user asks, or has said to do everything):
   `gh pr merge <n> --merge --delete-branch`.
6. Anything merged to `main` auto-deploys to Streamlit Cloud — verify with
   the **verify-live** skill.

## Stacked-PR trap (hit on 2026-07-10)
If PR B's base is PR A's branch, merging A with `--delete-branch` makes GitHub
**CLOSE PR B** (it does not retarget it), and a closed PR's base can't be
edited. Recovery: the head branch still exists — recreate the PR with
`gh pr create --head <branch> --base main` (diff shrinks to B's own commits
once A is in main). Better: retarget B to main (`gh pr edit B --base main`)
BEFORE merging A, or don't delete A's branch until B is retargeted.

## After merging
- `git fetch --prune` to drop stale remote-tracking refs.
- If the change affects data shape or refresh timing, update the README and
  the **verify** skill numbers.
