export type InspectionRecordability = {
  inspected_on: string | null;
  findings: string | null;
  pest_confirmed: boolean | null;
  completed_at: string | null;
  assigned_to_user_id: number;
  pest_case: { status: string };
};

export function isInspectionPending(item: InspectionRecordability): boolean {
  return (
    item.inspected_on === null &&
    item.findings === null &&
    item.pest_confirmed === null &&
    item.completed_at === null &&
    item.pest_case.status === "INSPECTION_SCHEDULED"
  );
}

// Mirrors backend can_act_on_assigned_work: Admin is office-wide, a Technician
// must be the explicit assignee, and completed inspections are immutable.
export function canRecordInspection(
  role: string | null,
  userId: number | null,
  item: InspectionRecordability,
): boolean {
  if (!isInspectionPending(item)) {
    return false;
  }
  if (role === "ADMIN") {
    return true;
  }
  return role === "TECHNICIAN" && item.assigned_to_user_id === userId;
}

export function canManageInspectionSchedule(role: string | null): boolean {
  return role === "ADMIN";
}
