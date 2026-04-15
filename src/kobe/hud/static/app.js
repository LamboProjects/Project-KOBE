/* =========================================================
   KOBE HUD — Phase 2 frontend controller
   Vanilla JS. No build step.
   ========================================================= */
(function () {
  "use strict";

  // ---------- Constants ----------
  const VALID_STATES = new Set(["idle", "listening", "thinking", "speaking", "muted"]);
  const STATE_LABELS = {
    idle:      { label: "KOBE · IDLE",   sub: "awaiting wake word" },
    listening: { label: "LISTENING",     sub: "capturing audio"    },
    thinking:  { label: "THINKING",      sub: "reasoning"          },
    speaking:  { label: "SPEAKING",      sub: "synthesizing reply" },
    muted:     { label: "MUTED",         sub: "microphone disabled"},
  };
  const TRANSCRIPT_MAX = 8;
  const RECONNECT_SCHEDULE = [1000, 2000, 4000, 8000, 15000];
  const VALID_PRINTER_STAGES = new Set([
    "idle", "preparing", "printing", "paused", "finished", "failed", "unknown",
  ]);
  const PRINTER_FILENAME_MAX = 40;
  const CONFIRM_SAFETY_TIMEOUT_MS = 15000;
  const CONFIRM_RESULT_FADE_MS = 2200;
  const VISION_SHIMMER_SAFETY_MS = 45000;
  const GESTURE_FLASH_MS = 700;

  // Fixed lookup — server values can never become HTML. Keys must match
  // kobe.events.GestureDetected.name vocabulary.
  const GESTURE_MAP = {
    swipe_left:  { glyph: "\u2190", label: "SWIPE LEFT",  accent: "cyan"    },
    swipe_right: { glyph: "\u2192", label: "SWIPE RIGHT", accent: "cyan"    },
    point:       { glyph: "\u261D", label: "POINT",       accent: "magenta" },
    confirm:     { glyph: "\u2713", label: "CONFIRM",     accent: "green"   },
    dismiss:     { glyph: "\u2715", label: "DISMISS",     accent: "red"     },
  };

  // ---------- DOM refs ----------
  const $ = (id) => document.getElementById(id);
  const el = {
    statePanel:      $("state-panel"),
    stateLabel:      $("state-label"),
    stateSub:        $("state-sub"),
    clockTime:       $("clock-time"),
    clockDate:       $("clock-date"),
    clockTz:         $("clock-tz"),
    transcriptList:  $("transcript-list"),
    transcriptCount: $("transcript-count"),
    responseBody:    $("response-body"),
    responseMeta:    $("response-meta"),
    cpuValue:        $("cpu-value"),
    cpuFill:         $("cpu-fill"),
    memValue:        $("mem-value"),
    memFill:         $("mem-fill"),
    sysFg:           $("system-fg"),
    sysFgFull:       $("system-fg-full"),
    connIndicator:   $("conn-indicator"),
    connLabel:       $("conn-label"),
    // Printer
    printerPanel:    $("printer-panel"),
    printerStage:    $("printer-stage"),
    printerFile:     $("printer-file"),
    printerProgVal:  $("printer-progress-value"),
    printerProgFill: $("printer-progress-fill"),
    printerEta:      $("printer-eta"),
    printerTemps:    $("printer-temps"),
    printerConnLbl:  $("printer-conn-label"),
    // Now playing
    npPanel:         $("nowplaying-panel"),
    npPlaceholder:   $("nowplaying-placeholder"),
    npActive:        $("nowplaying-active"),
    npTrack:         $("np-track"),
    npArtist:        $("np-artist"),
    npAlbum:         $("np-album"),
    npProgFill:      $("np-progress-fill"),
    npElapsed:       $("np-elapsed"),
    npDuration:      $("np-duration"),
    npLiveLabel:     $("nowplaying-live-label"),
    // Confirmation banner
    confirmBanner:   $("confirm-banner"),
    confirmPrompt:   $("confirm-prompt"),
    confirmResult:   $("confirm-result"),
    // Vision
    visionPanel:       $("vision-panel"),
    visionStatus:      $("vision-status"),
    visionPlaceholder: $("vision-placeholder"),
    visionContent:     $("vision-content"),
    visionQuestion:    $("vision-question"),
    visionSummary:     $("vision-summary"),
    visionMeta:        $("vision-meta"),
    // Gestures / webcam
    gesturesPanel:     $("gestures-panel"),
    gesturesBadge:     $("gestures-badge"),
    gesturesGlyph:     $("gestures-glyph"),
    gesturesLabel:     $("gestures-label"),
    gesturesMeta:      $("gestures-meta"),
    gesturesFrames:    $("gestures-frames"),
    gesturesFps:       $("gestures-fps"),
    gesturesCamLabel:  $("gestures-cam-label"),
  };

  // ---------- Clock (the only JS-driven poll) ----------
  const DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  const MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function updateClock() {
    const now = new Date();
    el.clockTime.textContent =
      pad(now.getHours()) + ":" + pad(now.getMinutes()) + ":" + pad(now.getSeconds());
    el.clockDate.textContent =
      DAYS[now.getDay()] + " · " +
      pad(now.getDate()) + " " + MONTHS[now.getMonth()] + " " + now.getFullYear();
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "LOCAL";
      el.clockTz.textContent = tz.toUpperCase();
    } catch (_) {
      el.clockTz.textContent = "LOCAL";
    }
  }
  updateClock();
  setInterval(updateClock, 1000);

  // ---------- State ----------
  let currentState = "idle";
  const transcript = []; // newest first

  function setState(next) {
    if (!VALID_STATES.has(next)) return;
    if (next === currentState) return;
    currentState = next;
    el.statePanel.setAttribute("data-state", next);
    const meta = STATE_LABELS[next];
    el.stateLabel.textContent = meta.label;
    el.stateSub.textContent = meta.sub;
  }

  // ---------- Transcript ----------
  function formatTime(tsMs) {
    const d = tsMs ? new Date(tsMs) : new Date();
    return pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
  }

  function addTranscript(text, tsMs) {
    if (!text) return;
    transcript.unshift({ text: String(text), time: formatTime(tsMs) });
    while (transcript.length > TRANSCRIPT_MAX) transcript.pop();
    renderTranscript();
  }

  function renderTranscript() {
    const list = el.transcriptList;
    list.innerHTML = "";
    if (transcript.length === 0) {
      const li = document.createElement("li");
      li.className = "placeholder";
      li.textContent = "— NO SIGNAL —";
      list.appendChild(li);
      el.transcriptCount.textContent = "0 / " + TRANSCRIPT_MAX;
      return;
    }
    for (const item of transcript) {
      const li = document.createElement("li");
      const t = document.createElement("span");
      t.className = "trans-time";
      t.textContent = item.time;
      const x = document.createElement("span");
      x.className = "trans-text";
      x.textContent = item.text;
      li.appendChild(t);
      li.appendChild(x);
      list.appendChild(li);
    }
    el.transcriptCount.textContent = transcript.length + " / " + TRANSCRIPT_MAX;
  }

  // ---------- Response ----------
  function setResponse(text, tsMs) {
    if (!text) return;
    const body = el.responseBody;
    body.innerHTML = "";
    const div = document.createElement("div");
    div.className = "response-text";
    div.textContent = String(text);
    body.appendChild(div);
    el.responseMeta.textContent = formatTime(tsMs);
  }

  // ---------- System ----------
  function setSystem(data) {
    if (!data || typeof data !== "object") return;

    if (typeof data.foreground_app === "string" && data.foreground_app.length) {
      const fg = data.foreground_app;
      el.sysFg.textContent = fg.length > 24 ? fg.slice(0, 24) + "…" : fg;
      el.sysFgFull.textContent = fg;
    }
    if (typeof data.cpu_percent === "number") {
      const pct = Math.max(0, Math.min(100, data.cpu_percent));
      el.cpuValue.textContent = pct.toFixed(0) + "%";
      el.cpuFill.style.width = pct + "%";
      el.cpuFill.setAttribute("data-level", pct >= 80 ? "high" : "ok");
    }
    if (typeof data.memory_percent === "number") {
      const pct = Math.max(0, Math.min(100, data.memory_percent));
      el.memValue.textContent = pct.toFixed(0) + "%";
      el.memFill.style.width = pct + "%";
      el.memFill.setAttribute("data-level", pct >= 85 ? "high" : "ok");
    }
  }

  // ---------- Printer ----------
  function truncate(s, max) {
    if (!s) return "";
    s = String(s);
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  }

  function formatRemaining(minutesAny) {
    if (typeof minutesAny !== "number" || !isFinite(minutesAny) || minutesAny <= 0) {
      return "—";
    }
    const total = Math.max(0, Math.round(minutesAny * 60));
    const mm = Math.floor(total / 60);
    const ss = total % 60;
    return pad(mm) + ":" + pad(ss);
  }

  function setPrinter(data) {
    if (!data || typeof data !== "object") return;

    if (typeof data.connected === "boolean") {
      el.printerPanel.setAttribute("data-connected", data.connected ? "true" : "false");
      el.printerConnLbl.textContent = data.connected ? "ONLINE" : "OFFLINE";
    }

    let stage = typeof data.stage === "string" ? data.stage.toLowerCase() : "unknown";
    if (!VALID_PRINTER_STAGES.has(stage)) stage = "unknown";
    el.printerPanel.setAttribute("data-stage", stage);
    el.printerStage.textContent = stage.toUpperCase();

    if (typeof data.progress_pct === "number") {
      const pct = Math.max(0, Math.min(100, data.progress_pct));
      el.printerProgVal.textContent = pct.toFixed(0) + "%";
      el.printerProgFill.style.width = pct + "%";
    }

    // Remaining: idle → em-dash.
    if (stage === "idle" || stage === "finished" || stage === "unknown") {
      el.printerEta.textContent = "—";
    } else {
      el.printerEta.textContent = formatRemaining(data.remaining_minutes);
    }

    const nozzle = (typeof data.nozzle_temp_c === "number") ? Math.round(data.nozzle_temp_c) : null;
    const bed    = (typeof data.bed_temp_c === "number")    ? Math.round(data.bed_temp_c)    : null;
    if (nozzle !== null || bed !== null) {
      el.printerTemps.textContent =
        (nozzle !== null ? nozzle + "°C" : "—°C") +
        " / " +
        (bed !== null ? bed + "°C" : "—°C");
    }

    if (typeof data.filename === "string") {
      el.printerFile.textContent = data.filename ? truncate(data.filename, PRINTER_FILENAME_MAX) : "— no job —";
    }
  }

  // ---------- Now playing ----------
  function formatMs(ms) {
    if (typeof ms !== "number" || !isFinite(ms) || ms < 0) return "0:00";
    const total = Math.floor(ms / 1000);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return m + ":" + pad(s);
  }

  function setNowPlaying(data) {
    if (!data || typeof data !== "object") return;
    const playing = !!data.is_playing;
    el.npPanel.setAttribute("data-playing", playing ? "true" : "false");
    el.npLiveLabel.textContent = playing ? "LIVE" : "IDLE";

    if (!playing) {
      el.npActive.hidden = true;
      el.npPlaceholder.style.display = "";
      return;
    }

    el.npActive.hidden = false;
    el.npPlaceholder.style.display = "none";

    el.npTrack.textContent = data.track ? String(data.track) : "—";
    el.npArtist.textContent = data.artist ? String(data.artist) : "—";
    el.npAlbum.textContent = data.album ? String(data.album) : "";

    const progMs = (typeof data.progress_ms === "number") ? data.progress_ms : 0;
    const durMs  = (typeof data.duration_ms === "number" && data.duration_ms > 0) ? data.duration_ms : 0;
    const pct = durMs > 0 ? Math.max(0, Math.min(100, (progMs / durMs) * 100)) : 0;
    el.npProgFill.style.width = pct + "%";
    el.npElapsed.textContent = formatMs(progMs);
    el.npDuration.textContent = formatMs(durMs);
  }

  // ---------- Vision (last screen-inspection result) ----------
  const vision = {
    lastQuestion: "",      // from most recent VisionRequested, cleared by next VisionResult
    scanning: false,       // shimmer overlay on/off
    lastResult: null,      // last VisionResult payload (or null)
  };
  let visionShimmerTimer = null;

  function formatVisionTime(iso) {
    if (!iso) return formatTime();
    const d = new Date(iso);
    if (isNaN(d.getTime())) return formatTime();
    return pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
  }

  function renderVision() {
    el.visionPanel.setAttribute("data-scanning", vision.scanning ? "true" : "false");

    const r = vision.lastResult;
    if (!r) {
      el.visionPanel.setAttribute("data-status", "empty");
      el.visionStatus.textContent = "—";
      el.visionContent.hidden = true;
      el.visionPlaceholder.style.display = "";
      // Question line is meaningless without a backing scan; suppress.
      el.visionQuestion.hidden = true;
      el.visionQuestion.textContent = "";
      return;
    }

    el.visionPanel.setAttribute("data-status", r.ok ? "ok" : "error");
    el.visionStatus.textContent = r.backend ? String(r.backend).toUpperCase() : (r.ok ? "OK" : "ERROR");

    el.visionPlaceholder.style.display = "none";
    el.visionContent.hidden = false;

    el.visionSummary.textContent = r.summary ? String(r.summary) : "(no summary)";

    const w = (typeof r.width === "number" && r.width > 0) ? r.width : null;
    const h = (typeof r.height === "number" && r.height > 0) ? r.height : null;
    const dims = (w && h) ? (w + "×" + h) : "—";
    const tag  = r.context_name ? String(r.context_name).toUpperCase()
                                : (r.backend ? String(r.backend).toUpperCase()
                                : (r.mode ? String(r.mode).toUpperCase() : "—"));
    el.visionMeta.textContent = dims + " · " + tag + " · " + formatVisionTime(r.timestamp_iso);

    if (vision.lastQuestion) {
      el.visionQuestion.hidden = false;
      el.visionQuestion.textContent = "Q: " + vision.lastQuestion;
    } else {
      el.visionQuestion.hidden = true;
      el.visionQuestion.textContent = "";
    }
  }

  function onVisionRequested(data) {
    if (!data || typeof data !== "object") return;
    vision.lastQuestion = typeof data.question === "string" ? data.question : "";
    vision.scanning = true;
    // Shimmer safety: if no matching VisionResult lands, auto-clear after a grace window.
    if (visionShimmerTimer) { clearTimeout(visionShimmerTimer); visionShimmerTimer = null; }
    visionShimmerTimer = setTimeout(function () {
      visionShimmerTimer = null;
      vision.scanning = false;
      renderVision();
    }, VISION_SHIMMER_SAFETY_MS);
    // If we already have a prior result, the question overlays it; otherwise placeholder + shimmer.
    renderVision();
  }

  function onVisionResult(data) {
    if (!data || typeof data !== "object") return;
    vision.scanning = false;
    if (visionShimmerTimer) { clearTimeout(visionShimmerTimer); visionShimmerTimer = null; }
    vision.lastResult = {
      ok:            !!data.ok,
      summary:       typeof data.summary === "string" ? data.summary : "",
      width:         typeof data.width === "number" ? data.width : 0,
      height:        typeof data.height === "number" ? data.height : 0,
      backend:       typeof data.backend === "string" ? data.backend : "",
      mode:          typeof data.mode === "string" ? data.mode : "",
      context_name:  typeof data.context_name === "string" ? data.context_name : "",
      timestamp_iso: typeof data.timestamp_iso === "string" ? data.timestamp_iso : "",
    };
    renderVision();
  }

  // ---------- Gestures / webcam ----------
  // Last-detected gesture persists until replaced; webcam stats update live.
  const gestures = {
    last: null,       // { glyph, label, accent, meta }
    connected: false, // from WebcamStatus
    fps: null,
    frameCount: null,
  };
  let gestureFlashTimer = null;

  function renderGesturesBadge() {
    const g = gestures.last;
    if (!g) {
      el.gesturesPanel.setAttribute("data-accent", "none");
      el.gesturesBadge.setAttribute("data-empty", "true");
      el.gesturesGlyph.textContent = "\u2014"; // em-dash placeholder
      el.gesturesLabel.textContent = "— no gesture yet —";
      el.gesturesMeta.textContent = "—";
      return;
    }
    el.gesturesPanel.setAttribute("data-accent", g.accent);
    el.gesturesBadge.setAttribute("data-empty", "false");
    el.gesturesGlyph.textContent = g.glyph;
    el.gesturesLabel.textContent = g.label;
    el.gesturesMeta.textContent = g.meta;
  }

  function renderGesturesWebcam() {
    el.gesturesPanel.setAttribute("data-connected", gestures.connected ? "true" : "false");
    el.gesturesCamLabel.textContent = gestures.connected ? "ONLINE" : "OFFLINE";
    el.gesturesFps.textContent =
      (typeof gestures.fps === "number" && isFinite(gestures.fps))
        ? gestures.fps.toFixed(0) + " FPS"
        : "— FPS";
    el.gesturesFrames.textContent =
      (typeof gestures.frameCount === "number" && isFinite(gestures.frameCount))
        ? String(gestures.frameCount)
        : "—";
  }

  function onGestureDetected(data) {
    if (!data || typeof data !== "object") return;
    const name = typeof data.name === "string" ? data.name : "";
    const spec = Object.prototype.hasOwnProperty.call(GESTURE_MAP, name)
      ? GESTURE_MAP[name]
      : null;
    if (!spec) return; // Unknown gestures are ignored (keeps badge stable).

    const hand = typeof data.hand === "string" && data.hand ? data.hand : "unknown";
    const confRaw = typeof data.confidence === "number" ? data.confidence : 0;
    const conf = Math.max(0, Math.min(1, confRaw));
    const meta =
      hand.toUpperCase() + " hand · conf " +
      (conf * 100).toFixed(0) + "% · " +
      formatVisionTime(data.timestamp_iso);

    gestures.last = {
      glyph: spec.glyph,
      label: spec.label,
      accent: spec.accent,
      meta: meta,
    };
    renderGesturesBadge();

    // Fade-flash pulse (mirrors confirmation-result timing pattern).
    if (gestureFlashTimer) { clearTimeout(gestureFlashTimer); gestureFlashTimer = null; }
    el.gesturesBadge.setAttribute("data-flash", "true");
    gestureFlashTimer = setTimeout(function () {
      el.gesturesBadge.removeAttribute("data-flash");
      gestureFlashTimer = null;
    }, GESTURE_FLASH_MS);
  }

  function onWebcamStatus(data) {
    if (!data || typeof data !== "object") return;
    if (typeof data.connected === "boolean") gestures.connected = data.connected;
    if (typeof data.fps === "number" && isFinite(data.fps)) gestures.fps = data.fps;
    if (typeof data.frame_count === "number" && isFinite(data.frame_count)) {
      gestures.frameCount = data.frame_count;
    }
    renderGesturesWebcam();
  }

  // ---------- Confirmation banner ----------
  let confirmActiveId = null;
  let confirmSafetyTimer = null;
  let confirmFadeTimer = null;

  function clearConfirmTimers() {
    if (confirmSafetyTimer) { clearTimeout(confirmSafetyTimer); confirmSafetyTimer = null; }
    if (confirmFadeTimer)   { clearTimeout(confirmFadeTimer);   confirmFadeTimer = null; }
  }

  function hideConfirm() {
    clearConfirmTimers();
    confirmActiveId = null;
    el.confirmBanner.setAttribute("data-status", "hidden");
    el.confirmBanner.setAttribute("aria-hidden", "true");
    el.confirmResult.textContent = "";
  }

  function showConfirmPrompt(data) {
    if (!data || typeof data !== "object") return;
    clearConfirmTimers();
    confirmActiveId = data.request_id || null;
    el.confirmPrompt.textContent = String(data.prompt || "Confirm?");
    el.confirmResult.textContent = "";
    el.confirmBanner.setAttribute("data-status", "prompt");
    el.confirmBanner.setAttribute("aria-hidden", "false");
    // Safety auto-clear.
    confirmSafetyTimer = setTimeout(hideConfirm, CONFIRM_SAFETY_TIMEOUT_MS);
  }

  function showConfirmResult(data) {
    if (!data || typeof data !== "object") return;
    // Only react if there's an active prompt (or one just expired but we got a tardy result).
    clearConfirmTimers();
    const confirmed = !!data.confirmed;
    el.confirmResult.textContent = confirmed ? "CONFIRMED" : "DENIED";
    el.confirmBanner.setAttribute("data-status", confirmed ? "confirmed" : "denied");
    el.confirmBanner.setAttribute("aria-hidden", "false");
    confirmFadeTimer = setTimeout(hideConfirm, CONFIRM_RESULT_FADE_MS);
  }

  // ---------- Message dispatch ----------
  function handleMessage(msg) {
    if (!msg || typeof msg !== "object") return;
    const type = msg.type;
    const data = msg.data || {};

    // Every message can carry a state; trust it.
    if (typeof msg.state === "string") setState(msg.state);

    switch (type) {
      case "HudSnapshot": {
        // Optional hydration payload
        if (Array.isArray(data.transcript)) {
          // Backend may send newest-first or oldest-first; we assume newest-first.
          transcript.length = 0;
          for (const t of data.transcript.slice(0, TRANSCRIPT_MAX)) {
            transcript.push({
              text: String(t.text || ""),
              time: formatTime(t.ts || t.timestamp),
            });
          }
          renderTranscript();
        }
        if (data.response && data.response.text) {
          setResponse(data.response.text, data.response.ts);
        }
        if (data.system) setSystem(data.system);
        if (data.printer) setPrinter(data.printer);
        if (data.now_playing) setNowPlaying(data.now_playing);
        if (data.vision) onVisionResult(data.vision);
        // Snapshot may or may not carry these — graceful no-op when absent.
        if (data.webcam) onWebcamStatus(data.webcam);
        if (data.gesture) onGestureDetected(data.gesture);
        break;
      }

      case "TranscriptReady":
        addTranscript(data.text, data.ts || data.timestamp);
        break;

      case "ResponseReady":
        setResponse(data.text, data.ts || data.timestamp);
        break;

      case "SystemStatus":
        setSystem(data);
        break;

      case "PrinterStatus":
        setPrinter(data);
        break;

      case "PrinterAlert":
        // Purely informational for now — stage updates arrive via PrinterStatus.
        break;

      case "NowPlayingChanged":
        setNowPlaying(data);
        break;

      case "ConfirmationRequested":
        showConfirmPrompt(data);
        break;

      case "ConfirmationResult":
        showConfirmResult(data);
        break;

      case "VisionRequested":
        onVisionRequested(data);
        break;

      case "VisionResult":
        onVisionResult(data);
        break;

      case "GestureDetected":
        onGestureDetected(data);
        break;

      case "WebcamStatus":
        onWebcamStatus(data);
        break;

      case "MuteToggled":
        // State already updated via msg.state if present; fallback:
        if (typeof msg.state !== "string" && typeof data.muted === "boolean") {
          setState(data.muted ? "muted" : "idle");
        }
        break;

      // These are primarily state-bearing; msg.state handles them.
      case "WakeDetected":
      case "ActionRequested":
        // Phase 5: gesture-driven HUD navigation. Other action namespaces
        // (open_app, bambu_*, spotify_*, etc.) are handled server-side.
        if (data && typeof data.action === "string" && data.action.startsWith("hud_")) {
          onHudNavAction(data.action);
        }
        break;

      case "RecordingStarted":
      case "RecordingStopped":
      case "SpeakStarted":
      case "SpeakFinished":
      case "ActionCompleted":
      default:
        // no extra handling
        break;
    }
  }

  // ---------- HUD navigation (gesture-driven) ----------
  // The gesture service publishes ActionRequested with the names below; the
  // backend relays every event to clients, so we can handle them here without
  // a server-side executor. Cycles a `data-focused` attribute across the
  // user-visible panels so the user can see which one a `select`/`confirm`
  // would act on. `dismiss` clears the focus. `select`/`confirm` flash it.
  //
  // Panels are looked up by CSS class because some of them (response, system,
  // transcript) don't have ids — they're class-only on `<section class="panel
  // <name>-panel">`. Using classes also means the cycle automatically picks
  // up the actually-rendered panels rather than ghost ids.
  const HUD_NAV_PANEL_CLASSES = [
    "state-panel",
    "transcript-panel",
    "response-panel",
    "system-panel",
    "printer-panel",
    "nowplaying-panel",
    "vision-panel",
    "gestures-panel",
  ];
  let hudNavIndex = -1;
  let hudFlashTimer = null;
  const HUD_NAV_FLASH_MS = 800;

  function _hudResolvedPanels() {
    // Resolve once per call so a node added later (none today, but cheap) can
    // still join the cycle. Filters out misses so the cycle never has a dead
    // stop.
    const out = [];
    for (const cls of HUD_NAV_PANEL_CLASSES) {
      const node = document.querySelector("." + cls);
      if (node) out.push(node);
    }
    return out;
  }

  function _hudFocusedEl() {
    const panels = _hudResolvedPanels();
    if (hudNavIndex < 0 || hudNavIndex >= panels.length) return null;
    return panels[hudNavIndex];
  }

  function _hudClearAllFocus() {
    for (const node of _hudResolvedPanels()) {
      node.removeAttribute("data-focused");
      node.removeAttribute("data-flash");
    }
  }

  function _hudApplyFocus() {
    _hudClearAllFocus();
    const node = _hudFocusedEl();
    if (node) node.setAttribute("data-focused", "true");
  }

  function onHudNavAction(action) {
    const n = _hudResolvedPanels().length;
    if (n === 0) return;
    if (action === "hud_navigate_next") {
      hudNavIndex = hudNavIndex < 0 ? 0 : (hudNavIndex + 1) % n;
      _hudApplyFocus();
    } else if (action === "hud_navigate_prev") {
      hudNavIndex = hudNavIndex < 0 ? n - 1 : (hudNavIndex - 1 + n) % n;
      _hudApplyFocus();
    } else if (action === "hud_select" || action === "hud_confirm") {
      const node = _hudFocusedEl();
      if (!node) return;
      if (hudFlashTimer) { clearTimeout(hudFlashTimer); hudFlashTimer = null; }
      node.setAttribute("data-flash", "true");
      hudFlashTimer = setTimeout(function () {
        node.removeAttribute("data-flash");
        hudFlashTimer = null;
      }, HUD_NAV_FLASH_MS);
    } else if (action === "hud_dismiss") {
      hudNavIndex = -1;
      if (hudFlashTimer) { clearTimeout(hudFlashTimer); hudFlashTimer = null; }
      _hudClearAllFocus();
    }
  }

  // ---------- Connection indicator ----------
  function setConn(status, label) {
    el.connIndicator.setAttribute("data-status", status);
    el.connLabel.textContent = label;
  }

  // ---------- WebSocket with backoff reconnect ----------
  let ws = null;
  let reconnectIdx = 0;
  let reconnectTimer = null;
  let manuallyClosed = false;

  function wsUrl() {
    const proto = (location.protocol === "https:") ? "wss:" : "ws:";
    // Fall back to a sensible default if served from file:// during local preview.
    const host = location.host || "localhost:8765";
    return proto + "//" + host + "/ws";
  }

  function connect() {
    clearTimeout(reconnectTimer);
    setConn("connecting", "CONNECTING");

    try {
      ws = new WebSocket(wsUrl());
    } catch (err) {
      scheduleReconnect();
      return;
    }

    ws.onopen = function () {
      reconnectIdx = 0;
      setConn("connected", "LINK OK");
    };

    ws.onmessage = function (ev) {
      let msg;
      try { msg = JSON.parse(ev.data); }
      catch (_) { return; }
      handleMessage(msg);
    };

    ws.onerror = function () {
      // error will usually be followed by close; handle there.
    };

    ws.onclose = function () {
      if (manuallyClosed) return;
      setConn("disconnected", "DISCONNECTED");
      scheduleReconnect();
    };
  }

  function scheduleReconnect() {
    // Defensive: if two sources both triggered reconnect, don't stack timers.
    clearTimeout(reconnectTimer);
    const delay = RECONNECT_SCHEDULE[Math.min(reconnectIdx, RECONNECT_SCHEDULE.length - 1)];
    reconnectIdx++;
    setConn("connecting", "RETRY " + Math.round(delay / 1000) + "s");
    reconnectTimer = setTimeout(connect, delay);
  }

  // Clean shutdown on unload
  window.addEventListener("beforeunload", function () {
    manuallyClosed = true;
    if (ws) try { ws.close(); } catch (_) {}
  });

  // ---------- Boot ----------
  renderTranscript();
  renderVision();
  renderGesturesBadge();
  renderGesturesWebcam();
  connect();
})();
