const state = {
  mode: "login",
  user: null,
  accessToken: localStorage.getItem("saa_access_token"),
  refreshToken: localStorage.getItem("saa_refresh_token"),
  opportunities: { limit: 10, offset: 0, total: 0 },
};

const applicationStatuses = [
  "interested",
  "researching",
  "preparing_documents",
  "waiting_for_recommendation",
  "ready_to_apply",
  "submitted",
  "interview_stage",
  "accepted",
  "rejected",
  "withdrawn",
  "expired",
];

const $ = (selector) => document.querySelector(selector);

function humanize(value) {
  if (value === null || value === undefined || value === "") {
    return "Not stated";
  }
  return String(value).replaceAll("_", " ");
}

function formatDate(value) {
  if (!value) {
    return "Not stated";
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function setStatus(selector, message, type = "") {
  const element = $(selector);
  element.textContent = message || "";
  element.className = `form-status ${type}`.trim();
}

function authHeaders() {
  return state.accessToken ? { Authorization: `Bearer ${state.accessToken}` } : {};
}

async function api(path, options = {}, retry = true) {
  const headers = {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...authHeaders(),
    ...(options.headers || {}),
  };
  const response = await fetch(`/api/v1${path}`, { ...options, headers });

  if (response.status === 401 && retry && state.refreshToken) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      return api(path, options, false);
    }
  }

  if (response.status === 204) {
    return null;
  }

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
      : detail || data?.message || `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return data;
}

async function refreshTokens() {
  try {
    const response = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh_token: state.refreshToken }),
    });
    if (!response.ok) {
      clearSession();
      return false;
    }
    const data = await response.json();
    storeSession(data);
    return true;
  } catch {
    clearSession();
    return false;
  }
}

function storeSession(data) {
  state.accessToken = data.access_token;
  state.refreshToken = data.refresh_token;
  state.user = data.user;
  localStorage.setItem("saa_access_token", data.access_token);
  localStorage.setItem("saa_refresh_token", data.refresh_token);
}

function clearSession() {
  state.accessToken = null;
  state.refreshToken = null;
  state.user = null;
  localStorage.removeItem("saa_access_token");
  localStorage.removeItem("saa_refresh_token");
}

function updateAuthMode(mode) {
  state.mode = mode;
  $("#login-tab").classList.toggle("active", mode === "login");
  $("#register-tab").classList.toggle("active", mode === "register");
  $("#auth-submit").textContent = mode === "login" ? "Login" : "Register";
}

function updateSessionUi() {
  const loggedIn = Boolean(state.user);
  $("#auth-panel").hidden = loggedIn;
  $("#workspace").hidden = !loggedIn;
  $("#logout-button").hidden = !loggedIn;

  if (!loggedIn) {
    return;
  }

  $("#user-email").textContent = state.user.email;
  $("#user-role").textContent = state.user.role;
  $("#user-avatar").textContent = state.user.email.slice(0, 1).toUpperCase();

  const isAdmin = state.user.role === "admin";
  $("#admin").hidden = !isAdmin;
  $("#admin-nav").hidden = !isAdmin;
}

async function bootstrapSession() {
  if (!state.accessToken) {
    updateSessionUi();
    loadOpportunities();
    return;
  }

  try {
    state.user = await api("/auth/me");
    updateSessionUi();
    await Promise.allSettled([loadProfile(), loadOpportunities(), loadSaved()]);
    if (state.user.role === "admin") {
      loadAdminOpportunities();
    }
  } catch {
    clearSession();
    updateSessionUi();
    loadOpportunities();
  }
}

function queryFromForm(form, extra = {}) {
  const params = new URLSearchParams();
  new FormData(form).forEach((value, key) => {
    const trimmed = String(value).trim();
    if (trimmed) {
      params.set(key, trimmed);
    }
  });
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });
  return params.toString();
}

async function loadOpportunities() {
  setStatus("#opportunity-status", "Loading opportunities...");
  const form = $("#opportunity-filters");
  const limit = Number(new FormData(form).get("limit") || state.opportunities.limit);
  state.opportunities.limit = limit;
  const query = queryFromForm(form, { limit, offset: state.opportunities.offset });

  try {
    const data = await api(`/opportunities?${query}`);
    state.opportunities.total = data.pagination.total;
    renderOpportunities(data);
    setStatus(
      "#opportunity-status",
      `${data.pagination.total} verified opportunities found. Showing ${data.pagination.count}.`,
      "success",
    );
  } catch (error) {
    setStatus("#opportunity-status", error.message, "error");
  }
}

function renderOpportunities(data) {
  $("#previous-page").disabled = !data.pagination.has_previous;
  $("#next-page").disabled = !data.pagination.has_next;
  const list = $("#opportunity-list");
  list.innerHTML = "";

  if (!data.items.length) {
    list.innerHTML = emptyCard(
      "No verified opportunities yet",
      "Seed official opportunities or adjust your filters. Public search intentionally hides drafts and unverified records.",
    );
    return;
  }

  list.innerHTML = data.items.map(opportunityCard).join("");
  list.querySelectorAll("[data-detail]").forEach((button) => {
    button.addEventListener("click", () => loadOpportunityDetail(button.dataset.detail));
  });
  list.querySelectorAll("[data-save]").forEach((button) => {
    button.addEventListener("click", () => saveOpportunity(button.dataset.save));
  });
}

function opportunityCard(opportunity) {
  return `
    <article class="card">
      <div class="card-header">
        <div>
          <h3>${escapeHtml(opportunity.name)}</h3>
          <p>${escapeHtml(opportunity.provider_name)}${opportunity.university_name ? ` · ${escapeHtml(opportunity.university_name)}` : ""}</p>
        </div>
        <span class="pill good">${humanize(opportunity.verification_status)}</span>
      </div>
      <div class="card-meta">
        <span class="pill">${escapeHtml(opportunity.country)}</span>
        <span class="pill">${humanize(opportunity.degree_level)}</span>
        <span class="pill">${humanize(opportunity.funding_type)}</span>
        <span class="pill warn">Deadline: ${formatDate(opportunity.application_deadline)}</span>
      </div>
      <p>${escapeHtml(opportunity.funding_summary)}</p>
      <p>Last verified: ${formatDate(opportunity.last_verified_at)}</p>
      <div class="card-actions">
        <button class="button secondary" type="button" data-detail="${opportunity.id}">View details</button>
        <button class="ghost" type="button" data-save="${opportunity.id}">Save</button>
        <a class="ghost" href="${escapeAttribute(opportunity.official_source_url)}" target="_blank" rel="noreferrer">Official source</a>
      </div>
    </article>
  `;
}

async function loadOpportunityDetail(id) {
  setStatus("#opportunity-status", "Loading opportunity detail...");
  try {
    const opportunity = await api(`/opportunities/${id}`);
    $("#opportunity-detail").hidden = false;
    $("#detail-title").textContent = opportunity.name;
    $("#detail-content").innerHTML = `
      <div class="detail-grid">
        ${detailBlock("Funding package", [
          ["Tuition", opportunity.tuition_coverage],
          ["Monthly stipend", opportunity.monthly_stipend_amount ? `${opportunity.monthly_stipend_amount} ${opportunity.monthly_stipend_currency || ""}` : null],
          ["Accommodation", opportunity.accommodation_coverage],
          ["Travel", opportunity.travel_allowance],
          ["Health insurance", opportunity.health_insurance],
          ["Application fee", opportunity.application_fee_info],
        ])}
        ${detailBlock("Eligibility", [
          ["Field", opportunity.field_eligibility],
          ["Nationality", opportunity.nationality_eligibility],
          ["Minimum academics", opportunity.minimum_academic_requirement],
          ["English", opportunity.english_language_requirement],
          ["Standardized test", opportunity.standardized_test_requirement],
        ])}
        ${detailBlock("Required documents", opportunity.required_documents?.length ? opportunity.required_documents.map((item) => ["Document", item]) : [["Documents", null]])}
        ${detailBlock("Application", [
          ["Method", opportunity.application_method],
          ["Deadline", formatDate(opportunity.application_deadline)],
          ["Intake", opportunity.intake_year],
          ["Apply", opportunity.application_url ? `<a href="${escapeAttribute(opportunity.application_url)}" target="_blank" rel="noreferrer">${escapeHtml(opportunity.application_url)}</a>` : null],
        ])}
        <div class="detail-block full">
          <h3>Official source evidence</h3>
          <p><strong>${escapeHtml(opportunity.source.title)}</strong></p>
          <p>${escapeHtml(opportunity.source.relevant_excerpt)}</p>
          <p>Verification: ${humanize(opportunity.source.verification_status)} · Last verified: ${formatDate(opportunity.source.last_verified_at)}</p>
          <p><a href="${escapeAttribute(opportunity.source.url)}" target="_blank" rel="noreferrer">Open official source</a></p>
        </div>
      </div>
    `;
    setStatus("#opportunity-status", "Detail loaded.", "success");
  } catch (error) {
    setStatus("#opportunity-status", error.message, "error");
  }
}

function detailBlock(title, rows) {
  const body = rows
    .map(([label, value]) => `<p><strong>${escapeHtml(label)}:</strong> ${renderValue(value)}</p>`)
    .join("");
  return `<div class="detail-block"><h3>${escapeHtml(title)}</h3>${body}</div>`;
}

function renderValue(value) {
  if (value === null || value === undefined || value === "") {
    return "Not stated";
  }
  const stringValue = String(value);
  return stringValue.includes("<a ") ? stringValue : escapeHtml(stringValue);
}

async function saveOpportunity(opportunityId) {
  if (!state.user) {
    setStatus("#opportunity-status", "Login as a student before saving opportunities.", "error");
    return;
  }
  try {
    await api("/saved-opportunities", {
      method: "POST",
      body: JSON.stringify({ opportunity_id: opportunityId, status: "interested" }),
    });
    setStatus("#opportunity-status", "Opportunity saved to tracker.", "success");
    loadSaved();
  } catch (error) {
    setStatus("#opportunity-status", error.message, "error");
  }
}

async function loadProfile() {
  if (!state.user) {
    return;
  }
  try {
    const profile = await api("/profiles/me");
    if (!profile) {
      $("#profile-completeness").textContent = "No profile yet";
      return;
    }
    fillProfileForm(profile);
    $("#profile-completeness").textContent = `${profile.profile_completeness}% complete`;
    $("#profile-completeness").classList.toggle("good", profile.profile_completeness >= 70);
  } catch (error) {
    setStatus("#profile-status", error.message, "error");
  }
}

function fillProfileForm(profile) {
  const form = $("#profile-form");
  Object.entries(profile).forEach(([key, value]) => {
    const field = form.elements[key];
    if (!field) {
      return;
    }
    field.value = Array.isArray(value) ? value.join(", ") : (value ?? "");
  });
}

function profilePayload(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  const decimalFields = ["cgpa", "grading_scale", "ielts_score"];
  const payload = {
    nationality: optional(data.nationality),
    country_of_residence: optional(data.country_of_residence),
    current_education_level: optional(data.current_education_level),
    target_degree_level: optional(data.target_degree_level),
    intended_field: optional(data.intended_field),
    academic_discipline: optional(data.academic_discipline),
    cgpa: optionalNumber(data.cgpa),
    grading_scale: optionalNumber(data.grading_scale),
    english_test_status: data.english_test_status || "unknown",
    ielts_score: optionalNumber(data.ielts_score),
    research_experience: optional(data.research_experience),
    leadership_experience: optional(data.leadership_experience),
    preferred_destination_countries: splitList(data.preferred_destination_countries),
  };
  decimalFields.forEach((field) => {
    if (payload[field] === null) {
      delete payload[field];
    }
  });
  return payload;
}

function optional(value) {
  const trimmed = String(value || "").trim();
  return trimmed || null;
}

function optionalNumber(value) {
  const trimmed = String(value || "").trim();
  return trimmed ? Number(trimmed) : null;
}

function splitList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function saveProfile(event) {
  event.preventDefault();
  setStatus("#profile-status", "Saving profile...");
  try {
    const profile = await api("/profiles/me", {
      method: "PUT",
      body: JSON.stringify(profilePayload(event.currentTarget)),
    });
    fillProfileForm(profile);
    $("#profile-completeness").textContent = `${profile.profile_completeness}% complete`;
    setStatus("#profile-status", "Profile saved. Matching can now use this data.", "success");
  } catch (error) {
    setStatus("#profile-status", error.message, "error");
  }
}

async function loadMatches() {
  setStatus("#match-status", "Loading matches...");
  try {
    const data = await api("/matches/me");
    const list = $("#match-list");
    if (!data.results.length) {
      list.innerHTML = emptyCard(
        "No matches yet",
        "Create a profile and make sure verified opportunities exist.",
      );
    } else {
      list.innerHTML = data.results
        .map((match) => {
          const opportunity = match.opportunity;
          return `
            <article class="card">
              <div class="card-header">
                <div>
                  <h3>${escapeHtml(opportunity.name)}</h3>
                  <p>${escapeHtml(opportunity.country)} · ${humanize(opportunity.degree_level)}</p>
                </div>
                <span class="pill good">${match.match_score}/100 · ${escapeHtml(match.score_label)}</span>
              </div>
              <p>${escapeHtml(match.disclaimer)}</p>
              ${explanationList("Satisfied", match.explanation.satisfied, "good")}
              ${explanationList("Missing", match.explanation.missing, "danger")}
              ${explanationList("Uncertain", match.explanation.uncertain, "warn")}
              ${explanationList("Next steps", match.explanation.next_steps, "")}
            </article>
          `;
        })
        .join("");
    }
    setStatus("#match-status", "Matches refreshed.", "success");
  } catch (error) {
    setStatus("#match-status", error.message, "error");
  }
}

function explanationList(title, items, tone) {
  if (!items?.length) {
    return "";
  }
  return `
    <div>
      <span class="pill ${tone}">${escapeHtml(title)}</span>
      <p>${items.map(escapeHtml).join(" · ")}</p>
    </div>
  `;
}

async function loadSaved() {
  if (!state.user || state.user.role !== "student") {
    return;
  }
  setStatus("#saved-status", "Loading tracker...");
  try {
    const saved = await api("/saved-opportunities");
    renderSaved(saved);
    setStatus("#saved-status", `${saved.length} saved opportunities.`, "success");
  } catch (error) {
    setStatus("#saved-status", error.message, "error");
  }
}

function renderSaved(saved) {
  const list = $("#saved-list");
  if (!saved.length) {
    list.innerHTML = emptyCard("Tracker is empty", "Save an opportunity to start tracking it.");
    return;
  }
  list.innerHTML = saved
    .map(
      (item) => `
        <article class="card">
          <div class="card-header">
            <div>
              <h3>${escapeHtml(item.opportunity.name)}</h3>
              <p>${escapeHtml(item.opportunity.country)} · Deadline: ${formatDate(item.opportunity.application_deadline)}</p>
            </div>
            <span class="pill">${humanize(item.status)}</span>
          </div>
          <label>
            Status
            <select data-saved-status="${item.id}">
              ${applicationStatuses
                .map((status) => `<option value="${status}" ${status === item.status ? "selected" : ""}>${humanize(status)}</option>`)
                .join("")}
            </select>
          </label>
          <label>
            Personal notes
            <textarea rows="2" data-saved-notes="${item.id}">${escapeHtml(item.personal_notes || "")}</textarea>
          </label>
          <div class="card-actions">
            <button class="button secondary" type="button" data-update-saved="${item.id}">Update</button>
            <button class="ghost" type="button" data-delete-saved="${item.id}">Remove</button>
          </div>
        </article>
      `,
    )
    .join("");

  list.querySelectorAll("[data-update-saved]").forEach((button) => {
    button.addEventListener("click", () => updateSaved(button.dataset.updateSaved));
  });
  list.querySelectorAll("[data-delete-saved]").forEach((button) => {
    button.addEventListener("click", () => deleteSaved(button.dataset.deleteSaved));
  });
}

async function updateSaved(id) {
  try {
    await api(`/saved-opportunities/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: document.querySelector(`[data-saved-status="${id}"]`).value,
        personal_notes: document.querySelector(`[data-saved-notes="${id}"]`).value || null,
      }),
    });
    setStatus("#saved-status", "Tracker updated.", "success");
    loadSaved();
  } catch (error) {
    setStatus("#saved-status", error.message, "error");
  }
}

