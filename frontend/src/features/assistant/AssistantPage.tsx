import { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

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

const scholarshipTools = [
  { id: "advisor", icon: "💬", label: "General Advisor", defaultPrompt: "" },
  { id: "auditor", icon: "🎯", label: "Eligibility Auditor", defaultPrompt: "Evaluate my GPA, nationality, and degree level eligibility for " },
  { id: "essay", icon: "✍️", label: "Essay & SOP Lab", defaultPrompt: "Help me outline a 500-word leadership essay using the STAR framework for " },
  { id: "documents", icon: "📁", label: "Document Reviewer", defaultPrompt: "What specific academic transcripts and documents are required for " },
  { id: "interview", icon: "🎙️", label: "Interview Coach", defaultPrompt: "Simulate top 5 interview questions and model answers for " },
];

function assistantErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "The assistant is unavailable. Please try again.";
  if (error.status === 429) return "The assistant is rate-limited. Please wait a minute and try again.";
  if (error.status === 503) return "The answer provider is unavailable. Your question was not answered from unverified data.";
  return error.message;
}

function CitationRefs({ ids, citations }: { ids: string[]; citations: Citation[] }) {
  if (!ids.length) return null;
  return (
    <span className="citation-refs">
      {ids.map((id) => {
        const index = citations.findIndex((citation) => citation.id === id);
        const citation = citations[index];
        return citation ? (
          <a key={id} href={citation.source_url} target="_blank" rel="noreferrer">
            [{index + 1}]
          </a>
        ) : (
          <span key={id}>[?]</span>
        );
      })}
    </span>
  );
}

