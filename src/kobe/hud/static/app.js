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

      case "MuteToggled":
        // State already updated via msg.state if present; fallback:
        if (typeof msg.state !== "string" && typeof data.muted === "boolean") {
          setState(data.muted ? "muted" : "idle");
        }
        break;

      // These are primarily state-bearing; msg.state handles them.
      case "WakeDetected":
      case "RecordingStarted":
      case "RecordingStopped":
      case "SpeakStarted":
      case "SpeakFinished":
      case "ActionRequested":
      case "ActionCompleted":
      default:
        // no extra handling
        break;
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
  connect();
})();