async function deleteSaved(id) {
  try {
    await api(`/saved-opportunities/${id}`, { method: "DELETE" });
    setStatus("#saved-status", "Saved opportunity removed.", "success");
    loadSaved();
  } catch (error) {
    setStatus("#saved-status", error.message, "error");
  }
}

async function loadAdminOpportunities() {
  if (!state.user || state.user.role !== "admin") {
    return;
  }
  setStatus("#admin-status", "Loading admin opportunities...");
  try {
    const data = await api("/admin/opportunities?limit=20&offset=0");
    const list = $("#admin-list");
    if (!data.items.length) {
      list.innerHTML = emptyCard("No admin records", "Create or import opportunities to begin review.");
    } else {
      list.innerHTML = data.items
        .map((item) => {
          const source = item.sources?.[0] || item.source;
          return `
            <article class="card">
              <div class="card-header">
                <div>
                  <h3>${escapeHtml(item.name)}</h3>
                  <p>${escapeHtml(item.provider_name)} · ${escapeHtml(item.country)}</p>
                </div>
                <span class="pill ${item.status === "active" ? "good" : "warn"}">${humanize(item.status)}</span>
              </div>
              <p>Source: ${escapeHtml(source?.title || "No source title")} · ${humanize(source?.verification_status)}</p>
              <div class="card-actions">
                ${source ? `<button class="button secondary" type="button" data-verify="${item.id}" data-source="${source.id}">Mark officially verified</button>` : ""}
              </div>
            </article>
          `;
        })
        .join("");
      list.querySelectorAll("[data-verify]").forEach((button) => {
        button.addEventListener("click", () =>
          verifyOpportunity(button.dataset.verify, button.dataset.source),
        );
      });
    }
    setStatus("#admin-status", `${data.pagination.total} admin records loaded.`, "success");
  } catch (error) {
    setStatus("#admin-status", error.message, "error");
  }
}

