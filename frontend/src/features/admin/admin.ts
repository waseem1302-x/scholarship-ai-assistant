import { apiClient } from "../../api/client";

import type {
  DataQualityResponse,
  DuplicateSuggestion,
  DuplicateSuggestionResponse,
  AdminOpportunityFilters,
  AdminOpportunitySearchResponse,
  ImportResponse,
  ReviewAction,
  ReviewQueueResponse,
  IngestionCandidateResponse,
  IngestionRun,
  OpportunityGraph,
  ReviewQueueItem,
  AcquiredCandidateReview,
  AdminOpportunityFamily,
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

export type ImportFormat = "json" | "csv";

const templateRow = {
  name: "Replace with opportunity name",
  provider_name: "Replace with provider name",
  country: "Malaysia",
  degree_level: "masters",
  funding_type: "full",
  tuition_coverage: "Replace with official funding evidence",
  application_deadline: "2027-12-31T23:59:59Z",
  required_documents: ["Transcript", "Passport"],
  english_language_requirement: "Replace with official requirement",
  minimum_academic_requirement: "Replace with official requirement",
  source: {
    url: "https://example.edu/official-scholarship",
    title: "Replace with official source title",
    relevant_excerpt: "Replace this with an official excerpt of at least twenty words that supports the scholarship details.",
  },
};

export const importTemplates: Record<ImportFormat, string> = {
  json: `${JSON.stringify([templateRow], null, 2)}\n`,
  csv: [
    "name,provider_name,country,degree_level,funding_type,tuition_coverage,application_deadline,required_documents,english_language_requirement,minimum_academic_requirement,source_url,source_title,source_relevant_excerpt",
    'Replace with opportunity name,Replace with provider name,Malaysia,masters,full,Replace with official funding evidence,2027-12-31T23:59:59Z,"Transcript;Passport",Replace with official requirement,Replace with official requirement,https://example.edu/official-scholarship,Replace with official source title,"Replace this with an official excerpt of at least twenty words that supports the scholarship details."',
    "",
  ].join("\n"),
};

export function importFormatForFile(filename: string): ImportFormat | null {
  const normalized = filename.trim().toLowerCase();
  if (normalized.endsWith(".json")) return "json";
  if (normalized.endsWith(".csv")) return "csv";
  return null;
}

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

export interface AdminWorkspacePage {
  queueOffset?: number;
  issueOffset?: number;
}

export async function getAdminWorkspace({
  queueOffset = 0,
  issueOffset = 0,
}: AdminWorkspacePage = {}, signal?: AbortSignal): Promise<[ReviewQueueResponse, DataQualityResponse]> {
  return Promise.all([
    apiClient.request<ReviewQueueResponse>(`/admin/review-queue?limit=100&offset=${queueOffset}`, { signal }),
    apiClient.request<DataQualityResponse>(`/admin/data-quality-issues?limit=20&offset=${issueOffset}`, { signal }),
  ]);
}

export function adminOpportunitySearch(filters: AdminOpportunityFilters, offset = 0): URLSearchParams {
  const params = new URLSearchParams({ limit: "20", offset: String(offset) });
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  return params;
}

export async function getAdminOpportunities(filters: AdminOpportunityFilters, offset = 0, signal?: AbortSignal): Promise<AdminOpportunitySearchResponse> {
  return apiClient.request<AdminOpportunitySearchResponse>(`/admin/opportunities?${adminOpportunitySearch(filters, offset)}`, { signal });
}

export async function getAdminCatalogueRecords(signal?: AbortSignal): Promise<AdminOpportunitySearchResponse> {
  return apiClient.request<AdminOpportunitySearchResponse>("/admin/opportunities?limit=100&offset=0", { signal });
}

export async function getDuplicateSuggestions(signal?: AbortSignal): Promise<DuplicateSuggestionResponse> {
  return apiClient.request<DuplicateSuggestionResponse>(
    "/admin/duplicate-suggestions?limit=100&offset=0",
    { signal },
  );
}

export async function getReviewQueueItem(opportunityId: string, signal?: AbortSignal): Promise<ReviewQueueItem> {
  return apiClient.request<ReviewQueueItem>(`/admin/review-queue/${encodeURIComponent(opportunityId)}`, { signal });
}

export async function getAdminOpportunityFamily(opportunityId: string, signal?: AbortSignal): Promise<AdminOpportunityFamily> {
  return apiClient.request<AdminOpportunityFamily>(
    `/admin/opportunities/${encodeURIComponent(opportunityId)}/family`,
    { signal },
  );
}

export async function getAcquiredCandidates(signal?: AbortSignal): Promise<IngestionCandidateResponse> {
  return apiClient.request<IngestionCandidateResponse>(
    "/admin/catalogue-ingestion/candidates?limit=100&offset=0",
    { signal },
  );
}

export async function getAcquiredCandidateReview(candidateId: string, signal?: AbortSignal): Promise<AcquiredCandidateReview> {
  const encodedId = encodeURIComponent(candidateId);
  const [candidate, projection] = await Promise.all([
    apiClient.request<AcquiredCandidateReview["candidate"]>(`/admin/catalogue-ingestion/candidates/${encodedId}`, { signal }),
    apiClient.request<AcquiredCandidateReview["projection"]>(`/admin/catalogue-ingestion/candidates/${encodedId}/review-projection`, { signal }),
  ]);
  return { candidate, projection };
}

async function adminMutation<T>(
  path: string,
  body: object,
  password: string,
  method: "POST" | "PATCH" = "POST",
): Promise<T> {
  if (!password) {
    throw new Error("Enter your administrator password to confirm this action.");
  }
  const stepUp = await apiClient.adminStepUp(password);
  return apiClient.request<T>(path, {
    method,
    headers: { "X-Admin-Step-Up": stepUp.step_up_token },
    body: JSON.stringify(body),
  });
}

export async function recordSourceCheck(
  sourceId: string,
  contentHash: string,
  changeSummary: string,
  password: string,
): Promise<void> {
  await adminMutation(`/admin/sources/${sourceId}/checks`, {
    content_hash: contentHash.trim() || null,
    change_summary: changeSummary.trim() || null,
  }, password);
}

export async function reverifySource(
  opportunityId: string,
  sourceId: string,
  notes: string,
  password: string,
): Promise<void> {
  await adminMutation(`/admin/opportunities/${opportunityId}/verification`, {
    source_id: sourceId,
    verification_status: "officially_verified",
    notes: notes.trim() || null,
  }, password, "PATCH");
}

export async function reviewDuplicateSuggestion(
  suggestionId: string,
  isDuplicate: boolean,
  password: string,
): Promise<DuplicateSuggestion> {
  return adminMutation<DuplicateSuggestion>(
    `/admin/duplicate-suggestions/${encodeURIComponent(suggestionId)}/decision`,
    { is_duplicate: isDuplicate },
    password,
  );
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
  sourceFormat: ImportFormat,
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

export async function acquireOfficialUrl(
  url: string,
  targetName: string,
  password: string,
  supportingUrls: string[] = [],
  university = "",
): Promise<{ run: IngestionRun; candidate: IngestionCandidateResponse["items"][number] | null; graph: OpportunityGraph | null }> {
  const run = await adminMutation<IngestionRun>("/admin/catalogue-ingestion/runs/url", {
    url,
    supporting_urls: supportingUrls,
    target_name: targetName.trim() || null,
    university: university.trim() || null,
    mode: "candidate_only",
    dry_run: true,
    process_now: false,
  }, password);
  const candidates = await apiClient.request<IngestionCandidateResponse>(
    `/admin/catalogue-ingestion/candidates?run_id=${encodeURIComponent(run.id)}&limit=1&offset=0`,
  );
  const candidate = candidates.items[0] ?? null;
  return { run, candidate, graph: null };
}
