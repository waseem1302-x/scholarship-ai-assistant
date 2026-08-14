import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { ApiError, apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";

type Citation = {
  id: string;
  source_title: string;
  source_url: string;
  excerpt: string;
  last_verified_at: string | null;
  freshness: string;
};
type ProgressItem = { opportunity_id: string; name: string; lifecycle: string; outstanding_tasks: number };
type ResponseBody = {
  answer: string;
  answer_type: string;
  confidence: string;
  facts: { text: string; citation_ids: string[] }[];
  possible_matches: { opportunity_id: string; name: string; reason: string; citation_ids: string[] }[];
  requirements_to_check: { text: string; citation_ids: string[] }[];
  private_progress: ProgressItem[];
  next_actions: string[];
  warnings: string[];
  citations: Citation[];
  abstained_reason: string | null;
};
type Answer = {
  id: string;
  conversation_id: string;
  status: "completed" | "abstained" | "blocked" | "failed";
  saved_to_workspace: boolean;
  response: ResponseBody;
};
type Preferences = {
  consented: boolean;
  history_enabled: boolean;
  history_retention_days: number;
  feedback_retention_days: number;
};
type Conversation = { id: string; title: string | null; created_at: string };
type ConversationDetail = Conversation & { answers: Answer[] };

const suggestions = [
  "Find master's scholarships in Malaysia",
  "What funding is listed for computer science scholarships?",
  "Which requirements should I confirm before applying?",
  "Show my application progress",
];

function assistantErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "The assistant is unavailable. Please try again.";
  if (error.status === 429) return "The assistant is rate-limited. Please wait a minute and try again.";
  if (error.status === 503) return "The answer provider is unavailable. Your question was not answered from unverified data.";
  return error.message;
}

function CitationRefs({ ids, citations }: { ids: string[]; citations: Citation[] }) {
  if (!ids.length) return null;
  return <span className="citation-refs">{ids.map((id) => {
    const index = citations.findIndex((citation) => citation.id === id);
    const citation = citations[index];
    return citation ? <a key={id} href={citation.source_url} target="_blank" rel="noreferrer">[{index + 1}]</a> : <span key={id}>[?]</span>;
  })}</span>;
}