async function createAdminOpportunity(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  const deadline = optional(data.application_deadline);
  const payload = {
    name: data.name,
    provider_name: data.provider_name,
    country: data.country,
    degree_level: data.degree_level,
    funding_type: data.funding_type || "unknown",
    application_deadline: deadline ? new Date(deadline).toISOString() : null,
    status: "draft",
    data_confidence: "low",
    source: {
      url: data.source_url,
      source_type: "official",
      title: data.source_title,
      relevant_excerpt: data.source_excerpt,
      verification_status: "needs_review",
    },
  };

  setStatus("#admin-status", "Creating draft opportunity...");
  try {
    await api("/admin/opportunities", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    event.currentTarget.reset();
    setStatus("#admin-status", "Draft created. Review and verify before it becomes public.", "success");
    loadAdminOpportunities();
  } catch (error) {
    setStatus("#admin-status", error.message, "error");
  }
}

async function verifyOpportunity(opportunityId, sourceId) {
  try {
    await api(`/admin/opportunities/${opportunityId}/verification`, {
      method: "PATCH",
      body: JSON.stringify({
        source_id: sourceId,
        verification_status: "officially_verified",
        notes: "Verified from frontend admin console.",
      }),
    });
    setStatus("#admin-status", "Opportunity marked officially verified and active.", "success");
    loadAdminOpportunities();
    loadOpportunities();
  } catch (error) {
    setStatus("#admin-status", error.message, "error");
  }
}

function emptyCard(title, message) {
  return `
    <article class="card">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(message)}</p>
    </article>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value || "#");
}

$("#login-tab").addEventListener("click", () => updateAuthMode("login"));
$("#register-tab").addEventListener("click", () => updateAuthMode("register"));

$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  setStatus("#auth-status", `${state.mode === "login" ? "Logging in" : "Creating account"}...`);

  try {
    const result = await api(`/auth/${state.mode}`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    storeSession(result);
    updateSessionUi();
    setStatus("#auth-status", "");
    await Promise.allSettled([loadProfile(), loadOpportunities(), loadSaved()]);
    if (state.user.role === "admin") {
      loadAdminOpportunities();
    }
  } catch (error) {
    setStatus("#auth-status", error.message, "error");
  }
});

$("#logout-button").addEventListener("click", async () => {
  const refreshToken = state.refreshToken;
  clearSession();
  updateSessionUi();
  if (refreshToken) {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).catch(() => null);
  }
});

$("#opportunity-filters").addEventListener("submit", (event) => {
  event.preventDefault();
  state.opportunities.offset = 0;
  loadOpportunities();
});

$("#previous-page").addEventListener("click", () => {
  state.opportunities.offset = Math.max(0, state.opportunities.offset - state.opportunities.limit);
  loadOpportunities();
});

$("#next-page").addEventListener("click", () => {
  state.opportunities.offset += state.opportunities.limit;
  loadOpportunities();
});

$("#close-detail").addEventListener("click", () => {
  $("#opportunity-detail").hidden = true;
});

$("#profile-form").addEventListener("submit", saveProfile);
$("#load-matches").addEventListener("click", loadMatches);
$("#load-saved").addEventListener("click", loadSaved);
$("#load-admin").addEventListener("click", loadAdminOpportunities);
$("#admin-create-form").addEventListener("submit", createAdminOpportunity);

bootstrapSession();