export function AssistantPage() {
  const { user, isRestoring } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [useProfile, setUseProfile] = useState(false);
  const [useApplicationData, setUseApplicationData] = useState(false);
  const [activeTool, setActiveTool] = useState("advisor");
  const [activeFocus, setActiveFocus] = useState<string | null>(searchParams.get("opportunity"));
  const [searchFilter, setSearchFilter] = useState("");

  useEffect(() => {
    const initialPrompt = searchParams.get("prompt");
    if (initialPrompt) {
      setQuestion(initialPrompt);
    }
  }, [searchParams]);

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
      const fullQuestion = activeFocus ? `[Regarding ${activeFocus}]: ${question}` : question;
      const result = await apiClient.request<Answer>("/assistant/answers", {
        method: "POST",
        body: JSON.stringify({ question: fullQuestion, use_profile: useProfile, use_application_data: useApplicationData }),
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

  function handleToolClick(toolId: string, defaultPrompt: string) {
    setActiveTool(toolId);
    if (defaultPrompt) {
      setQuestion(defaultPrompt + (activeFocus ? ` ${activeFocus}` : ""));
    }
  }

  const filteredConversations = conversations.filter((c) =>
    searchFilter ? (c.title || "").toLowerCase().includes(searchFilter.toLowerCase()) : true,
  );

  return (
    <div className="copilot-page-wrapper">
      <div className="copilot-app-window">
        
        {/* 1. LEFT NAVIGATION SIDEBAR */}
        <aside className="copilot-sidebar">
          <div className="sidebar-top-section">
            
            {/* Branding */}
            <div className="copilot-brand-row">
              <div className="copilot-brand-badge">
                <div className="copilot-brand-logo">S/</div>
                <div>
                  <span className="copilot-brand-name">Scholarship AI</span>
                  <span className="copilot-brand-tag">Official RAG Copilot</span>
                </div>
              </div>
              <button
                className="copilot-new-chat-btn"
                type="button"
                onClick={() => {
                  setAnswer(null);
                  setQuestion("");
                  setActiveFocus(null);
                  setSearchParams({});
                }}
                title="New Scholarship Session"
              >
                ✏️
              </button>
            </div>

            {/* Search Input */}
            <div className="copilot-search-box">
              <span className="search-icon">🔍</span>
              <input
                type="text"
                placeholder="Search sessions..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="copilot-search-input"
              />
            </div>

            {/* Scholarship Tools Nav */}
            <nav className="copilot-tools-nav">
              <span className="nav-group-title">Scholarship Tools</span>
              {scholarshipTools.map((tool) => (
                <button
                  key={tool.id}
                  type="button"
                  onClick={() => handleToolClick(tool.id, tool.defaultPrompt)}
                  className={`copilot-tool-btn ${activeTool === tool.id ? "active" : ""}`}
                >
                  <span className="tool-btn-icon">{tool.icon}</span>
                  <span className="tool-btn-label">{tool.label}</span>
                  {activeTool === tool.id ? <span className="active-dot" /> : null}
                </button>
              ))}
            </nav>

            {/* Conversations History */}
            {filteredConversations.length ? (
              <div className="copilot-history-group">
                <span className="nav-group-title">Recent Inquiries</span>
                <div className="history-list">
                  {filteredConversations.map((conversation) => (
                    <div key={conversation.id} className="history-item-row">
                      <button
                        type="button"
                        className="history-open-btn"
                        onClick={() => openConversation(conversation.id)}
                      >
                        {conversation.title || `Inquiry from ${new Date(conversation.created_at).toLocaleDateString()}`}
                      </button>
                      <button
                        type="button"
                        className="history-delete-btn"
                        onClick={() => deleteConversation(conversation.id)}
                        title="Delete inquiry"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

          </div>

          {/* Student Profile Footer */}
          <div className="copilot-user-footer">
            <div className="user-profile-summary">
              <div className="user-avatar-pill">{user.email.slice(0, 2).toUpperCase()}</div>
              <div className="user-text-meta">
                <span className="user-display-email">{user.email}</span>
                <span className="user-role-badge">Student Profile</span>
              </div>
            </div>
            <Link className="profile-link-btn" to="/profile">
              Profile ➔
            </Link>
          </div>
        </aside>

        {/* 2. RIGHT MAIN WORKSPACE */}
        <main className="copilot-main-workspace">
          
          {/* Top Control Bar */}
          <div className="copilot-top-bar">
            {activeFocus ? (
              <div className="copilot-focus-ribbon">
                <span className="focus-label">Focus Context:</span>
                <span className="focus-tag">
                  <span>🎓</span> {activeFocus}
                  <button
                    type="button"
                    className="focus-remove-btn"
                    onClick={() => {
                      setActiveFocus(null);
                      setSearchParams({});
                    }}
                  >
                    ×
                  </button>
                </span>
              </div>
            ) : (
              <span className="copilot-session-status">Scholarship Assistant · Evidence-First</span>
            )}

            <div className="top-bar-right-controls">
              <div className="source-scope-toggle">
                <button type="button" className="scope-btn active">
                  ✓ Verified Government RAG
                </button>
                <button type="button" className="scope-btn">
                  🌐 Global Edu Web
                </button>
              </div>
            </div>
          </div>

          {/* Privacy Notice Banner if not consented */}
          {!preferences?.consented ? (
            <div className="assistant-warning copilot-consent-banner" role="alert">
              <strong>Data-use notice</strong>
              <p>
                The assistant uses your question and, only when selected, your profile or application workspace to search verified scholarship sources. Chat history is retained for {preferences?.history_retention_days ?? 30} days. It never reads documents, notes, or another student’s data.
              </p>
              <button className="button button-primary" type="button" onClick={consent}>
                I understand and agree
              </button>
            </div>
          ) : null}

          {/* Content Area: Empty State Hero or Active Answer */}
          <div className="copilot-content-area">
            {!answer ? (
              <div className="copilot-hero-empty-state">
                <div className="hero-greeting-stack">
                  <h1 className="hero-heading">
                    Hi, what scholarship are we preparing today?
                  </h1>
                  <p className="hero-subheading">
                    Connected to your student profile credentials and 450+ verified official awards.
                  </p>
                </div>

                {/* 3 Quick-Starter Action Cards */}
                <div className="copilot-action-cards-grid">
                  <div
                    className="copilot-starter-card"
                    onClick={() =>
                      setQuestion(
                        "Audit my GPA, degree level, and work experience against Chevening 2026 criteria",
                      )
                    }
                  >
                    <div className="starter-card-top">
                      <span className="starter-icon">📊</span>
                      <span className="starter-badge badge-teal">Fit Audit</span>
                    </div>
                    <p className="starter-title">
                      Audit my GPA & work experience for <strong className="text-blue">Chevening 2026</strong>
                    </p>
                    <span className="starter-subtext">Audits 6 statutory rules</span>
                  </div>

                  <div
                    className="copilot-starter-card"
                    onClick={() =>
                      setQuestion(
                        "Draft a 500-word Leadership Essay using the STAR framework for Commonwealth Scholarship",
                      )
                    }
                  >
                    <div className="starter-card-top">
                      <span className="starter-icon">✍️</span>
                      <span className="starter-badge badge-blue">Essay Lab</span>
                    </div>
                    <p className="starter-title">
                      Draft 500-word Leadership Essay for <strong className="text-blue">Commonwealth</strong>
                    </p>
                    <span className="starter-subtext">Uses STAR framework</span>
                  </div>

                  <div
                    className="copilot-starter-card"
                    onClick={() =>
                      setQuestion(
                        "Generate a week-by-week application preparation plan for Fulbright 2026",
                      )
                    }
                  >
                    <div className="starter-card-top">
                      <span className="starter-icon">📅</span>
                      <span className="starter-badge badge-coral">Radar</span>
                    </div>
                    <p className="starter-title">
                      Generate preparation milestones for <strong className="text-blue">Fulbright 2026</strong>
                    </p>
                    <span className="starter-subtext">Syncs with Tracker</span>
                  </div>
                </div>
              </div>
            ) : (
              <section className="assistant-answer copilot-answer-view" aria-live="polite">
                <div className="assistant-answer-head">
                  <div>
                    <p className="eyebrow">
                      {answer.status === "completed" ? "Source-backed response" : "Transparent uncertainty"}
                    </p>
                    <h2>{answer.response.answer}</h2>
                    <p>Evidence confidence: {answer.response.confidence}</p>
                  </div>
                  {answer.status === "completed" ? (
                    <button
                      className="button button-quiet"
                      type="button"
                      onClick={save}
                      disabled={answer.saved_to_workspace}
                    >
                      {answer.saved_to_workspace ? "Saved to Workspace" : "Save result"}
                    </button>
                  ) : null}
                </div>

                {answer.response.warnings.length ? (
                  <div className="assistant-warning" role="alert">
                    <strong>Check before acting</strong>
                    <ul>
                      {answer.response.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {answer.response.facts.length ? (
                  <div className="assistant-section">
                    <h3>Verified facts</h3>
                    <ul>
                      {answer.response.facts.map((fact) => (
                        <li key={fact.text}>
                          {fact.text}{" "}
                          <CitationRefs ids={fact.citation_ids} citations={answer.response.citations} />
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {answer.response.possible_matches.length ? (
                  <div className="assistant-section">
                    <h3>Possible matches</h3>
                    {answer.response.possible_matches.map((m) => (
                      <article key={m.opportunity_id}>
                        <Link to={`/catalogue/${m.opportunity_id}`}>{m.name}</Link>
                        <p>
                          {m.reason} <CitationRefs ids={m.citation_ids} citations={answer.response.citations} />
                        </p>
                        <button type="button" onClick={() => startApplication(m.opportunity_id, m.name)}>
                          Create application plan
                        </button>
                      </article>
                    ))}
                  </div>
                ) : null}

                {answer.response.requirements_to_check.length ? (
                  <div className="assistant-section">
                    <h3>Requirements to confirm</h3>
                    <ul>
                      {answer.response.requirements_to_check.map((item) => (
                        <li key={item.text}>
                          {item.text}{" "}
                          <CitationRefs ids={item.citation_ids} citations={answer.response.citations} />
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {answer.response.private_progress.length ? (
                  <div className="assistant-section">
                    <h3>Private application progress</h3>
                    <ul>
                      {answer.response.private_progress.map((item) => (
                        <li key={item.opportunity_id}>
                          <strong>{item.name}</strong>: {item.lifecycle}; {item.outstanding_tasks} outstanding task(s).
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {answer.response.next_actions.length ? (
                  <div className="assistant-section">
                    <h3>Suggested next steps</h3>
                    <ol>
                      {answer.response.next_actions.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ol>
                  </div>
                ) : null}

                {answer.response.citations.length ? (
                  <div className="assistant-section">
                    <h3>Official citations</h3>
                    {answer.response.citations.map((citation) => (
                      <article className="assistant-citation" key={citation.id}>
                        <div>
                          <strong>{citation.source_title}</strong>
                          <p>{citation.excerpt}</p>
                          <small>
                            {citation.freshness}{" "}
                            {citation.last_verified_at
                              ? `· verified ${new Date(citation.last_verified_at).toLocaleDateString()}`
                              : ""}
                          </small>
                        </div>
                        <a
                          className="button button-quiet"
                          href={citation.source_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`Open official source: ${citation.source_title}`}
                        >
                          Open source ↗
                        </a>
                      </article>
                    ))}
                  </div>
                ) : null}

                <footer className="assistant-feedback">
                  <span>Was this response useful?</span>
                  {["helpful", "not_helpful", "incorrect", "outdated", "missing_citation"].map((kind) => (
                    <button type="button" key={kind} onClick={() => feedback(kind)}>
                      {kind.replaceAll("_", " ")}
                    </button>
                  ))}
                </footer>
              </section>
            )}
          </div>

          {/* Floating Input Capsule Section */}
          <div className="copilot-input-container">
            <form onSubmit={ask} className="copilot-input-form">
              <label htmlFor="assistant-question" className="sr-only">
                Ask about scholarships, requirements, funding, deadlines, or your progress
              </label>
              <textarea
                id="assistant-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                maxLength={4000}
                required
                placeholder="Ask about eligibility rules, draft essays, evaluate GPA match, or track deadlines..."
                className="copilot-textarea"
                rows={2}
              />

              <div className="copilot-input-controls-row">
                <div className="input-opt-ins">
                  <label className="assistant-opt-in">
                    <input
                      type="checkbox"
                      checked={useProfile}
                      onChange={(e) => setUseProfile(e.target.checked)}
                    />
                    Use my profile for this question
                  </label>
                  <label className="assistant-opt-in">
                    <input
                      type="checkbox"
                      checked={useApplicationData}
                      onChange={(e) => setUseApplicationData(e.target.checked)}
                    />
                    Use my private application workspace for progress or priority questions
                  </label>
                </div>

                <div className="input-action-buttons">
                  <button
                    className="button button-primary copilot-submit-btn"
                    disabled={loading || !preferences?.consented}
                  >
                    {loading ? "Checking verified sources…" : "Ask assistant"}
                  </button>
                </div>
              </div>
            </form>
            {notice ? (
              <p className="form-success copilot-notice" role="status">
                {notice}
              </p>
            ) : null}
          </div>

        </main>
      </div>
    </div>
  );
}
