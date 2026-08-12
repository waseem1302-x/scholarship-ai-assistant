import { apiClient } from "../../api/client";

import type {
  DataQualityResponse,
  ImportResponse,
  ReviewAction,
  ReviewQueueResponse,
} from "./types";

export const reviewActions: { value: ReviewAction; label: string; needsNotes: boolean }[] = [
  { value: "publish", label: "Publish", needsNotes: false },
  { value: "hold_for_review", label: "Hold for review", needsNotes: true },
  { value: "flag_conflict", label: "Flag conflict", needsNotes: true },
  { value: "request_recheck", label: "Request recheck", needsNotes: true },
  { value: "resolve_conflict", label: "Resolve conflict", needsNotes: true },
  { value: "expire", label: "Expire", needsNotes: true },
  { value: "archive", label: "Archive", needsNotes: true },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function jsonImportRows(input: string): Record<string, unknown>[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(input);
  } catch {
    throw new Error("Enter valid JSON before importing.");
  }
  const rows = Array.isArray(parsed) ? parsed : isRecord(parsed) ? parsed.rows : undefined;
  if (!Array.isArray(rows) || !rows.every(isRecord)) {
    throw new Error("JSON imports must be an array of opportunity rows or an object with a rows array.");
  }
  if (!rows.length) {
    throw new Error("Add at least one opportunity row before importing.");
  }
  return rows;
}

export async function getAdminWorkspace(): Promise<[ReviewQueueResponse, DataQualityResponse]> {
  return Promise.all([
    apiClient.request<ReviewQueueResponse>("/admin/review-queue?limit=50&offset=0"),
    apiClient.request<DataQualityResponse>("/admin/data-quality-issues?limit=50&offset=0"),
  ]);
}

async function adminMutation<T>(path: string, body: object, password: string): Promise<T> {
  if (!password) {
    throw new Error("Enter your administrator password to confirm this action.");
  }
  const stepUp = await apiClient.adminStepUp(password);
  return apiClient.request<T>(path, {
    method: "POST",
    headers: { "X-Admin-Step-Up": stepUp.step_up_token },
    body: JSON.stringify(body),
  });
}

export async function applyReviewAction(
  opportunityId: string,
  action: ReviewAction,
  sourceId: string,
  notes: string,
  password: string,
): Promise<void> {
  await adminMutation(`/admin/opportunities/${opportunityId}/review-actions`, {
    action,
    source_id: sourceId,
    notes: notes.trim() || null,
  }, password);
}

export async function importOpportunities(
  sourceFormat: "json" | "csv",
  content: string,
  dryRun: boolean,
  password: string,
): Promise<ImportResponse> {
  const body = sourceFormat === "json"
    ? { source_format: sourceFormat, dry_run: dryRun, rows: jsonImportRows(content) }
    : { source_format: sourceFormat, dry_run: dryRun, csv_content: content.trim() };
  if (sourceFormat === "csv" && !content.trim()) {
    throw new Error("Paste CSV content before importing.");
  }
  return adminMutation<ImportResponse>("/admin/opportunities/import", body, password);
}
