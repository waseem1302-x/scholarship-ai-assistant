import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { ApiError, apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";

type DocumentKind = "cv_resume" | "statement_of_purpose" | "personal_statement" | "motivation_letter";
type Version = { id: string; version_number: number; status: string; scan_status: string; extraction_status: string | null; rejection_code: string | null; encryption_key_version: string; size_bytes: number; page_count: number | null };
type Asset = { id: string; document_kind: DocumentKind; display_name: string; retention_expires_at: string; versions: Version[] };
type Policy = { enabled: boolean; feature_enabled: boolean; accepting_uploads: boolean; scanner_ready: boolean; worker_ready: boolean; analysis_provider_ready: boolean; max_upload_bytes: number; max_pages: number; max_extracted_characters: number; retention_days: number; notice_version: string; data_use_notice: string };
type Feedback = { id: string; category: string; text: string; excerpt: string | null; rubric_category: string; confidence: string; is_general_suggestion: boolean };
type Analysis = { id: string; version_id: string; status: string; provider_status: string; summary: string | null; confidence: string | null; abstained_reason: string | null; rubric_version: string; feedback: Feedback[] };
type ApplicationDocument = { id: string; name: string };
type ApplicationList = { items: { id: string; opportunity: { name: string }; documents: ApplicationDocument[] }[] };

const labels: Record<DocumentKind, string> = {
  cv_resume: "CV / resume", statement_of_purpose: "Statement of purpose", personal_statement: "Personal statement", motivation_letter: "Motivation letter",
};

function statusText(value: string | null) { return (value || "pending").replaceAll("_", " "); }
function errorText(error: unknown) { return error instanceof Error ? error.message : "The private document request could not be completed."; }

export function DocumentLabPage() {
  const { user, isRestoring } = useAuth();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, Analysis[]>>({});
  const [applicationDocuments, setApplicationDocuments] = useState<ApplicationDocument[]>([]);
  const [applicationDocumentId, setApplicationDocumentId] = useState("");
  const [replacementFiles, setReplacementFiles] = useState<Record<string, File | null>>({});
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<DocumentKind>("cv_resume");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function load(signal?: AbortSignal) {
    try {
      const [nextPolicy, nextAssets, applications] = await Promise.all([
        apiClient.request<Policy>("/document-lab/policy", { signal }), apiClient.request<Asset[]>("/document-lab/assets", { signal }), apiClient.request<ApplicationList>("/applications", { signal }),
      ]);
      setPolicy(nextPolicy); setAssets(nextAssets);
      setApplicationDocuments(applications.items.flatMap((item) => item.documents));
      const histories = await Promise.all(nextAssets.flatMap((asset) => asset.versions.map(async (version) => [version.id, await apiClient.request<Analysis[]>(`/document-lab/versions/${version.id}/analyses`, { signal })] as const)));
      setAnalyses(Object.fromEntries(histories));
    } catch (error) { if (!signal?.aborted) setNotice(errorText(error)); }
  }
  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [user]);
  if (!isRestoring && !user) return <Navigate replace to="/auth" />;
  if (!user) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session…</main>;

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || !policy) return;
    if (file.size > policy.max_upload_bytes) { setNotice("This file exceeds the 10 MB upload limit."); return; }
    setBusy(true); setNotice(null);
    try {
      await apiClient.upload<Asset>(`/document-lab/assets?document_kind=${kind}`, file);
      setFile(null); setNotice("Upload is quarantined for safety scanning and private text extraction.");
      await load();
    } catch (error) { setNotice(errorText(error)); } finally { setBusy(false); }
  }
  async function analyse(asset: Asset, version: Version) {
    if (!policy || !consent) { setNotice("Confirm the data-use notice before sending extracted text for analysis."); return; }
    setBusy(true); setNotice(null);
    try {
      const result = await apiClient.request<Analysis>(`/document-lab/versions/${version.id}/analyses`, { method: "POST", body: JSON.stringify({ analysis_type: asset.document_kind, consent: true, notice_version: policy.notice_version }) });
      setAnalyses((current) => ({ ...current, [version.id]: [result, ...(current[version.id] || [])] }));
      setNotice("Analysis is queued. Refresh this page after the private worker completes it.");
    } catch (error) { setNotice(errorText(error)); } finally { setBusy(false); }
  }
  async function refreshAnalysis(version: Version) {
    try { const next = await apiClient.request<Analysis[]>(`/document-lab/versions/${version.id}/analyses`); setAnalyses((items) => ({ ...items, [version.id]: next })); } catch (error) { setNotice(errorText(error)); }
  }
  async function uploadVersion(asset: Asset) {
    const next = replacementFiles[asset.id]; if (!next) return;
    setBusy(true); setNotice(null);
    try { await apiClient.upload<Asset>(`/document-lab/assets/${asset.id}/versions`, next); setReplacementFiles((current) => ({ ...current, [asset.id]: null })); setNotice("Replacement version is quarantined for safety scanning and extraction."); await load(); } catch (error) { setNotice(errorText(error)); } finally { setBusy(false); }
  }
  async function link(applicationDocumentId: string, version: Version) {
    if (!applicationDocumentId) { setNotice("Choose an application document before linking a private version."); return; }
    if (!window.confirm("Link this private version to the selected application document? This does not change application status or submit anything.")) return;
    try { await apiClient.request(`/document-lab/application-documents/${applicationDocumentId}/link`, { method: "POST", body: JSON.stringify({ version_id: version.id, confirmed: true }) }); setNotice("Private version linked after your confirmation. No application status was changed."); } catch (error) { setNotice(errorText(error)); }
  }
  async function retry(version: Version) {
    setBusy(true); setNotice(null);
    try { await apiClient.request(`/document-lab/versions/${version.id}/retry`, { method: "POST" }); setNotice("Private safety preparation has been queued again."); await load(); } catch (error) { setNotice(errorText(error)); } finally { setBusy(false); }
  }
  async function remove(asset: Asset) {
    if (!window.confirm(`Permanently delete ${asset.display_name} and all of its private versions, extracted text, and feedback?`)) return;
    try { await apiClient.request(`/document-lab/assets/${asset.id}`, { method: "DELETE" }); setNotice("Private document data deleted."); await load(); } catch (error) { setNotice(errorText(error)); }
  }
  async function exportData() {
    try { const data = await apiClient.request<object>("/document-lab/export"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "document-lab-export.json"; anchor.click(); URL.revokeObjectURL(url); } catch (error) { setNotice(errorText(error)); }
  }

  return <main className="workspace-page page-width document-lab-page">
    <section className="workspace-intro"><p className="eyebrow">Private Document Lab</p><h1>Editorial feedback, under your control.</h1><p>Use CVs, resumes, statements of purpose, personal statements, and motivation letters only. Feedback is not an eligibility, admission, funding, visa, plagiarism, or authorship decision.</p></section>
    {!policy ? <p aria-live="polite">Loading private Document Lab settings…</p> : !policy.enabled ? <section className="assistant-warning" role="alert"><strong>Document Lab is unavailable</strong><p>This deployment has not enabled the private storage, scanner, and worker configuration.</p></section> : <>
      <section className="assistant-panel"><h2>Upload a private draft</h2><p>PDF or DOCX only · up to 10 MB · up to {policy.max_pages} pages · up to {policy.max_extracted_characters.toLocaleString()} extracted characters. Password-protected files, archives, macros, OCR/image-only files, and spreadsheets are not supported.</p>
        <form onSubmit={upload} className="assistant-form"><label htmlFor="document-kind">Document type</label><select id="document-kind" value={kind} onChange={(event) => setKind(event.target.value as DocumentKind)}>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><label htmlFor="document-file">Private PDF or DOCX</label><input id="document-file" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} required /><button className="button button-primary" disabled={busy}>{busy ? "Uploading…" : "Upload private draft"}</button></form>
        <label className="assistant-opt-in"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> I understand that, only after I request analysis, this version’s extracted text is sent to the configured AI provider. I can export or delete it, and feedback is editorial guidance only.</label><div><button type="button" onClick={exportData}>Export Document Lab data</button></div>{notice ? <p className="form-success" role="status">{notice}</p> : null}
      </section>
      <section aria-label="Private document versions"><h2>Private drafts</h2>{!assets.length ? <p>No private drafts yet.</p> : assets.map((asset) => <article className="assistant-answer" key={asset.id}><div className="assistant-answer-head"><div><p className="eyebrow">{labels[asset.document_kind]}</p><h3>{asset.display_name}</h3><p>Retention ends {new Date(asset.retention_expires_at).toLocaleDateString()}.</p></div><button className="button-danger" type="button" onClick={() => remove(asset)}>Delete</button></div><div className="assistant-section"><label>Upload a new immutable version<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setReplacementFiles((current) => ({ ...current, [asset.id]: event.target.files?.[0] ?? null }))} /></label><button type="button" disabled={busy || !replacementFiles[asset.id]} onClick={() => uploadVersion(asset)}>Upload new version</button></div>{asset.versions.map((version) => <div className="assistant-section" key={version.id}><h4>Version {version.version_number}</h4><p><strong>Status:</strong> {statusText(version.status)} · <strong>Safety scan:</strong> {statusText(version.scan_status)} · <strong>Extraction:</strong> {statusText(version.extraction_status)} · <strong>Key:</strong> {version.encryption_key_version}</p>{version.rejection_code ? <p role="alert">This version cannot continue: {statusText(version.rejection_code)}.</p> : null}{version.status === "failed" ? <button type="button" disabled={busy} onClick={() => retry(version)}>Retry private preparation</button> : null}{version.status === "ready" ? <div><button type="button" disabled={busy} onClick={() => analyse(asset, version)}>Request editorial feedback</button><button type="button" onClick={() => refreshAnalysis(version)}>Refresh analysis history</button>{applicationDocuments.length ? <div><label>Link to application document<select value={applicationDocumentId} onChange={(event) => setApplicationDocumentId(event.target.value)}><option value="">Select a private application document</option>{applicationDocuments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button type="button" onClick={() => link(applicationDocumentId, version)}>Confirm link</button></div> : <p>To link this version, first add a document coordination record in an application workspace.</p>}</div> : null}{analyses[version.id]?.map((analysis) => <FeedbackView analysis={analysis} key={analysis.id} />)}</div>)}</article>)}</section>
    </>}
  </main>;
}

function FeedbackView({ analysis }: { analysis: Analysis }) {
  const grouped = ["strength", "suggestion", "question", "warning"].map((category) => [category, analysis.feedback.filter((item) => item.category === category)] as const);
  return <section className="assistant-section" aria-live="polite"><h4>Editorial feedback</h4><p><strong>Status:</strong> {statusText(analysis.status)} · <strong>Provider:</strong> {statusText(analysis.provider_status)}</p>{analysis.summary ? <p>{analysis.summary}</p> : null}{analysis.abstained_reason ? <p role="alert">No feedback was shown: {statusText(analysis.abstained_reason)}.</p> : null}{grouped.map(([category, items]) => items.length ? <div key={category}><h5>{statusText(category)}s</h5><ul>{items.map((item) => <li key={item.id}>{item.text}<small> {statusText(item.rubric_category)} · {statusText(item.confidence)} confidence</small>{item.excerpt ? <blockquote>“{item.excerpt}”</blockquote> : <small> General suggestion</small>}</li>)}</ul></div> : null)}</section>;
}
