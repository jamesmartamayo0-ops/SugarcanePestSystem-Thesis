# Inspection Scheduling Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make inspection scheduling authoritative, date-correct, Administrator-managed, and clear without changing the existing workflow model or UI system.

**Architecture:** Reuse the existing `status=FOR_INSPECTION` pest-case list and add a SQL `NOT EXISTS` inspection filter so the selector is backed by the domain relationship. Reuse the existing inspection schedule update endpoint and detail UI, adding shared date validation, Administrator-only authorization, and focused presentation copy. Keep the existing unique constraint, case locks, completion guards, and technician scoping.

**Tech Stack:** Flask, SQLAlchemy, pytest, Next.js/React/TypeScript, npm scripts, existing demo runtime on ports 5002/3002.

**Spec:** `docs/superpowers/specs/2026-11-09-inspection-scheduling-design.md`

## Global Constraints

- Do not commit, push, merge, rebase, reset, restore, clean, or change branches.
- Preserve all pre-existing Claude frontend/UI changes and Codex setup artifacts.
- Do not change BRUN-System, TierCourt, ports 3000/5000, unrelated workflows, or the database schema.
- New schedules accept today and future dates only, using the existing Asia/Manila date policy.
- Only Administrators may create, reschedule, or reassign inspection schedules; Technicians remain assignment-scoped for viewing and findings.
- Scheduling never validates a case; field findings remain the transition to validation outcomes.

## Review Focus

- A case with `FOR_INSPECTION` status but an existing inspection must be absent from the eligible query; test it in the pest-case listing.
- A stale/racing duplicate schedule must still return 409 with actionable management guidance; test the existing create route and unique protection.
- A date before Manila today must fail for both creation and pending schedule update while today and future dates pass; test with a patched date helper.
- A Technician must not update a pending schedule even when assigned; test 403 and unchanged date/assignee.
- A completed inspection must remain immutable through the update route; test 409 and unchanged completion/history fields.

### Task 1: Backend eligibility and date policy

**Files:**
- Modify: `backend/app/models/inspection.py`
- Modify: `backend/app/routes/pest_cases.py`
- Modify: `backend/app/routes/inspections.py`
- Test: `backend/tests/test_inspections.py`
- Test: `backend/tests/test_pest_cases.py`

**Interfaces:**
- Produces a reusable scheduled-date validator based on `manila_today()` and a case-list query that excludes cases having any `Inspection` row.

- [ ] **Step 1: Write failing unit/API tests** for: existing-inspection exclusion from `status=FOR_INSPECTION`; today accepted; future accepted; past rejected on create; past rejected on update; actionable duplicate message; Technician schedule update forbidden; Administrator pending update allowed; completed update rejected.
- [ ] **Step 2: Run the focused tests** with `pytest backend/tests/test_inspections.py backend/tests/test_pest_cases.py -q`; confirm failures are due to the missing eligibility/date/authorization behavior.
- [ ] **Step 3: Implement the smallest backend changes**: add the `NOT EXISTS` relationship predicate only when listing `FOR_INSPECTION` cases, add a Manila today-or-future validator for create/update, use the approved duplicate message, and change schedule-update authorization to Administrator-only while retaining pending/completion guards and locking.
- [ ] **Step 4: Run the focused tests again** and confirm all new and existing tests pass.

### Task 2: Frontend scheduling UX and client validation

**Files:**
- Modify: `frontend/app/inspections/page.tsx`
- Modify: `frontend/lib/inspections.ts` only if response/error typing requires it
- Test: repository-supported frontend tests or add a focused pure helper test only if an existing test convention supports it

**Interfaces:**
- Consumes the existing backend-filtered `listPestCases({ status: "FOR_INSPECTION" })` result and existing `rescheduleInspection` API client.

- [ ] **Step 1: Add a focused frontend regression test** for the scheduling date constraint if the repository test setup supports page/helper tests; otherwise pin the behavior with the existing TypeScript/lint checks and manual form verification.
- [ ] **Step 2: Run the focused frontend test/check** and confirm the new expectation fails before implementation.
- [ ] **Step 3: Update the scheduling form** to use the exact label `Scheduled inspection date`, the exact helper text `Select the date the assigned Agriculture Technician is expected to conduct the field inspection.`, and a local-date minimum for today; add submit-time past-date validation rather than relying on HTML `min` alone.
- [ ] **Step 4: Ensure schedule-management controls are Administrator-only** while retaining detail visibility and assigned-Technician findings access; preserve the existing report/inspection/field-validation distinction and native UI components.
- [ ] **Step 5: Run the frontend focused checks** and confirm the form and page compile cleanly.

### Task 3: Full verification and runtime review

**Files:**
- Modify: none unless verification exposes a task-scoped defect

- [ ] **Step 1: Run backend tests** including the full repository-supported pytest suite and record exact counts/results.
- [ ] **Step 2: Run frontend tests, lint, typecheck, and production build** using the commands in `frontend/package.json`; record exact results.
- [ ] **Step 3: Run `git diff --check` and inspect the final diff**, confirming only task-scoped files changed beyond the approved design/plan documents and pre-existing dirty files remain intact.
- [ ] **Step 4: Start or use the established local demo services** on `127.0.0.1:5002` and `localhost:3002` without changing ports; use synthetic records only.
- [ ] **Step 5: Manually verify Administrator eligibility, today/future scheduling, duplicate feedback, pending reschedule/reassignment, completed-history protection, Technician assignment-scoped visibility, and unchanged report-versus-validation semantics.
- [ ] **Step 6: Capture final `git status --short`, `git diff --stat`, and `git diff --name-only` for the implementation report; do not commit or push.
