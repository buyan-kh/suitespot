# SuiteSpot agent rules

Ten people work in this repo with coding agents. Stay inside your task. Do not edit someone else's code.

## Stay in your task

- Edit only files the current task needs.
- Create new features in a new folder. A new page goes in its own route under `frontend/app/`. A new API goes in its own module under `backend/`.
- Do not refactor, reformat, rename, or restyle code you did not write for this task.
- Do not delete a file you did not create.
- If the task needs a file outside your area, stop. Name the file and why. Wait until the owner says yes.

## Shared files

These files affect everyone. Leave them alone unless Buyan or the owner named that file in the task:

- `frontend/package.json`, `frontend/package-lock.json`
- `frontend/app/layout.tsx`, `frontend/app/page.tsx`, `frontend/app/globals.css`
- `frontend/components/layout/`, `frontend/components/ui/`
- `frontend/tsconfig.json`, `frontend/next.config.ts`, `frontend/eslint.config.mjs`, `frontend/postcss.config.mjs`
- `frontend/AGENTS.md`, `frontend/CLAUDE.md`
- `AGENTS.md`, root `README.md`, `.github/`

Do not add, remove, or upgrade a package unless the task says to.
Do not commit `node_modules`, `.env`, API keys, or tokens.

## Git

- Work on your own branch from `main`. One branch per task. Never commit or push to `main`.
- Name the branch with the team, your name, and the task: `frontend/your_name-search-page`, `backend/your_name-login-api`.
- Never force-push, rebase a shared branch, or change git config.
- One feature per pull request. The diff should be your files.
- Pull `main` before you start.
- In the pull request, list every file you changed that you did not create.

## When you are unsure

Ask in the pull request or the team chat. Do not guess and edit.
