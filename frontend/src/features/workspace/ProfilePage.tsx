import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { draftFromProfile, getProfile, humanize, saveProfile } from "./workspace";
import { emptyProfileDraft, type ProfileDraft, type StudentProfile, type TestStatus } from "./types";

const testStatuses: TestStatus[] = ["unknown", "not_taken", "planned", "taken", "not_required"];

function Field({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return <label className={wide ? "wide" : ""}>{label}{children}</label>;
}

function Select({ value, onChange, children }: { value: string; onChange: (value: string) => void; children: ReactNode }) {
  return <select value={value} onChange={(event) => onChange(event.target.value)}>{children}</select>;
}

export function ProfilePage() {
  const { user, isRestoring } = useAuth();
  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [draft, setDraft] = useState<ProfileDraft>(emptyProfileDraft);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let active = true;
    void getProfile().then((response) => {
      if (active) { setProfile(response); setDraft(draftFromProfile(response)); }
    }).catch((requestError: unknown) => {
      if (active) setError(requestError instanceof Error ? requestError.message : "Unable to load your profile.");
    }).finally(() => { if (active) setIsLoading(false); });
    return () => { active = false; };
  }, [user]);

  if (isRestoring) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user?.role !== "student") return <main className="page-width placeholder-page"><h1>Profiles are available to student accounts.</h1><p className="lead">Administrator curation is kept separate from student decision tools.</p></main>;

  function update(key: keyof ProfileDraft, value: string) { setDraft((current) => ({ ...current, [key]: value })); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setIsSaving(true); setMessage(null); setError(null);
    try { const saved = await saveProfile(draft); setProfile(saved); setDraft(draftFromProfile(saved)); setMessage("Profile saved. Your match explanations now use this information."); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to save your profile."); }
    finally { setIsSaving(false); }
  }

  return <main className="workspace-tool page-width" aria-busy={isLoading}>
    <section className="tool-header"><div><p className="eyebrow">Student profile</p><h1>Build a profile you can trust.</h1><p className="lead">Only add information you are comfortable using for decision support. Missing information is kept as unknown, never guessed.</p></div>
      <aside className="completeness-card"><strong>{profile ? `${profile.profile_completeness}% complete` : "Not started"}</strong><p>{profile?.missing_recommended_fields.length ? `Still useful to add: ${profile.missing_recommended_fields.map(humanize).join(", ")}.` : "Add your study goals and evidence to receive clearer explanations."}</p></aside></section>
    {isLoading ? <div className="catalogue-message">Loading your profile...</div> : null}
    {!isLoading ? <form className="profile-editor" onSubmit={submit}>
      <fieldset><legend>Background and goals</legend><div className="form-grid">
        <Field label="Nationality"><input value={draft.nationality} onChange={(e) => update("nationality", e.target.value)} placeholder="Pakistan" /></Field>
        <Field label="Country of residence"><input value={draft.country_of_residence} onChange={(e) => update("country_of_residence", e.target.value)} placeholder="Malaysia" /></Field>
        <Field label="Current education"><Select value={draft.current_education_level} onChange={(v) => update("current_education_level", v)}><option value="">Unknown</option>{["high_school", "diploma", "bachelors", "masters", "phd", "other"].map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</Select></Field>
        <Field label="Target degree"><Select value={draft.target_degree_level} onChange={(v) => update("target_degree_level", v)}><option value="">Unknown</option>{["bachelors", "masters", "phd", "short_course", "other"].map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</Select></Field>
        <Field label="Intended field"><input value={draft.intended_field} onChange={(e) => update("intended_field", e.target.value)} placeholder="Artificial Intelligence" /></Field>
        <Field label="Academic discipline"><input value={draft.academic_discipline} onChange={(e) => update("academic_discipline", e.target.value)} placeholder="Computer Science" /></Field>
        <Field label="Preferred study mode"><Select value={draft.preferred_study_mode} onChange={(v) => update("preferred_study_mode", v)}><option value="">No preference</option>{["on_campus", "online", "hybrid", "any"].map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</Select></Field>
        <Field label="Target intake"><input value={draft.target_intake} onChange={(e) => update("target_intake", e.target.value)} placeholder="Fall 2027" /></Field>
        <Field label="Preferred destinations" wide><input value={draft.preferred_destination_countries} onChange={(e) => update("preferred_destination_countries", e.target.value)} placeholder="Malaysia, Germany, Canada" /><small>Separate countries with commas.</small></Field>
      </div></fieldset>
      <fieldset><legend>Academic record and tests</legend><div className="form-grid">
        <Field label="CGPA"><input inputMode="decimal" value={draft.cgpa} onChange={(e) => update("cgpa", e.target.value)} placeholder="3.75" /></Field>
        <Field label="CGPA scale"><input inputMode="decimal" value={draft.grading_scale} onChange={(e) => update("grading_scale", e.target.value)} placeholder="4.00" /></Field>
        <Field label="Percentage"><input inputMode="decimal" value={draft.percentage} onChange={(e) => update("percentage", e.target.value)} placeholder="87" /></Field>
        <Field label="Work experience (months)"><input inputMode="numeric" value={draft.work_experience_months} onChange={(e) => update("work_experience_months", e.target.value)} placeholder="12" /></Field>
        <Field label="English test status"><Select value={draft.english_test_status} onChange={(v) => update("english_test_status", v)}>{testStatuses.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</Select></Field>
        <Field label="IELTS score"><input disabled={draft.english_test_status !== "taken"} inputMode="decimal" value={draft.ielts_score} onChange={(e) => update("ielts_score", e.target.value)} placeholder="7.0" /></Field>
        <Field label="TOEFL score"><input disabled={draft.english_test_status !== "taken"} inputMode="numeric" value={draft.toefl_score} onChange={(e) => update("toefl_score", e.target.value)} placeholder="100" /></Field>
        <Field label="Duolingo score"><input disabled={draft.english_test_status !== "taken"} inputMode="numeric" value={draft.duolingo_score} onChange={(e) => update("duolingo_score", e.target.value)} placeholder="125" /></Field>
        <Field label="GRE status"><Select value={draft.gre_status} onChange={(v) => update("gre_status", v)}>{testStatuses.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</Select></Field>
        <Field label="GRE score"><input disabled={draft.gre_status !== "taken"} inputMode="numeric" value={draft.gre_score} onChange={(e) => update("gre_score", e.target.value)} placeholder="320" /></Field>
      </div></fieldset>
      <fieldset><legend>Context that can improve explanations</legend><div className="form-grid">
        <Field label="Research experience" wide><textarea rows={3} value={draft.research_experience} onChange={(e) => update("research_experience", e.target.value)} /></Field>
        <Field label="Publications" wide><input value={draft.publications} onChange={(e) => update("publications", e.target.value)} placeholder="Title one, title two" /><small>Separate items with commas.</small></Field>
        <Field label="Leadership experience" wide><textarea rows={3} value={draft.leadership_experience} onChange={(e) => update("leadership_experience", e.target.value)} /></Field>
        <Field label="Financial need" wide><textarea rows={2} value={draft.financial_need} onChange={(e) => update("financial_need", e.target.value)} /></Field>
        <Field label="Application constraints" wide><textarea rows={2} value={draft.application_constraints} onChange={(e) => update("application_constraints", e.target.value)} /></Field>
        <Field label="Additional eligibility information" wide><textarea rows={2} value={draft.additional_eligibility_information} onChange={(e) => update("additional_eligibility_information", e.target.value)} /></Field>
      </div></fieldset>
      {error ? <p className="form-error" role="alert">{error}</p> : null}{message ? <p className="form-success" role="status">{message}</p> : null}
      <button className="button button-primary" type="submit" disabled={isSaving}>{isSaving ? "Saving profile..." : "Save profile"}</button>
    </form> : null}
  </main>;
}
