# Inspection Scheduling Workflow Design

## Intent

Make Administrator inspection scheduling operationally clear while preserving the existing agricultural workflow, RBAC, audit history, and Claude's UI system.

## Existing rules found

- `PestCaseStatus.FOR_INSPECTION` is the only case status accepted by the create-schedule route.
- Creating a schedule inserts one `Inspection`, changes the case to `INSPECTION_SCHEDULED`, and records the scheduling Administrator and assigned Technician.
- `Inspection.pest_case_id` has a database unique constraint, so a case can have only one inspection record.
- The current eligible-case request is the general pest-case list filtered by `status=FOR_INSPECTION`; it does not exclude cases that already have an inspection. This is why a stale `FOR_INSPECTION` case such as Case #17 can remain selectable.
- An inspection is pending only while its case is `INSPECTION_SCHEDULED` and completion/findings fields are empty. Findings completion sets `completed_at`, `completed_by_user_id`, `inspected_on`, `findings`, `pest_confirmed`, and `validated_area_hectares`, then transitions the case to `FIELD_VALIDATED` or `NOT_CONFIRMED`.
- The existing `PUT /api/v1/inspections/<id>/schedule` updates the same inspection record and already blocks non-`INSPECTION_SCHEDULED` cases and completed inspections. It will be retained, but schedule changes will be Administrator-only.
- Technician inspection visibility and findings permissions are assignment-scoped through the existing scoping helpers and will not be broadened.
- `scheduled_for` is a date-only field and the application already uses Asia/Manila for inspection scheduling's current-date helper; new schedules must be today or later.
- Initial report data remains separate from field validation data; scheduling must not validate or confirm a case.

## Goals

- Make the eligible-case list authoritative by excluding any case with an existing inspection while retaining the `FOR_INSPECTION` status rule.
- Preserve duplicate protection and return actionable conflict feedback.
- Enforce today-or-future dates server-side and in the scheduling form.
- Label the field `Scheduled inspection date` with the expected field-visit helper text.
- Allow only Administrators to reschedule pending inspections or reassign their Technicians.
- Prevent edits to completed/historical inspections and preserve assignment-scoped Technician access.
- Add focused regression coverage for eligibility, dates, duplicate protection, update permissions, lifecycle protection, and record uniqueness.

## Non-goals

- No new endpoint, database migration, inspection status, reinspection model, audit-log redesign, or global UI redesign.
- No changes to BRUN-System, TierCourt, ports, unrelated workflows, or existing frontend redesign work.

## Approach

The selected approach is to extend the existing pest-case list query used with `status=FOR_INSPECTION` using a `NOT EXISTS` inspection relationship filter. The existing schedule update endpoint and frontend detail action will be reused. This keeps eligibility rules centralized and avoids a second API contract.

Backend changes will add a shared today-or-future validation for new schedules and schedule updates, improve the duplicate conflict message, apply the inspection exclusion to the eligible case query, and require `ADMIN` for schedule updates. Existing case locking, unique constraints, completion guards, findings transitions, and technician scoping remain intact.

Frontend changes will apply the label/helper text and date minimum/validation to new scheduling, present the existing schedule actions only to Administrators, and keep the current workflow/status presentation native to the enhanced UI. Any derived due/overdue presentation will be added only if it can be implemented from the existing date and completion fields without replacing persisted workflow states.

## Verification

Run focused backend tests, frontend lint/typecheck/build/tests supported by the repository, `git diff --check`, and the configured demo runtime checks on ports 3002 and 5002 using synthetic records only. Report any unavailable check explicitly; do not commit or push.
