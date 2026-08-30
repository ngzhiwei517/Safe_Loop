import { apiFetch } from "./api";
import { listReports, type ReportListItem } from "./reports";
import { reportStatus } from "./stateMachine";

export type OpenAction = ReportListItem & {
  action_id: string;
  action_text: string;
  action_due_at: string;
};

export type ActionSubmitInput = {
  completed_note?: string;
  media_ids: string[];
  transcript_id?: string;
};

export type ActionSubmitResult = {
  report_id: string;
  action_id: string;
  status: typeof reportStatus.action_submitted;
  completed_note: string | null;
  submitted_at: string;
  media_ids: string[];
};

function isOpenAction(report: ReportListItem): report is OpenAction {
  return Boolean(report.action_id && report.action_text && report.action_due_at);
}

export function isReturnedAction(action: OpenAction): boolean {
  return action.sent_back_unresolved;
}

export function sortOpenActions(actions: OpenAction[]): OpenAction[] {
  return [...actions].sort((left, right) => {
    const returnedOrder = Number(isReturnedAction(right)) - Number(isReturnedAction(left));
    if (returnedOrder !== 0) return returnedOrder;
    const dueOrder = new Date(left.action_due_at).getTime() - new Date(right.action_due_at).getTime();
    return dueOrder || left.action_id.localeCompare(right.action_id);
  });
}

export async function listOpenActions(accessToken: string): Promise<OpenAction[]> {
  const actions: OpenAction[] = [];
  let cursor: string | undefined;
  do {
    const page = await listReports(
      {
        status: reportStatus.action_assigned,
        assignee: "me",
        limit: 100,
        cursor,
      },
      accessToken,
    );
    actions.push(...page.items.filter(isOpenAction));
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  return sortOpenActions(actions);
}

export function submitActionEvidence(
  reportId: string,
  actionId: string,
  input: ActionSubmitInput,
  accessToken: string,
): Promise<ActionSubmitResult> {
  return apiFetch<ActionSubmitResult>(
    `/reports/${reportId}/actions/${actionId}/submit`,
    accessToken,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}
