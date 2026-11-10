# Sugarcane Local Demo Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the existing Sugarcane application for a safe local client demo on ports 3002/5002, launched and supervised through `Sugarcane -Open` from one Windows PowerShell terminal.

**Architecture:** Keep application behavior unchanged. Use the existing Flask application through Flask's supported CLI port override, Next.js's supported development-server port override, ignored local env files for machine-specific configuration, and one PowerShell 5.1-compatible supervisor for preflight, labeled output, readiness, browser launch, and process-tree cleanup.

**Tech Stack:** Windows PowerShell 5.1, Python 3.13 virtual environment, Flask 3.1, PostgreSQL 17, Node 24, npm 11, Next.js 16.

**Spec:** `C:\Users\Acer\.codex\attachments\87f8b04f-a6e0-40d7-bce7-201f2d6b25d9\Pasted text.txt`

## Global Constraints

- Work only in `C:\TierCourt-Player\SugarcanePestSystem-Thesis`, except for the explicitly authorized current-user PowerShell profile registration and its backup.
- Preserve unrelated work, including the pre-existing modification to `frontend/app/globals.css`.
- Do not touch the BRUN-System processes on ports 3000/5000.
- Use backend `127.0.0.1:5002`, frontend `localhost:3002`, PostgreSQL `127.0.0.1:5434`, and database `sugarcane_pest_test`.
- Use only the repository migrations, guarded synthetic seeder, password hashing, authentication, RBAC, and workflow rules.
- Do not print or persist plaintext administrator or PostgreSQL passwords in tracked files, logs, or the final report.
- Do not commit or push.

## Review Focus

- Port 3002 or 5002 becomes occupied: report owner details and abort without killing it.
- One child exits during startup or runtime: surface its output and clean up only the launched Sugarcane process tree.
- Backend/database/frontend readiness times out: fail with the responsible component named and release both demo ports.
- Ctrl+C interrupts the supervisor: the `finally` path stops both process trees and checks port release.
- Profile registration is repeated: replace one marked function block without duplicating or disturbing unrelated profile content.

---

### Task 1: Reproducible local dependencies and ignored configuration

**Files:**
- Create (ignored): `backend/.venv/`
- Create (ignored): `backend/.env`
- Create (ignored): `frontend/node_modules/`
- Create (ignored): `frontend/.env.local`

**Interfaces:**
- Produces a Python interpreter with exactly `backend/requirements.txt`, a lockfile-driven npm install, and local configuration for PostgreSQL plus ports 3002/5002.

- [ ] Reconfirm branch, HEAD, status, ignored env paths, and free demo ports.
- [ ] Create `backend/.venv` and install `backend/requirements.txt` without upgrades.
- [ ] Run `npm ci` from `frontend`.
- [ ] Create missing env files with a generated secret, localhost-only trusted origin, secure-cookie disabled for HTTP localhost, database settings, and `BACKEND_API_URL=http://127.0.0.1:5002`.
- [ ] Verify imports, Next.js CLI port support, ignored status, and absence of tracked dependency/env changes.

### Task 2: PostgreSQL demo database, migrations, seed, and administrator

**Files:**
- Modify no tracked files.

**Interfaces:**
- Consumes the local backend environment and repository CLI commands.
- Produces migrated `sugarcane_pest_test`, idempotent synthetic data, and active `admin_demo` with role `ADMIN`.

- [ ] Attempt guarded local database/role discovery without displaying credentials.
- [ ] If PostgreSQL administrator authentication is required, stop at the exact interactive step and provide one manual command that prompts securely.
- [ ] Run `flask db upgrade` and verify Alembic revision `d6b8f2a1c4e7` plus the expected database identity.
- [ ] Run the existing demo seeder twice; verify first-run success or existing marker, then idempotent refusal.
- [ ] Inspect `admin_demo`; if absent, use interactive `flask create-admin` so the user enters a hidden password.
- [ ] Verify username, active state, and `ADMIN` role without exposing hashes or passwords.

### Task 3: One-terminal PowerShell supervisor

**Files:**
- Create: `scripts/Sugarcane.ps1`
- Test: `scripts/Sugarcane.Tests.ps1`

**Interfaces:**
- Consumes repository paths, ignored env files, `.venv`, `node_modules`, PostgreSQL service/connection, and the existing Flask/Next.js CLIs.
- Produces `scripts/Sugarcane.ps1 -Open`, supervising Flask on 5002 and Next.js on 3002 with labeled streams and bounded readiness.

- [ ] Write Pester 3-compatible contract tests for exact ports/URLs, preflight failure behavior, required process labels, bounded readiness, browser target, and cleanup hooks.
- [ ] Run tests and confirm they fail because the launcher is absent.
- [ ] Implement the smallest PowerShell 5.1-compatible launcher: repo/dependency/env/database/admin/port checks, Flask CLI and Next CLI child processes, redirected labeled streams, health polling, optional browser open, runtime monitoring, and `finally` cleanup of only captured process trees.
- [ ] Run the focused Pester suite and PowerShell parser validation until both pass.

### Task 4: Idempotent current-user command registration

**Files:**
- Modify (outside repository, explicitly authorized): active current-user PowerShell profile.
- Create (outside repository): timestamped profile backup.

**Interfaces:**
- Consumes `scripts/Sugarcane.ps1`.
- Produces the global current-user function `Sugarcane([switch]$Open)`.

- [ ] Back up the active profile before its first modification.
- [ ] Insert or replace one marked minimal function block while preserving unrelated content.
- [ ] Reload the profile and verify `Get-Command Sugarcane` resolves to a function invoking the repository launcher.
- [ ] Repeat registration and verify the marker/function remains singular.

### Task 5: End-to-end runtime and shutdown verification

**Files:**
- Modify no tracked files unless a setup-specific defect is proven first.

**Interfaces:**
- Consumes `Sugarcane -Open` and the configured demo data/admin.
- Produces evidence for runtime, application routes, authorization, browser launch, one-terminal supervision, and cleanup.

- [ ] Start `Sugarcane -Open` from outside the repository and capture labeled backend/frontend readiness without exposing secrets.
- [ ] Have the user enter the administrator password only through the real hidden/login UI interaction when required.
- [ ] Verify login, dashboard, farmers, farms, pest cases, inspection/validation, intervention, follow-up/reassessment, reports, map, logout/login, admin authorization, and technician confidentiality using real routes and existing tests where direct browser interaction cannot prove server-side invariants.
- [ ] Interrupt the supervising terminal with Ctrl+C; confirm both captured process trees stop and ports 3002/5002 are released.
- [ ] Run focused backend/frontend/launcher tests, `git diff --check`, review the final diff, and report exact tracked/ignored/profile changes and any unverified item.
