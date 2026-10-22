/* MediBot frontend – talks only to the JSON API under /api. All medical content
   shown here comes from backend responses; nothing clinical is hard-coded. */
(() => {
  "use strict";

  // ── UI strings ────────────────────────────────────────────────────────────
  const I18N = {
    hi: {
      brand_sub: "symptom guide",
      hero_title: "Kya takleef hai?", hero_title_b: "Batayein.",
      hero_lead: "Kuch sawaal poochkar bataunga ki kaunsi aam wajah ho sakti hai — source ke saath.",
      start: "Shuru karein", resume: "Jahan chhoda tha wahin se",
      voice_hint: "Bolkar bhi bata sakte hain.",
      scope_line: "Sirf aam takleefon ke liye. Diagnosis ya dawai nahi batata.",
      emerg_strip_t: "Emergency?", emerg_strip_d: "Abhi call karein:",
      footer_disclaimer: "Sirf jaankari ke liye. Software tested hai, clinically validated nahi.",
      footer_sources: "Sources ki list", footer_graph: "WHO disease graph",
      steps: ["Aapki baat", "Safety check", "Sawaal", "Nateeja"], step_of: (n, m, name) => `${n}/${m} — ${name}`,
      input_label: "Apne symptoms likhein", placeholder: "Likhiye ya bolkar batayiye… jaise \"2 din se sar dard aur halka bukhar\"",
      composer_hint: "Enter dabakar bhejein. Kuch galat likha gaya ho to baad mein bhi badal sakte hain.",
      assess_now: "Ab tak ki baat par nateeja dikhayein",
      side_title: "Ab tak ki baat", side_help: "Jo aapne bataya, woh yahan likha jaata hai. Kuch galat ho to yahin theek kar dein.",
      side_symptoms: "Symptoms", side_details: "Aur details", add_symptom: "Symptom jodein", add: "Jodein", close: "Band karein",
      restart: "Shuru se", restart_full: "Shuru se karein", summary_btn: "Notes",
      no_symptoms: "Abhi koi symptom nahi.", choose_symptom: "Symptom chunein…",
      st_present: "Hai", st_absent: "Nahi hai", st_unsure: "Pata nahi", remove: "Hatayein",
      d_duration: "Kab se", d_severity: "Takleef (1–10)", d_onset: "Shuruaat", d_progression: "Badlaav", d_age: "Kiske liye",
      unknown: "—", dur_opts: [["", "—"], ["0.5", "Ek din se kam"], ["2", "1–3 din"], ["5", "4–7 din"], ["10", "1–2 hafte"], ["21", "2–4 hafte"], ["45", "1 mahine se zyada"]],
      onset_opts: [["", "—"], ["sudden", "Achanak"], ["gradual", "Dheere-dheere"]],
      prog_opts: [["", "—"], ["improving", "Behtar"], ["same", "Waise hi"], ["worsening", "Badh raha"]],
      age_opts: [["", "—"], ["adult", "Adult (18+)"], ["teen", "Teenager (12–17)"], ["child", "12 se chhota bachcha"], ["older", "65+"]],
      why: "Yeh kyun pooch raha hoon:", cont: "Aage badhein", none: "Inme se koi nahi", skip_to: "Abhi assessment dikhayein",
      tag_screen: "Safety check", tag_clarify: "Confirm karna", tag_q: "Sawaal",
      thinking: "Soch raha hoon…", checking: "Warning signs check ho rahe hain…", building: "Sources ke saath assessment ban raha hai…",
      em_call: "112 call karein", em_amb: "108 ambulance", em_mh: "Tele-MANAS 14416", em_reasons: "Yeh kyun dikh raha hai:",
      em_mistake: "Yeh mujh par laagu nahi hota", em_you_said: "Aapne likha/chuna:",
      res_title: "Aapka assessment", res_updated: "Nayi jaankari ke saath update hua",
      what_fits: "Kya match karta hai", what_not: "Kya kam match karta hai", what_unknown: "Abhi pata nahi", what_unexplained: "Iss condition se explain nahi hota",
      what_help: "Kya jaankari madad karegi", alternatives: "Yeh bhi ho sakta hai", self_care: "Ghar par kya karein", see_doc: "Doctor ko kab dikhayein",
      related: "Sources se aur jaankari", how_assessed: "Yeh kaise assess kiya gaya", limitations: "Seemayein (limitations)",
      sources: "Sources", set_aside: "Kam sambhav maana gaya (rule out nahi)", more_conds: "Aur conditions jo kuch match karti hain",
      reported: "Aapne bataya", absent_lbl: "Nahi hai", copy: "Copy karein", download: "Download (.txt)", print: "Print",
      copied: "Summary copy ho gaya", ai_title: "Aasaan shabdon mein (AI)", ai_loading: "AI se aasaan summary ban raha hai…",
      source_word: "Source", open_src: "Source kholein", reviewed: "Review", validation: "Evidence check",
      grounded: (g, c) => `${c} mein se ${g} medical statements verified source passage se jude hain.`,
      net_error: "Server tak nahi pahunch paaye. Internet check karke dobara koshish karein.",
      timeout: "Jawab aane mein zyada time lag raha hai. Dobara koshish karein.",
      expired: "Yeh session expire ho gaya. Naya assessment shuru kar rahe hain.",
      mic_err: "Voice input abhi available nahi hai — kripya type karein.",
      mic_label: "Bolkar batayein", theme_dark: "Dark mode karein", theme_light: "Light mode karein",
      mic_insecure: "Mic is address par block hai — browser sirf https ya localhost par mic deta hai. Isi computer par {url} kholein, ya app ko `python app.py --https` se chalayein.",
      mic_unsupported: "Is browser mein voice recording support nahi hai — kripya type karein.", mic_denied: "Microphone ki permission nahi mili. Browser settings mein allow karein, ya type karein.",
      voice_listening: "Sun raha hoon… bolna rokte hi apne-aap ruk jaayega", voice_processing: "Samajh raha hoon…",
      voice_stop: "Ho gaya", voice_cancel: "Cancel", voice_no_speech: "Kuch sunai nahi diya — mic ke paas dobara bolein, ya type karein.",
      voice_note: "Awaaz se likha gaya hai — bhejne se pehle ek baar padh lein.", autosend: "Bolne ke baad apne-aap bhejein",
      speak_on: "Jawab bolkar sunayein", speak_off: "Jawab bolna band karein",
      lang_suggest: "Kya aap English mein jaari rakhna chahenge?",
      sources_title: "Medical sources (knowledge base)",
      outdated: "Purana ho sakta hai",
    },
    en: {
      brand_sub: "symptom guide",
      hero_title: "What's bothering you?", hero_title_b: "Tell me.",
      hero_lead: "A few questions, then the likely common causes — with sources.",
      start: "Let's start", resume: "Pick up where you left off",
      voice_hint: "You can also just speak.",
      scope_line: "For common, minor problems only. No diagnosis, no medicines.",
      emerg_strip_t: "Emergency?", emerg_strip_d: "Call now:",
      footer_disclaimer: "For information only. Software-tested, not clinically validated.",
      footer_sources: "List of sources", footer_graph: "WHO disease graph",
      steps: ["Your story", "Safety check", "Questions", "Result"], step_of: (n, m, name) => `${n} of ${m} — ${name}`,
      input_label: "Describe your symptoms", placeholder: "Type or speak… e.g. \"headache and a mild fever for 2 days\"",
      composer_hint: "Press Enter to send. You can still change anything later.",
      assess_now: "Show me the result so far",
      side_title: "What you've told me", side_help: "Everything you mention is noted here. If something's wrong, fix it here.",
      side_symptoms: "Symptoms", side_details: "Other details", add_symptom: "Add a symptom", add: "Add", close: "Close",
      restart: "Start over", restart_full: "Start over", summary_btn: "Notes",
      no_symptoms: "No symptoms yet.", choose_symptom: "Choose a symptom…",
      st_present: "Yes", st_absent: "No", st_unsure: "Not sure", remove: "Remove",
      d_duration: "How long", d_severity: "Severity (1–10)", d_onset: "Onset", d_progression: "Change", d_age: "For",
      unknown: "—", dur_opts: [["", "—"], ["0.5", "Less than a day"], ["2", "1–3 days"], ["5", "4–7 days"], ["10", "1–2 weeks"], ["21", "2–4 weeks"], ["45", "More than a month"]],
      onset_opts: [["", "—"], ["sudden", "Sudden"], ["gradual", "Gradual"]],
      prog_opts: [["", "—"], ["improving", "Improving"], ["same", "Same"], ["worsening", "Worsening"]],
      age_opts: [["", "—"], ["adult", "Adult (18+)"], ["teen", "Teen (12–17)"], ["child", "Child under 12"], ["older", "65+"]],
      why: "Why I'm asking:", cont: "Continue", none: "None of these", skip_to: "Show assessment now",
      tag_screen: "Safety check", tag_clarify: "Clarifying", tag_q: "Question",
      thinking: "Thinking…", checking: "Checking warning signs…", building: "Building your assessment with sources…",
      em_call: "Call 112", em_amb: "108 ambulance", em_mh: "Tele-MANAS 14416", em_reasons: "Why you're seeing this:",
      em_mistake: "This doesn't apply to me", em_you_said: "You wrote/selected:",
      res_title: "Your assessment", res_updated: "Updated with new information",
      what_fits: "What fits", what_not: "What fits less well", what_unknown: "Not known yet", what_unexplained: "Not explained by this condition",
      what_help: "What would help clarify", alternatives: "Other possibilities", self_care: "Self-care", see_doc: "When to see a doctor",
      related: "More from the sources", how_assessed: "How this was assessed", limitations: "Limitations",
      sources: "Sources", set_aside: "Considered less likely (not ruled out)", more_conds: "Other conditions with some overlap",
      reported: "You reported", absent_lbl: "Not present", copy: "Copy", download: "Download (.txt)", print: "Print",
      copied: "Summary copied", ai_title: "In plain words (AI)", ai_loading: "Writing a plain-language summary…",
      source_word: "Source", open_src: "Open source", reviewed: "Reviewed", validation: "Evidence check",
      grounded: (g, c) => `${g} of ${c} medical statements are linked to a verified source passage.`,
      net_error: "Couldn't reach the server. Check your connection and try again.",
      timeout: "The server is taking too long. Please try again.",
      expired: "This session expired. Starting a new assessment.",
      mic_err: "Voice input isn't available right now — please type instead.",
      mic_label: "Speak your symptoms", theme_dark: "Switch to dark mode", theme_light: "Switch to light mode",
      mic_insecure: "The microphone is blocked on this address — browsers only allow it on https or localhost. Open {url} on this computer, or start the app with `python app.py --https`.",
      mic_unsupported: "This browser can't record audio — please type instead.", mic_denied: "Microphone permission was blocked. Allow it in your browser settings, or type instead.",
      voice_listening: "Listening… I'll stop when you pause", voice_processing: "Understanding…",
      voice_stop: "Done", voice_cancel: "Cancel", voice_no_speech: "I didn't hear anything — try again closer to the mic, or type.",
      voice_note: "Typed from your voice — give it a quick read before sending.", autosend: "Send automatically after speaking",
      speak_on: "Read replies aloud", speak_off: "Stop reading replies aloud",
      lang_suggest: "Would you like to continue in Hinglish?",
      sources_title: "Medical sources (knowledge base)",
      outdated: "May be outdated",
    },
  };

  // ── state ────────────────────────────────────────────────────────────────
  const S = { lang: "hi", sid: null, last: null, busy: false, meta: null, results: null, lastAssessKey: null };
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const t = (k) => (I18N[S.lang][k] !== undefined ? I18N[S.lang][k] : I18N.en[k]);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  };

  // ── API ──────────────────────────────────────────────────────────────────
  class ApiError extends Error { constructor(msg, status, code) { super(msg); this.status = status; this.code = code; } }
  async function api(path, { method = "GET", body, timeout = 45000 } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    let res;
    try {
      res = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined, signal: ctrl.signal });
    } catch (e) {
      throw new ApiError(e.name === "AbortError" ? t("timeout") : t("net_error"), 0, "network");
    } finally { clearTimeout(timer); }
    let data = null;
    try { data = await res.json(); } catch { /* non-JSON */ }
    if (!res.ok) {
      const err = data && data.error ? data.error : {};
      throw new ApiError(err.message || `Error ${res.status}`, res.status, err.code);
    }
    return data;
  }

  function toast(msg, isError = false, ms) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.setAttribute("role", isError ? "alert" : "status");
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), ms || (isError ? 6000 : 2500));
  }

  async function guarded(fn, label) {
    if (S.busy) return;
    S.busy = true; setBusy(true, label);
    try { await fn(); }
    catch (e) {
      if (e.status === 404 && S.sid) { toast(t("expired"), true); await startAssessment(); }
      else toast(e.message || t("net_error"), true);
    } finally { S.busy = false; setBusy(false); }
  }

  // ── static text / language ───────────────────────────────────────────────
  function applyStatic() {
    document.documentElement.lang = S.lang === "hi" ? "hi-Latn" : "en";
    $$("[data-i18n]").forEach((el) => { const v = t(el.dataset.i18n); if (typeof v === "string") el.textContent = v; });
    $$("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    $$(".lang-toggle button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === S.lang)));
    if (typeof paintTheme === "function") paintTheme();
    const sb = $("#start-btn");
    if (sb) sb.textContent = store.get("medibot_sid") ? t("resume") : t("start");
  }

  async function setLanguage(lang) {
    if (lang === S.lang) return;
    S.lang = lang; store.set("medibot_lang", lang); applyStatic();
    if (S.sid && !$("#workspace").hidden) {
      await guarded(async () => { const r = await api(`/api/assessments/${S.sid}/language`, { method: "PATCH", body: { language: lang } }); handle(r); });
    }
  }

  // ── landing ──────────────────────────────────────────────────────────────
  function showWorkspace() {
    $("#landing").hidden = true;
    $("#workspace").hidden = false;
    $("#restart-btn").hidden = false;
    $("#summary-toggle").hidden = false;
    window.scrollTo({ top: 0 });
  }

  function showLanding() {
    $("#landing").hidden = false;
    $("#workspace").hidden = true;
    $("#restart-btn").hidden = true;
    $("#summary-toggle").hidden = true;
    applyStatic();
  }

  async function startAssessment() {
    $("#chat").innerHTML = ""; $("#results").hidden = true; $("#results").innerHTML = ""; $("#emergency-slot").innerHTML = "";
    S.lastAssessKey = null;
    const r = await api("/api/assessments", { method: "POST", body: { language: S.lang } });
    S.sid = r.session_id; store.set("medibot_sid", S.sid);
    showWorkspace();
    handle(r);
    $("#input").focus();
  }

  async function resume(sid) {
    const r = await api(`/api/assessments/${sid}`);
    S.sid = sid; S.lang = r.language; store.set("medibot_lang", S.lang); applyStatic();
    showWorkspace();
    $("#chat").innerHTML = "";
    (r.transcript || []).forEach((m) => addMessage(m.role === "user" ? "user" : "bot", m.text, m.kind));
    r.messages = [];
    handle(r);
  }

  // ── chat rendering ───────────────────────────────────────────────────────
  function addMessage(who, text, kind) {
    if (!text) return;
    const div = document.createElement("div");
    div.className = `msg ${who}${kind === "answer" ? " answer" : ""}`;
    // name only at the start of a run of messages from the same side, like a written transcript
    const prev = [...$("#chat").children].reverse().find((el) => el.classList.contains("msg") && el.id !== "typing");
    const first = !prev || !prev.classList.contains(who);
    div.innerHTML = `${first ? `<div class="who"></div>` : ""}<div class="bubble"></div>`;
    if (first) div.querySelector(".who").textContent = who === "user" ? (S.lang === "hi" ? "Aap" : "You") : "MediBot";
    div.querySelector(".bubble").textContent = text;
    $("#chat").appendChild(div);
    scrollChat();
  }

  function scrollChat() {
    const last = $("#chat").lastElementChild;
    if (last) last.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function setBusy(on, label) {
    $("#send-btn").disabled = on;
    $$(".qcard button").forEach((b) => (b.disabled = on));
    const existing = $("#typing");
    if (on && !existing) {
      const d = document.createElement("div");
      d.id = "typing"; d.className = "msg bot";
      d.innerHTML = `<div class="bubble typing" role="status"><span class="typing-label">${esc(label || t("thinking"))}</span></div>`;
      $("#chat").appendChild(d); scrollChat();
    } else if (!on && existing) existing.remove();
  }

  // ── main response handler ────────────────────────────────────────────────
  // Run one part of the screen update; a failure in one part (e.g. a page/script version
  // mismatch) is logged instead of stopping the reply, the question or the safety guidance.
  function part(name, fn) {
    try { fn(); } catch (e) { console.error(`MediBot: could not update ${name}`, e); }
  }

  function handle(r) {
    S.last = r;
    if (r.language && r.language !== S.lang) { S.lang = r.language; part("language", applyStatic); }
    $$(".qcard").forEach((q) => q.remove());
    (r.messages || []).forEach((m) => addMessage("bot", m.text, m.kind));
    part("emergency", () => renderEmergency(r.emergency));      // safety guidance first
    if (r.question) part("question", () => renderQuestion(r.question));
    part("read-aloud", () => {
      if (!TTS.on) return;
      stopSpeaking();
      (r.messages || []).forEach((m) => speak(m.text));
      if (r.emergency) { speak(r.emergency.title); speak(r.emergency.instruction); }
      else if (r.question) speak(r.question.text);
      else if (r.assessment) speak(r.assessment.urgency.label + ". " + r.assessment.summary);
    });
    part("progress", () => renderStepper(r.progress, r.stage));
    part("notes", () => renderSide(r));
    part("results", () => renderResults(r.assessment));
    part("toolbar", () => {
      const btn = $("#assess-now"), count = $("#summary-count");
      if (btn) btn.hidden = !(r.can_assess && r.stage !== "assessment" && r.stage !== "emergency");
      if (count) count.textContent = (r.symptoms || []).filter((s) => s.status === "present").length;
    });
  }

  function renderStepper(p, stage) {
    if (!p) return;
    const steps = t("steps");
    const box = $("#stepper"), label = $("#step-label"), list = $("#stepper-list");
    if (!box || !list) return;
    box.classList.toggle("emergency", stage === "emergency");
    if (label) label.textContent = t("step_of")(p.step + 1, steps.length, steps[p.step]);
    list.innerHTML = steps.map((s, i) => {
      const cls = i < p.step ? "done" : i === p.step ? "current" : "";
      return `<li class="${cls}" ${i === p.step ? 'aria-current="step"' : ""}><span class="visually-hidden">${esc(s)}</span></li>`;
    }).join("");
  }

  // ── question cards ───────────────────────────────────────────────────────
  function renderQuestion(q) {
    const card = document.createElement("div");
    card.className = "qcard" + (q.kind === "screen" ? " screen" : "");
    const tag = q.kind === "screen" ? t("tag_screen") : q.kind === "clarify" ? t("tag_clarify") : t("tag_q");
    let inner = `<fieldset><legend tabindex="-1"><span class="qtag">${esc(tag)}</span><br>${esc(q.text)}</legend>
      <p class="why"><span><strong>${esc(t("why"))}</strong> ${esc(q.why)}</span></p>`;
    if (q.type === "multi") {
      const pre = new Set(q.preselected || []);
      inner += `<div class="options" role="group">` + q.options.map((o) =>
        `<button type="button" class="opt" role="checkbox" aria-checked="${pre.has(o.value)}" data-v="${esc(o.value)}"><span class="box" aria-hidden="true">${pre.has(o.value) ? "✓" : ""}</span>${esc(o.label)}</button>`).join("") +
        (q.none_option ? `<button type="button" class="opt none" data-none="1">${esc(t("none"))}</button>` : "") + `</div>
        <div class="qactions"><button type="button" class="btn btn-primary btn-sm" data-submit="1">${esc(t("cont"))}</button></div>`;
    } else if (q.type === "scale") {
      inner += `<div class="scale" role="group">` + Array.from({ length: q.max - q.min + 1 }, (_, i) => i + q.min)
        .map((n) => `<button type="button" class="opt" data-v="${n}" aria-label="${n}">${n}</button>`).join("") + `</div>
        <div class="scale-labels">${Object.entries(q.labels || {}).map(([k, v]) => `<span>${esc(k)} · ${esc(v)}</span>`).join("")}</div>`;
    } else {
      inner += `<div class="options" role="group">` + q.options.map((o) => `<button type="button" class="opt" data-v="${esc(o.value)}">${esc(o.label)}</button>`).join("") + `</div>`;
    }
    inner += `</fieldset>`;
    card.innerHTML = inner;
    card.dataset.qid = q.id;

    card.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || b.disabled) return;
      if (q.type === "multi") {
        if (b.dataset.none) return submitAnswer(q, "none");
        if (b.dataset.submit) {
          const vals = $$('.opt[aria-checked="true"]', card).map((x) => x.dataset.v);
          return submitAnswer(q, vals.length ? vals : "none");
        }
        if (b.dataset.v !== undefined) {
          const on = b.getAttribute("aria-checked") !== "true";
          b.setAttribute("aria-checked", String(on));
          b.querySelector(".box").textContent = on ? "✓" : "";
        }
      } else if (b.dataset.v !== undefined) {
        b.setAttribute("aria-pressed", "true");
        submitAnswer(q, q.type === "scale" ? Number(b.dataset.v) : b.dataset.v);
      }
    });
    $("#chat").appendChild(card);
    scrollChat();
    const lg = card.querySelector("legend");
    if (document.activeElement !== $("#input")) lg.focus({ preventScroll: true });
  }

  function submitAnswer(q, value) {
    const label = q.kind === "screen" ? t("checking") : t("thinking");
    guarded(async () => {
      const r = await api(`/api/assessments/${S.sid}/answers`, { method: "POST", body: { question_id: q.id, value } });
      $$(".qcard").forEach((c) => c.remove());
      // echo the chosen answer as the user's message
      let text;
      if (value === "none") text = t("none");
      else if (Array.isArray(value)) text = value.map((v) => (q.options.find((o) => o.value === v) || {}).label || v).join(", ");
      else if (q.type === "scale") text = `${value}/10`;
      else text = (q.options.find((o) => o.value === value) || {}).label || value;
      addMessage("user", text, "answer");
      handle(r);
    }, label);
  }

  // ── emergency ────────────────────────────────────────────────────────────
  function citeLink(c) {
    if (!c) return "";
    return `<a class="cite-link" href="${esc(c.link || c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.publisher.split(" (")[0])}: ${esc(c.title)} ↗</a>`;
  }
  function quoteBlock(c) {
    if (!c) return "";
    return `<div class="quote"><q>${esc(c.quote)}</q> — ${citeLink(c)}</div>`;
  }

  function renderEmergency(em) {
    const slot = $("#emergency-slot");
    if (!em) { slot.innerHTML = ""; $("#composer").hidden = false; return; }
    slot.innerHTML = `<div class="emergency-card" role="alert">
      <h2><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M12 3 2 21h20L12 3z"/><path d="M12 10v5M12 18h.01"/></svg>${esc(em.title)}</h2>
      <p class="instr">${esc(em.instruction)}</p>
      <div class="call-row">
        <a class="btn btn-danger btn-lg" href="tel:112">${esc(t("em_call"))}</a>
        ${em.mental_health ? `<a class="btn btn-danger btn-lg" href="tel:14416">${esc(t("em_mh"))}</a>` : `<a class="btn btn-danger btn-lg" href="tel:108">${esc(t("em_amb"))}</a>`}
      </div>
      <p class="small">${esc(em.while_waiting)}</p>
      <h3 class="small">${esc(t("em_reasons"))}</h3>
      ${em.reasons.map((r) => `<div class="reason"><strong>${esc(r.label)}</strong>
        <div class="matched">${esc(t("em_you_said"))} “${esc(r.matched)}”</div>
        ${r.citations.map(quoteBlock).join("")}
        <button type="button" class="btn btn-sm btn-ghost" data-dismiss="${esc(r.id)}">${esc(t("em_mistake"))}</button></div>`).join("")}
      <p class="small muted">${esc(em.note)}</p></div>`;
    slot.querySelectorAll("[data-dismiss]").forEach((b) => b.addEventListener("click", () =>
      guarded(async () => handle(await api(`/api/assessments/${S.sid}/red-flags/${b.dataset.dismiss}/dismiss`, { method: "POST" })))));
    slot.querySelector(".emergency-card").scrollIntoView({ block: "start", behavior: "smooth" });
  }

  // ── side panel ───────────────────────────────────────────────────────────
  function opts(list, val) { return list.map(([v, l]) => `<option value="${esc(v)}" ${String(val ?? "") === v ? "selected" : ""}>${esc(l)}</option>`).join(""); }

  function renderSide(r) {
    const list = $("#sym-list");
    const syms = r.symptoms || [];
    const row = (s) => `
      <li class="sym ${s.status}">
        <span class="st" aria-hidden="true">${s.status === "present" ? "✓" : s.status === "absent" ? "✕" : "?"}</span>
        <span class="name">${esc(s.label)}${s.user_words && s.user_words.length ? `<span class="words">“${esc(s.user_words.slice(-1)[0])}”</span>` : ""}</span>
        <label class="visually-hidden" for="st-${esc(s.id)}">${esc(s.label)}</label>
        <select id="st-${esc(s.id)}" data-sym="${esc(s.id)}">
          <option value="present" ${s.status === "present" ? "selected" : ""}>${esc(t("st_present"))}</option>
          <option value="absent" ${s.status === "absent" ? "selected" : ""}>${esc(t("st_absent"))}</option>
          <option value="unsure" ${s.status === "unsure" ? "selected" : ""}>${esc(t("st_unsure"))}</option>
        </select>
        <button type="button" class="rm" data-rm="${esc(s.id)}" aria-label="${esc(t("remove"))}: ${esc(s.label)}">✕</button>
      </li>`;
    const shown = syms.filter((s) => s.status !== "absent");
    const absent = syms.filter((s) => s.status === "absent");
    const wasOpen = !!$("#absent-group[open]");
    list.innerHTML = (shown.length ? shown.map(row).join("") : `<li class="empty">${esc(t("no_symptoms"))}</li>`) +
      (absent.length ? `<li><details id="absent-group" class="plain" ${wasOpen ? "open" : ""}><summary class="small">${esc(t("absent_lbl"))} (${absent.length})</summary>
        <ul class="sym-list" style="margin-top:6px">${absent.map(row).join("")}</ul></details></li>` : "");

    if (S.meta) {
      const have = new Set(syms.map((s) => s.id));
      $("#add-symptom").innerHTML = `<option value="">${esc(t("choose_symptom"))}</option>` +
        S.meta.symptoms.filter((s) => !have.has(s.id) && s.id !== "other_pain")
          .sort((a, b) => (a[S.lang] || a.en).localeCompare(b[S.lang] || b.en))
          .map((s) => `<option value="${esc(s.id)}">${esc(s[S.lang] || s.en)}</option>`).join("");
    }
    const a = r.attributes || {};
    const dur = a.duration_days == null ? "" : String(a.duration_days);
    const durList = t("dur_opts").some(([v]) => v === dur) ? t("dur_opts") : [...t("dur_opts"), [dur, `${dur} ${S.lang === "hi" ? "din" : "days"}`]];
    $("#details").innerHTML = `
      <dt><label for="a-duration">${esc(t("d_duration"))}</label></dt><dd><select id="a-duration" data-attr="duration_days">${opts(durList, dur)}</select></dd>
      <dt><label for="a-severity">${esc(t("d_severity"))}</label></dt><dd><select id="a-severity" data-attr="severity">${opts([["", "—"], ...Array.from({ length: 10 }, (_, i) => [String(i + 1), String(i + 1)])], a.severity == null ? "" : String(a.severity))}</select></dd>
      <dt><label for="a-onset">${esc(t("d_onset"))}</label></dt><dd><select id="a-onset" data-attr="onset">${opts(t("onset_opts"), a.onset || "")}</select></dd>
      <dt><label for="a-prog">${esc(t("d_progression"))}</label></dt><dd><select id="a-prog" data-attr="progression">${opts(t("prog_opts"), a.progression || "")}</select></dd>
      <dt><label for="a-age">${esc(t("d_age"))}</label></dt><dd><select id="a-age" data-attr="age_group">${opts(t("age_opts"), a.age_group || "")}</select></dd>`;
    $("#side-notices").innerHTML = (r.notices || []).map((n) => `<div class="notice lvl-${esc(n.level)}"><div class="lvl-title"><strong>${esc(n.label)}</strong></div>${n.citations.map(quoteBlock).join("")}</div>`).join("");
  }

  // ── results ──────────────────────────────────────────────────────────────
  function renderResults(a) {
    const box = $("#results");
    if (!a) { box.hidden = true; box.innerHTML = ""; S.results = null; return; }
    const key = JSON.stringify([a.status, a.conditions.map((c) => [c.id, c.support.level]), a.urgency.level, S.lang, a.reported]);
    const updated = S.lastAssessKey && S.lastAssessKey !== key;
    if (S.lastAssessKey === key && !box.hidden) return;
    S.lastAssessKey = key; S.results = a;
    const rep = a.reported;
    box.innerHTML = `<div class="results">
      <div class="results-head"><h2 tabindex="-1" id="results-title">${esc(t("res_title"))}</h2>
        <div class="toolbar">
          <button type="button" class="btn btn-sm btn-outline" data-act="copy">${esc(t("copy"))}</button>
          <button type="button" class="btn btn-sm btn-outline" data-act="download">${esc(t("download"))}</button>
          <button type="button" class="btn btn-sm btn-outline" data-act="print">${esc(t("print"))}</button>
        </div></div>
      ${updated ? `<div class="notice lvl-soon small">${esc(t("res_updated"))}</div>` : ""}
      <div class="urgency lvl-${esc(a.urgency.level)}" role="status">
        <div class="lvl-title">${esc(a.urgency.label)}</div>
        ${a.urgency.reasons.length ? `<ul>${a.urgency.reasons.map((r) => `<li>${esc(r.text)} ${r.citations.map(citeLink).join(" ")}</li>`).join("")}</ul>` : ""}
      </div>
      <p class="summary-text">${esc(a.summary)}</p>
      <div id="ai-summary"></div>
      <div class="pill-row" aria-label="${esc(t("reported"))}">
        ${rep.present.map((s) => `<span class="pill">✓ ${esc(s.label)}</span>`).join("")}
        ${rep.absent.length ? `<span class="pill muted" title="${esc(rep.absent.map((s) => s.label).join(", "))}">✕ ${esc(t("absent_lbl"))}: ${rep.absent.length}</span>` : ""}
        ${rep.duration ? `<span class="pill">${esc(t("d_duration"))}: ${esc(rep.duration)}</span>` : ""}
        ${rep.severity ? `<span class="pill">${esc(t("d_severity"))}: ${esc(rep.severity)}</span>` : ""}
      </div>
      ${a.conditions.map((c, i) => `
        <details class="cond" ${i === 0 ? "open" : ""}>
          <summary>
            <div style="flex:1;min-width:0">
              <div class="cond-title">${esc(c.name)}</div>
              <div class="cond-desc">${esc(c.description)}</div>
            </div>
            <span class="badge ${esc(c.support.level)}">${esc(c.support.label)}</span>
            <svg class="chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
          </summary>
          <div class="cond-body">
            <div class="explain">${esc(c.explanation)}<div class="rule">${esc(c.support.rule)}</div>
              ${c.description_citation ? `<div class="quote" style="margin-top:6px">${citeLink(c.description_citation)}</div>` : ""}</div>
            <div><h4>${esc(t("what_fits"))}</h4><ul class="evi-list">
              ${c.supporting.map((s) => `<li class="evi for"><span><strong>${esc(s.label)}</strong> · <span class="muted small">${esc(s.role_label)}</span></span>
                ${s.user_words.length ? `<span class="yw">“${esc(s.user_words.join("”, “"))}”</span>` : ""}${quoteBlock(s.citation)}</li>`).join("")}
            </ul></div>
            ${c.against.length ? `<div><h4>${esc(t("what_not"))}</h4><ul class="evi-list">${c.against.map((x) => `<li class="evi against"><strong>${esc(x.label)}</strong><span class="small">${esc(x.note)}</span>${quoteBlock(x.citation)}</li>`).join("")}</ul></div>` : ""}
            <div class="two-col">
              ${c.unknown.length ? `<div><h4>${esc(t("what_unknown"))}</h4><div class="pill-row">${c.unknown.map((u) => `<span class="pill">${esc(u)}</span>`).join("")}</div></div>` : ""}
              ${c.unexplained.length ? `<div><h4>${esc(t("what_unexplained"))}</h4><div class="pill-row">${c.unexplained.map((u) => `<span class="pill">${esc(u)}</span>`).join("")}</div></div>` : ""}
            </div>
            <div><h4>${esc(t("what_help"))}</h4><ul class="care-list">${c.clarify.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
            ${c.alternatives.length ? `<div><h4>${esc(t("alternatives"))}</h4><ul class="care-list">${c.alternatives.map((x) => `<li><strong>${esc(x.name)}</strong> — ${esc(x.why)}</li>`).join("")}</ul></div>` : ""}
            ${c.context_note ? `<div class="notice lvl-soon small">${esc(c.context_note.text)} ${citeLink(c.context_note.citation)}</div>` : ""}
            <div class="two-col">
              <div><h4>${esc(t("self_care"))}</h4><ul class="care-list">${c.self_care.map((x) => `<li>${esc(x.text)} ${citeLink(x.citation)}</li>`).join("")}</ul></div>
              <div><h4>${esc(t("see_doc"))}</h4><ul class="care-list">${c.see_doctor_if.map((x) => `<li>${esc(x.text)} ${citeLink(x.citation)}</li>`).join("")}</ul></div>
            </div>
            ${c.related_passages.length ? `<details class="plain"><summary>${esc(t("related"))}</summary>${c.related_passages.map((p) => `<div class="passage" style="margin-top:8px"><strong>${esc(p.section)}</strong>\n${esc(p.text)}\n<a class="cite-link" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.publisher.split(" (")[0])}: ${esc(p.title)} ↗</a></div>`).join("")}</details>` : ""}
          </div>
        </details>`).join("")}
      ${a.more_conditions.length ? `<div><h4>${esc(t("more_conds"))}</h4><div class="pill-row">${a.more_conditions.map((m) => `<span class="pill">${esc(m.name)} · ${esc(m.support)}</span>`).join("")}</div></div>` : ""}
      ${a.set_aside.length ? `<div><h4>${esc(t("set_aside"))}</h4><ul class="care-list">${a.set_aside.map((m) => `<li><strong>${esc(m.name)}</strong> — ${esc(m.reasons.filter(Boolean).join("; "))}</li>`).join("")}</ul></div>` : ""}
      <details class="plain"><summary>${esc(t("how_assessed"))}</summary><p class="small">${esc(a.method)}</p>
        <p class="small muted">${esc(t("validation"))}: ${esc(t("grounded")(a.validation.grounded, a.validation.claims))}${a.validation.issues.length ? " " + esc(a.validation.issues.join("; ")) : ""}</p></details>
      <details class="plain"><summary>${esc(t("limitations"))}</summary><ul class="care-list small">${a.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></details>
      ${a.sources.length ? `<details class="plain"><summary>${esc(t("sources"))} (${a.sources.length})</summary><div class="sources-list" style="margin-top:8px">${a.sources.map(sourceRow).join("")}</div></details>` : ""}
    </div>`;
    box.hidden = false;
    box.querySelector('[data-act="copy"]').addEventListener("click", copySummary);
    box.querySelector('[data-act="download"]').addEventListener("click", downloadSummary);
    box.querySelector('[data-act="print"]').addEventListener("click", () => window.print());
    box.scrollIntoView({ block: "start", behavior: "smooth" });
    if (a.status === "candidates") loadAiSummary();
  }

  function sourceRow(s) {
    const f = s.freshness || {};
    return `<div class="source-item"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.publisher.split(" (")[0])}: ${esc(s.title)} ↗</a>
      <span class="small muted">${s.last_reviewed ? `${esc(t("reviewed"))}: ${esc(s.last_reviewed)}` : ""}
      <span class="fresh ${esc(f.status || "unknown")}" title="${esc(f.note || "")}">${f.status === "current" ? "✓" : f.status === "unknown" ? "?" : esc(t("outdated"))}</span></span></div>`;
  }

  async function loadAiSummary() {
    const slot = $("#ai-summary");
    if (!slot) return;
    slot.innerHTML = `<p class="small muted">${esc(t("ai_loading"))}</p>`;
    try {
      const r = await api(`/api/assessments/${S.sid}/summary`, { timeout: 40000 });
      if (!$("#ai-summary")) return;
      $("#ai-summary").innerHTML = r.available ? `<div class="ai-summary"><strong class="small">${esc(t("ai_title"))}</strong><div>${esc(r.text)}</div><small>${esc(r.note)}</small></div>` : "";
    } catch { const s2 = $("#ai-summary"); if (s2) s2.innerHTML = ""; }
  }

  function summaryText() {
    const a = S.results;
    if (!a) return "";
    const L = [];
    L.push(`MediBot — ${t("res_title")} (${new Date().toLocaleString()})`, "");
    L.push(`${a.urgency.label}`);
    a.urgency.reasons.forEach((r) => L.push(`  - ${r.text}${r.citations[0] ? ` [${r.citations[0].publisher}: ${r.citations[0].url}]` : ""}`));
    L.push("", a.summary, "");
    L.push(`${t("reported")}: ${a.reported.present.map((s) => s.label).join(", ")}`);
    if (a.reported.absent.length) L.push(`${t("absent_lbl")}: ${a.reported.absent.map((s) => s.label).join(", ")}`);
    if (a.reported.duration) L.push(`${t("d_duration")}: ${a.reported.duration}`);
    a.conditions.forEach((c) => {
      L.push("", `## ${c.name} — ${c.support.label}`, c.explanation, c.support.rule);
      c.supporting.forEach((s) => L.push(`  + ${s.label}: "${s.citation.quote}" (${s.citation.publisher}, ${s.citation.url})`));
      c.against.forEach((x) => L.push(`  - ${x.label}: ${x.note}${x.citation ? ` (${x.citation.url})` : ""}`));
      L.push(`  ${t("see_doc")}:`); c.see_doctor_if.forEach((x) => L.push(`   • ${x.text}`));
    });
    L.push("", `${t("limitations")}:`); a.limitations.forEach((l) => L.push(`  • ${l}`));
    return L.join("\n");
  }
  async function copySummary() {
    try { await navigator.clipboard.writeText(summaryText()); toast(t("copied")); }
    catch { downloadSummary(); }
  }
  function downloadSummary() {
    const blob = new Blob([summaryText()], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "medibot-assessment.txt"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ── sending messages ─────────────────────────────────────────────────────
  function send() {
    const input = $("#input");
    const text = input.value.trim();
    if (!text || S.busy) return;
    input.value = ""; autoGrow();
    $("#voice-note").hidden = true;
    stopSpeaking();
    addMessage("user", text);
    guarded(async () => {
      if (!S.sid) {                              // never lose a message because no assessment was started yet
        await startAssessment();                 // (this clears the chat, so show the message again)
        addMessage("user", text);
      }
      handle(await api(`/api/assessments/${S.sid}/messages`, { method: "POST", body: { text } }));
    }, t("checking"));
  }
  function autoGrow() { const i = $("#input"); i.style.height = "auto"; i.style.height = Math.min(i.scrollHeight, 140) + "px"; }

  // ── voice: speech input (Groq Whisper via /api/voice/transcribe) ─────────
  // The recorder measures loudness locally: it stops by itself after a pause once
  // speech was heard, and it never uploads a recording in which nobody spoke
  // (silence is where speech models hallucinate). The server cross-checks the
  // transcript; it is put in the input box for review unless auto-send is on.
  const V = { state: "idle", rec: null, stream: null, ctx: null, chunks: [], raf: 0, t0: 0,
              speechMs: 0, lastSpeech: 0, floor: null, cancelled: false, mime: "" };
  const VOICE = { minSpeechMs: 350, silenceStopMs: 1800, noSpeechStopMs: 8000, maxMs: 45000 };

  function pickMime() {
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return "";
    return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find((m) => MediaRecorder.isTypeSupported(m)) || "";
  }
  function setVoiceUI(state) {
    V.state = state;
    const bar = $("#voice-bar"), btn = $("#mic-btn");
    bar.hidden = state === "idle";
    bar.classList.toggle("processing", state === "processing");
    btn.classList.toggle("recording", state === "recording");
    btn.setAttribute("aria-pressed", String(state === "recording"));
    btn.setAttribute("aria-label", state === "recording" ? t("voice_stop") : t("mic_label"));
    $("#voice-stop").hidden = state !== "recording";
    $("#voice-cancel").hidden = state === "idle";
    $("#voice-status").textContent = state === "processing" ? t("voice_processing") : t("voice_listening");
  }

  async function startRecording() {
    if (!window.isSecureContext) {
      // browsers only expose the microphone on https:// or localhost
      toast(t("mic_insecure").replace("{url}", `http://localhost:${location.port || 80}`), true, 12000);
      return;
    }
    if (!navigator.mediaDevices || !window.MediaRecorder) { toast(t("mic_unsupported"), true); return; }
    stopSpeaking();
    try {
      V.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) {
      toast(e && e.name === "NotAllowedError" ? t("mic_denied") : t("mic_err"), true);
      return;
    }
    V.mime = pickMime();
    V.rec = new MediaRecorder(V.stream, V.mime ? { mimeType: V.mime } : undefined);
    V.chunks = []; V.speechMs = 0; V.lastSpeech = 0; V.floor = null; V.cancelled = false; V.t0 = performance.now();
    V.rec.ondataavailable = (e) => { if (e.data && e.data.size) V.chunks.push(e.data); };
    V.rec.onstop = onRecordingStop;
    // loudness meter + automatic stop
    V.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = V.ctx.createMediaStreamSource(V.stream);
    const an = V.ctx.createAnalyser(); an.fftSize = 1024; src.connect(an);
    const buf = new Float32Array(an.fftSize);
    const bars = $$("#voice-level i");
    let prev = performance.now();
    const tick = (now) => {
      an.getFloatTimeDomainData(buf);
      let sum = 0; for (let k = 0; k < buf.length; k++) sum += buf[k] * buf[k];
      const rms = Math.sqrt(sum / buf.length), dt = now - prev; prev = now;
      const elapsed = now - V.t0;
      if (elapsed < 300) V.floor = V.floor == null ? rms : Math.min(V.floor, rms);     // calibrate background level
      const threshold = Math.max(0.012, (V.floor || 0) * 3);
      if (elapsed >= 300 && rms > threshold) { V.speechMs += dt; V.lastSpeech = now; }
      const level = Math.min(1, rms / 0.12);
      bars.forEach((b, k) => { b.style.transform = `scaleY(${Math.max(0.15, Math.min(1, level * (1.4 - Math.abs(k - 3) * 0.25)))})`; });
      const sec = Math.floor(elapsed / 1000);
      $("#voice-time").textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
      const heard = V.speechMs >= VOICE.minSpeechMs;
      if ((heard && now - V.lastSpeech > VOICE.silenceStopMs) || (!heard && elapsed > VOICE.noSpeechStopMs) || elapsed > VOICE.maxMs) {
        stopRecording(false);
        return;
      }
      V.raf = requestAnimationFrame(tick);
    };
    V.rec.start(250);
    setVoiceUI("recording");
    V.raf = requestAnimationFrame(tick);
  }

  function stopRecording(cancel) {
    if (!V.rec || V.rec.state !== "recording") return;
    V.cancelled = cancel;
    cancelAnimationFrame(V.raf);
    V.rec.stop();
  }

  function releaseMic() {
    if (V.stream) V.stream.getTracks().forEach((tr) => tr.stop());
    if (V.ctx) V.ctx.close().catch(() => {});
    V.stream = null; V.ctx = null; V.rec = null;
  }

  async function onRecordingStop() {
    releaseMic();
    if (V.cancelled) { setVoiceUI("idle"); return; }
    if (V.speechMs < VOICE.minSpeechMs || !V.chunks.length) { setVoiceUI("idle"); toast(t("voice_no_speech"), true); return; }
    setVoiceUI("processing");
    const type = V.mime.split(";")[0] || "audio/webm";
    const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
    const fd = new FormData();
    fd.append("audio", new Blob(V.chunks, { type }), `voice.${ext}`);
    fd.append("language", S.lang);
    if (S.sid) fd.append("session_id", S.sid);
    try {
      const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 30000);
      const res = await fetch("/api/voice/transcribe", { method: "POST", body: fd, signal: ctrl.signal });
      clearTimeout(timer);
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error((d.error && d.error.message) || t("mic_err"));
      if (!d.accepted) { toast(d.message || t("voice_no_speech"), true); return; }
      const input = $("#input");
      input.value = (input.value.trim() ? input.value.trim() + " " : "") + d.text;
      autoGrow();
      if ($("#autosend").checked) { send(); }
      else { $("#voice-note").hidden = false; input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
    } catch (e) {
      toast(e.name === "AbortError" ? t("timeout") : (e.message || t("mic_err")), true);
    } finally {
      if (V.state === "processing") setVoiceUI("idle");
    }
  }

  function toggleMic() {
    if (V.state === "recording") stopRecording(false);
    else if (V.state === "idle") startRecording();
  }

  // ── voice: reading replies aloud (browser speech synthesis) ─────────────
  // Replies are Roman-script Hinglish or English, which an Indian-English voice
  // reads most naturally; a Hindi voice would spell out the Latin letters.
  const TTS = { on: false, voice: null };
  function pickVoice() {
    const vs = window.speechSynthesis ? speechSynthesis.getVoices() : [];
    const by = (re) => vs.find((v) => re.test(v.lang));
    TTS.voice = by(/^en[-_]IN/i) || by(/^en[-_]GB/i) || by(/^en/i) || null;
  }
  function speak(text) {
    if (!TTS.on || !window.speechSynthesis || !text) return;
    const clean = text.replace(/[“”"()↗]/g, " ").replace(/\s+/g, " ").trim();
    const u = new SpeechSynthesisUtterance(clean);
    if (TTS.voice) { u.voice = TTS.voice; u.lang = TTS.voice.lang; } else u.lang = "en-IN";
    u.rate = 0.97;
    speechSynthesis.speak(u);
  }
  function stopSpeaking() { if (window.speechSynthesis) speechSynthesis.cancel(); }
  function setSpeak(on) {
    TTS.on = on; store.set("medibot_speak", on ? "1" : null);
    const b = $("#speak-btn");
    b.setAttribute("aria-pressed", String(on));
    b.setAttribute("aria-label", on ? t("speak_off") : t("speak_on"));
    b.title = on ? t("speak_off") : t("speak_on");
    if (!on) stopSpeaking();
  }
  function initVoice() {
    if (window.speechSynthesis) {
      pickVoice();
      speechSynthesis.onvoiceschanged = pickVoice;
      $("#speak-btn").hidden = false;
      setSpeak(store.get("medibot_speak") === "1");
      $("#speak-btn").addEventListener("click", () => setSpeak(!TTS.on));
    }
    $("#autosend").checked = store.get("medibot_autosend") === "1";
    $("#autosend").addEventListener("change", (e) => store.set("medibot_autosend", e.target.checked ? "1" : null));
    $("#voice-stop").addEventListener("click", () => stopRecording(false));
    $("#voice-cancel").addEventListener("click", () => stopRecording(true));
    $("#input").addEventListener("input", () => { $("#voice-note").hidden = true; });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && V.state === "recording") stopRecording(true); });
    setVoiceUI("idle");
  }

  // ── sources dialog (landing footer) ──────────────────────────────────────
  async function showSources(e) {
    e.preventDefault();
    try {
      const r = await api("/api/sources");
      const w = document.createElement("div");
      w.className = "scrim"; w.style.zIndex = 60; w.style.display = "grid"; w.style.placeItems = "center"; w.style.padding = "16px";
      w.innerHTML = `<div class="panel" role="dialog" aria-modal="true" aria-labelledby="src-t" style="max-width:720px;width:100%;max-height:85vh;overflow:auto;padding:18px">
        <div class="results-head"><h2 id="src-t" style="font-size:1.1rem;margin:0">${esc(t("sources_title"))}</h2><button class="btn btn-sm btn-outline" data-close>${esc(t("close"))}</button></div>
        <div class="sources-list" style="margin-top:12px">${r.sources.map(sourceRow).join("")}</div></div>`;
      document.body.appendChild(w);
      const close = () => w.remove();
      w.addEventListener("click", (ev) => { if (ev.target === w || ev.target.closest("[data-close]")) close(); });
      document.addEventListener("keydown", function esc_(ev) { if (ev.key === "Escape") { close(); document.removeEventListener("keydown", esc_); } });
      w.querySelector("[data-close]").focus();
    } catch (err) { toast(err.message, true); }
  }

  // ── wiring ───────────────────────────────────────────────────────────────
  function openSide(open) {
    $("#side").classList.toggle("open", open);
    let scrim = $(".scrim.side-scrim");
    if (open && !scrim && window.matchMedia("(max-width: 960px)").matches) {
      scrim = document.createElement("div"); scrim.className = "scrim side-scrim";
      scrim.addEventListener("click", () => openSide(false)); document.body.appendChild(scrim);
    } else if (!open && scrim) scrim.remove();
  }

  async function restart() {
    store.set("medibot_sid", null);
    await guarded(() => startAssessment());
  }

  // ── light / dark theme ──────────────────────────────────────────────────
  // With no saved choice the page follows the system setting (and keeps following it).
  // A choice that matches the system is not stored, so "back to automatic" is just toggling back.
  const darkQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function effectiveTheme() {
    const chosen = document.documentElement.getAttribute("data-theme");
    return chosen || (darkQuery && darkQuery.matches ? "dark" : "light");
  }
  function paintTheme() {
    const theme = effectiveTheme(), root = document.documentElement;
    root.setAttribute("data-effective-theme", theme);
    const label = theme === "dark" ? t("theme_light") : t("theme_dark");
    const btn = $("#theme-btn");
    if (btn) { btn.setAttribute("aria-label", label); btn.title = label; }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", getComputedStyle(root).getPropertyValue("--bg").trim() || (theme === "dark" ? "#062a2a" : "#efeeec"));
  }
  function toggleTheme() {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    const system = darkQuery && darkQuery.matches ? "dark" : "light";
    if (next === system) { document.documentElement.removeAttribute("data-theme"); store.set("medibot_theme", null); }
    else { document.documentElement.setAttribute("data-theme", next); store.set("medibot_theme", next); }
    paintTheme();
  }

  function init() {
    S.lang = store.get("medibot_lang") || "hi";
    paintTheme();
    $("#theme-btn").addEventListener("click", toggleTheme);
    if (darkQuery && darkQuery.addEventListener) darkQuery.addEventListener("change", paintTheme);
    applyStatic();
    api("/api/meta").then((m) => { S.meta = m; if (S.last) renderSide(S.last); }).catch(() => {});

    $$(".lang-toggle button").forEach((b) => b.addEventListener("click", () => setLanguage(b.dataset.lang)));
    $("#start-btn").addEventListener("click", () => guarded(async () => {
      const saved = store.get("medibot_sid");
      if (saved) { try { await resume(saved); return; } catch { store.set("medibot_sid", null); } }
      await startAssessment();
    }));
    $("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
    $("#input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
    $("#input").addEventListener("input", autoGrow);
    $("#mic-btn").addEventListener("click", toggleMic);
    initVoice();
    $("#assess-now").addEventListener("click", () => guarded(async () => {
      $$(".qcard").forEach((c) => c.remove());
      handle(await api(`/api/assessments/${S.sid}/assessment`, { method: "POST" }));
    }, t("building")));
    $("#restart-btn").addEventListener("click", restart);
    $("#restart-btn-2").addEventListener("click", restart);
    $("#home-link").addEventListener("click", (e) => { e.preventDefault(); showLanding(); });
    $("#sources-link").addEventListener("click", showSources);
    $("#summary-toggle").addEventListener("click", () => openSide(!$("#side").classList.contains("open")));
    $("#side-close").addEventListener("click", () => openSide(false));

    $("#sym-list").addEventListener("change", (e) => {
      const sel = e.target.closest("select[data-sym]");
      if (sel) guarded(async () => handle(await api(`/api/assessments/${S.sid}/symptoms/${sel.dataset.sym}`, { method: "PATCH", body: { status: sel.value } })));
    });
    $("#sym-list").addEventListener("click", (e) => {
      const b = e.target.closest("[data-rm]");
      if (b) guarded(async () => handle(await api(`/api/assessments/${S.sid}/symptoms/${b.dataset.rm}`, { method: "DELETE" })));
    });
    $("#add-symptom-btn").addEventListener("click", () => {
      const id = $("#add-symptom").value;
      if (id) guarded(async () => handle(await api(`/api/assessments/${S.sid}/symptoms`, { method: "POST", body: { symptoms: [{ id, status: "present" }] } })));
    });
    $("#details").addEventListener("change", (e) => {
      const sel = e.target.closest("select[data-attr]");
      if (sel) guarded(async () => handle(await api(`/api/assessments/${S.sid}/attributes`, { method: "PATCH", body: { name: sel.dataset.attr, value: sel.value || null } })));
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
