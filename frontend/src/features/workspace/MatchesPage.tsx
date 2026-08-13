import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { deadlineLabel, readableValue } from "../catalogue/catalogue";
import type { OpportunityMatch } from "./types";
import { getMatches, humanize, profileRequired } from "./workspace";

function Explanation({ title, values, tone }: { title: string; values: string[]; tone: string }) {
  if (!values.length) return null;
  return <section className={`explanation ${tone}`}><h3>{title}</h3><ul>{values.map((value) => <li key={value}>{value}</li>)}</ul></section>;
}

function MatchCard({ match }: { match: OpportunityMatch }) {
  const hardFailure = match.eligibility_status === "ineligible" || match.eligibility_status === "likely_ineligible";
  return <article className="match-card">
    <div className="match-card-header"><div><p className="eyebrow">{match.score_label}</p><h2>{match.opportunity.name}</h2><p>{match.opportunity.country} · {readableValue(match.opportunity.degree_level)} · {deadlineLabel(match.opportunity.application_deadline)}</p></div>
      <div className={`fit-score ${hardFailure ? "blocked" : ""}`}><strong>{hardFailure ? "--" : match.fit_score ?? match.match_score}</strong><span>{hardFailure ? humanize(match.eligibility_status) : "fit score"}</span></div></div>
    <div className="match-meta"><span>Evidence completeness {match.evidence_completeness}%</span><span>Profile completeness {match.profile_completeness}%</span><span>{humanize(match.confidence)} confidence</span>{match.preference_fit !== null ? <span>Preference fit {match.preference_fit}%</span> : null}<span>Matcher {match.matcher_version}</span></div>
    {hardFailure ? <p className="hard-gate">This opportunity has one or more known hard eligibility failures. It is shown for transparency, not as a recommendation.</p> : null}
    <div className="explanation-grid"><Explanation title="Already aligned" values={match.explanation.satisfied} tone="positive" /><Explanation title="Information to add" values={match.explanation.missing} tone="attention" /><Explanation title="Still uncertain" values={match.explanation.uncertain} tone="neutral" /><Explanation title="Next steps" values={match.explanation.next_steps} tone="next" /></div>
    {match.preference_mismatches.length ? <Explanation title="Preference mismatches" values={match.preference_mismatches} tone="attention" /> : null}
    {match.confidence_factors.length ? <Explanation title="Confidence factors" values={match.confidence_factors} tone="neutral" /> : null}
    {match.warnings.length ? <Explanation title="Warnings" values={match.warnings} tone="attention" /> : null}
    <p className="match-disclaimer">{match.disclaimer}</p>
    <Link className="detail-link" to={`/catalogue/${match.opportunity.id}`}>Review official opportunity details</Link>
  </article>;
}

export function MatchesPage() {
  const { user, isRestoring } = useAuth();
  const [matches, setMatches] = useState<OpportunityMatch[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [needsProfile, setNeedsProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user || user.role !== "student") return;
    let active = true;
    void getMatches().then((results) => { if (active) setMatches(results); }).catch((requestError: unknown) => {
      if (active) { setNeedsProfile(profileRequired(requestError)); if (!profileRequired(requestError)) setError(requestError instanceof Error ? requestError.message : "Unable to load matches."); }
    }).finally(() => { if (active) setIsLoading(false); });
    return () => { active = false; };
  }, [user]);

  if (isRestoring) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "student") return <Navigate replace to="/dashboard" />;
  return <main className="workspace-tool page-width" aria-busy={isLoading}>
    <section className="tool-header"><div><p className="eyebrow">Explainable matching</p><h1>Recommendations you can inspect.</h1><p className="lead">A fit score is not a prediction. Each result separates confirmed alignment from missing or uncertain information.</p></div><Link className="button button-quiet" to="/profile">Edit profile</Link></section>
    {isLoading ? <div className="catalogue-message">Evaluating your profile against verified opportunities...</div> : null}
    {needsProfile ? <div className="catalogue-message"><h2>Build your profile first.</h2><p>Matching needs your study goals and background. Unknown details are welcome, but no profile means there is nothing to compare yet.</p><Link className="button button-primary" to="/profile">Build profile</Link></div> : null}
    {error ? <div className="catalogue-message error-message" role="alert"><h2>We could not load matches.</h2><p>{error}</p></div> : null}
    {!isLoading && !needsProfile && !error && !matches.length ? <div className="catalogue-message"><h2>No matches are available yet.</h2><p>There may be no currently verified opportunities that can be compared with your profile.</p><Link className="button button-primary" to="/catalogue">Explore catalogue</Link></div> : null}
    <div className="match-list">{matches.map((match) => <MatchCard key={match.opportunity.id} match={match} />)}</div>
  </main>;
}