export function AssistantPage() {
  const { user, isRestoring } = useAuth();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [useProfile, setUseProfile] = useState(false);
  const [useApplicationData, setUseApplicationData] = useState(false);

  useEffect(() => {
    if (user) {
      const controller = new AbortController();
      void loadPreferences(controller.signal);
      void loadConversations(controller.signal);
      return () => controller.abort();
    }
  }, [user]);

  if (!isRestoring && !user) return <Navigate replace to="/auth" />;
  if (!user) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session…</main>;

  async function loadPreferences(signal?: AbortSignal) {
    setPreferences(await apiClient.request<Preferences>("/assistant/preferences", { signal }));
  }
  async function loadConversations(signal?: AbortSignal) {
    setConversations(await apiClient.request<Conversation[]>("/assistant/conversations", { signal }));
  }
  async function consent() {
    const value = await apiClient.request<Preferences>("/assistant/preferences", {
      method: "PUT",
      body: JSON.stringify({ consent: true }),
    });
    setPreferences(value);
    setNotice("Assistant data-use notice accepted.");
  }
  async function toggleHistory() {
    if (!preferences) return;
    const value = await apiClient.request<Preferences>("/assistant/preferences", {
      method: "PUT",
      body: JSON.stringify({ history_enabled: !preferences.history_enabled }),
    });
    setPreferences(value);
    await loadConversations();
  }
  async function deleteConversation(id: string) {
    await apiClient.request(`/assistant/conversations/${id}`, { method: "DELETE" });
    if (answer?.conversation_id === id) setAnswer(null);
    await loadConversations();
  }
  async function openConversation(id: string) {
    const detail = await apiClient.request<ConversationDetail>(`/assistant/conversations/${id}`);
    setAnswer(detail.answers.at(-1) ?? null);
    setNotice("Conversation loaded.");
  }
  async function exportData() {
    const data = await apiClient.request<object>("/assistant/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "assistant-data-export.json";
    link.click();
    URL.revokeObjectURL(url);
  }
  async function deleteAllData() {
    if (!window.confirm("Permanently delete all assistant conversations, saved answers, and feedback?")) return;
    await apiClient.request("/assistant/data", { method: "DELETE" });
    setAnswer(null);
    setConversations([]);
    setNotice("Assistant data deleted.");
  }
  async function ask(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim() || !preferences?.consented) return;
    setLoading(true);
    setNotice(null);
    try {
      const result = await apiClient.request<Answer>("/assistant/answers", {
        method: "POST",
        body: JSON.stringify({ question, use_profile: useProfile, use_application_data: useApplicationData }),
      });
      setAnswer(result);
      if (result.status === "failed") {
        setNotice("The provider is unavailable. No unsupported answer was generated.");
      }
      await loadConversations();
    } catch (error) {
      setNotice(assistantErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }
  async function save() {
    if (!answer) return;
    try {
      await apiClient.request(`/assistant/answers/${answer.id}/save`, { method: "POST" });
      setAnswer({ ...answer, saved_to_workspace: true });
      setNotice("Saved privately to your workspace.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not save this answer.");
    }
  }
  async function startApplication(opportunityId: string, name: string) {
    if (!window.confirm(`Create a private application plan for ${name}?`)) return;
    try {
      await apiClient.request("/applications", {
        method: "POST",
        body: JSON.stringify({ opportunity_id: opportunityId }),
      });
      setNotice(`Created a private application plan for ${name}.`);
    } catch (error) {
      setNotice(error instanceof ApiError && error.status === 409 ? "An application plan already exists." : assistantErrorMessage(error));
    }
  }
  async function feedback(feedback_type: string) {
    if (!answer) return;
    await apiClient.request(`/assistant/answers/${answer.id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback_type }),
    });
    setNotice("Thanks—your feedback was recorded.");
  }

  return <main className="assistant-page page-width">
    <section className="assistant-intro">
      <p className="eyebrow">Private citation-first assistant</p>
      <h1>Research scholarships with evidence in view.</h1>
      <p>Answers use the catalogue’s verified official sources. Always confirm requirements, deadlines, funding, and eligibility directly with the provider.</p>
    </section>
    <section className="assistant-panel">
      {!preferences ? <p>Loading privacy settings…</p> : !preferences.consented ? <div className="assistant-warning" role="alert">
        <strong>Data-use notice</strong>
        <p>The assistant uses your question and, only when selected, your profile or application workspace to search verified catalogue sources. Chat history is retained for {preferences.history_retention_days} days; feedback for {preferences.feedback_retention_days} days. It never reads documents, notes, or another student’s data.</p>
        <button className="button button-primary" type="button" onClick={consent}>I understand and agree</button>
      </div> : <div className="assistant-settings">
        <span>History: {preferences.history_enabled ? "enabled" : "disabled"}</span>
        <button type="button" onClick={toggleHistory}>{preferences.history_enabled ? "Disable assistant history" : "Enable assistant history"}</button>
        <button type="button" onClick={exportData}>Export assistant data</button>
        <button type="button" className="button-danger" onClick={deleteAllData}>Delete assistant data</button>
      </div>}
      <form onSubmit={ask} className="assistant-form">
        <label htmlFor="assistant-question">Ask about scholarships, requirements, funding, deadlines, or your progress</label>
        <textarea id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={4000} required placeholder="For example: Find master's scholarships in Malaysia" />
        <label className="assistant-opt-in"><input type="checkbox" checked={useProfile} onChange={(event) => setUseProfile(event.target.checked)} /> Use my profile for this question</label>
        <label className="assistant-opt-in"><input type="checkbox" checked={useApplicationData} onChange={(event) => setUseApplicationData(event.target.checked)} /> Use my private application workspace for progress or priority questions</label>
        <div><button className="button button-primary" disabled={loading || !preferences?.consented}>{loading ? "Checking verified sources…" : "Ask assistant"}</button></div>
      </form>
      <div className="assistant-suggestions" aria-label="Supported question suggestions">{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setQuestion(suggestion)}>{suggestion}</button>)}</div>
      {notice ? <p className="form-success" role="status">{notice}</p> : null}
    </section>
    {conversations.length ? <section className="assistant-conversations" aria-label="Assistant conversations">
      <h2>Conversation history</h2><ul>{conversations.map((conversation) => <li key={conversation.id}>
        <button type="button" className="assistant-conversation-open" onClick={() => openConversation(conversation.id)}>{conversation.title || `Conversation from ${new Date(conversation.created_at).toLocaleDateString()}`}</button>
        <button type="button" onClick={() => deleteConversation(conversation.id)} aria-label="Delete conversation">Delete</button>
      </li>)}</ul>
    </section> : null}
    {answer ? <section className="assistant-answer" aria-live="polite">
      <div className="assistant-answer-head"><div><p className="eyebrow">{answer.status === "completed" ? "Source-backed response" : "Transparent uncertainty"}</p><h2>{answer.response.answer}</h2><p>Evidence confidence: {answer.response.confidence}</p></div>{answer.status === "completed" ? <button className="button button-quiet" type="button" onClick={save} disabled={answer.saved_to_workspace}>{answer.saved_to_workspace ? "Saved" : "Save result"}</button> : null}</div>
      {answer.response.warnings.length ? <div className="assistant-warning" role="alert"><strong>Check before acting</strong><ul>{answer.response.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div> : null}
      {answer.response.facts.length ? <div className="assistant-section"><h3>Verified facts</h3><ul>{answer.response.facts.map((fact) => <li key={fact.text}>{fact.text} <CitationRefs ids={fact.citation_ids} citations={answer.response.citations} /></li>)}</ul></div> : null}
      {answer.response.possible_matches.length ? <div className="assistant-section"><h3>Possible matches</h3>{answer.response.possible_matches.map((match) => <article key={match.opportunity_id}><Link to={`/catalogue/${match.opportunity_id}`}>{match.name}</Link><p>{match.reason} <CitationRefs ids={match.citation_ids} citations={answer.response.citations} /></p><button type="button" onClick={() => startApplication(match.opportunity_id, match.name)}>Create application plan</button></article>)}</div> : null}
      {answer.response.requirements_to_check.length ? <div className="assistant-section"><h3>Requirements to confirm</h3><ul>{answer.response.requirements_to_check.map((item) => <li key={item.text}>{item.text} <CitationRefs ids={item.citation_ids} citations={answer.response.citations} /></li>)}</ul></div> : null}
      {answer.response.private_progress.length ? <div className="assistant-section"><h3>Private application progress</h3><ul>{answer.response.private_progress.map((item) => <li key={item.opportunity_id}><strong>{item.name}</strong>: {item.lifecycle}; {item.outstanding_tasks} outstanding task(s).</li>)}</ul></div> : null}
      {answer.response.next_actions.length ? <div className="assistant-section"><h3>Suggested next steps</h3><ol>{answer.response.next_actions.map((item) => <li key={item}>{item}</li>)}</ol></div> : null}
      {answer.response.citations.length ? <div className="assistant-section"><h3>Official citations</h3>{answer.response.citations.map((citation) => <article className="assistant-citation" key={citation.id}><div><strong>{citation.source_title}</strong><p>{citation.excerpt}</p><small>{citation.freshness} {citation.last_verified_at ? `· verified ${new Date(citation.last_verified_at).toLocaleDateString()}` : ""}</small></div><a className="button button-quiet" href={citation.source_url} target="_blank" rel="noreferrer" aria-label={`Open official source: ${citation.source_title}`}>Open source</a></article>)}</div> : null}
      <footer className="assistant-feedback"><span>Was this response useful?</span>{["helpful", "not_helpful", "incorrect", "outdated", "missing_citation"].map((kind) => <button type="button" key={kind} onClick={() => feedback(kind)}>{kind.replaceAll("_", " ")}</button>)}</footer>
    </section> : null}
  </main>;
}
