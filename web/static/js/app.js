/**
 * Talk Head — full-screen avatar + collapsible chat sidebar.
 */

const statusPill = document.getElementById("statusPill");
const statusText = document.getElementById("statusText");
const chatLog = document.getElementById("chatLog");
const chatPanel = document.getElementById("chatPanel");
const settingsPanel = document.getElementById("settingsPanel");
const settingsBtn = document.getElementById("settingsBtn");
const settingsBack = document.getElementById("settingsBack");
const sidebarTitle = document.getElementById("sidebarTitle");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
const sidebarClose = document.getElementById("sidebarClose");
const composer = document.getElementById("composer");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const clearBtn = document.getElementById("clearBtn");
const voiceSelect = document.getElementById("voiceSelect");
const langSelect = document.getElementById("langSelect");
const avatarModelSelect = document.getElementById("avatarModelSelect");
const moodSelect = document.getElementById("moodSelect");
const listenRing = document.getElementById("listenRing");
const avatarLoader = document.getElementById("avatarLoader");
const avatarLoaderText = document.getElementById("avatarLoaderText");
const aiCaption = document.getElementById("aiCaption");
const aiCaptionText = document.getElementById("aiCaptionText");

const fetchOpts = { credentials: "include" };

let avatar = null;
let sessionId = null;
let currentUser = null;
let busy = false;
let recognition = null;
let uiReady = false;
let settingsOpen = false;
let captionTimers = [];
/** How long the on-avatar caption stays visible after TTS finishes. */
const CAPTION_HOLD_AFTER_SPEECH_MS = 2500;

async function unlockAudioFromGesture() {
  if (!avatar?.unlockAudio) return false;
  try {
    await avatar.unlockAudio();
    return true;
  } catch (e) {
    console.warn("unlockAudio:", e.message);
    return false;
  }
}

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

const isIOS =
  /iPad|iPhone|iPod/.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

/** @type {'browser' | 'server' | 'none'} */
let speechMode = "none";
let mediaStream = null;
let mediaRecorder = null;
let recordChunks = [];
let recording = false;

const mobileChatFab = document.getElementById("mobileChatFab");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const mobileMq = window.matchMedia("(max-width: 768px)");

function isMobileLayout() {
  return mobileMq.matches;
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
  if (mobileChatFab) {
    mobileChatFab.setAttribute("aria-expanded", String(!collapsed));
  }
  if (sidebarBackdrop) {
    if (isMobileLayout() && !collapsed) {
      sidebarBackdrop.hidden = false;
    } else {
      sidebarBackdrop.hidden = true;
    }
  }
  requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
}

function toggleChatPanel() {
  const wasCollapsed = document.body.classList.contains("sidebar-collapsed");
  setSidebarCollapsed(!wasCollapsed);
  if (wasCollapsed && textInput && isMobileLayout()) {
    requestAnimationFrame(() => textInput.focus());
  }
}

function clearCaptionTimers() {
  captionTimers.forEach((id) => clearTimeout(id));
  captionTimers = [];
}

function hideAiCaption() {
  clearCaptionTimers();
  aiCaption.classList.remove("ai-caption--visible");
  aiCaption.hidden = true;
  aiCaptionText.textContent = "";
}

function scheduleHideAiCaption(delayMs = CAPTION_HOLD_AFTER_SPEECH_MS) {
  clearCaptionTimers();
  const id = setTimeout(() => {
    captionTimers = captionTimers.filter((t) => t !== id);
    aiCaption.classList.remove("ai-caption--visible");
    aiCaption.hidden = true;
    aiCaptionText.textContent = "";
  }, delayMs);
  captionTimers.push(id);
}

/** Reveal reply word-by-word in sync with TTS duration. */
function streamAiCaption(text, durationMs) {
  clearCaptionTimers();
  const full = (text || "").trim();
  const words = full.split(/\s+/).filter(Boolean);
  if (!words.length || durationMs <= 0) {
    hideAiCaption();
    return Promise.resolve();
  }

  aiCaption.hidden = false;
  aiCaptionText.textContent = "";
  requestAnimationFrame(() => aiCaption.classList.add("ai-caption--visible"));

  const weights = words.map((w) => Math.max(1, [...w].length));
  const total = weights.reduce((a, b) => a + b, 0) || 1;
  const shown = [];

  return new Promise((resolve) => {
    let cursor = 0;
    for (let i = 0; i < words.length; i++) {
      const t = cursor;
      captionTimers.push(
        setTimeout(() => {
          shown.push(words[i]);
          aiCaptionText.textContent = shown.join(" ");
        }, t)
      );
      cursor += (weights[i] / total) * durationMs;
    }

    captionTimers.push(
      setTimeout(() => {
        aiCaptionText.textContent = full;
        captionTimers.push(
          setTimeout(() => {
            scheduleHideAiCaption();
            resolve();
          }, CAPTION_HOLD_AFTER_SPEECH_MS)
        );
      }, durationMs + 80)
    );
  });
}

function openSettings() {
  settingsOpen = true;
  chatPanel.hidden = true;
  settingsPanel.hidden = false;
  sidebarTitle.textContent = "Settings";
  settingsBtn.setAttribute("aria-pressed", "true");
}

function closeSettings() {
  settingsOpen = false;
  chatPanel.hidden = false;
  settingsPanel.hidden = true;
  sidebarTitle.textContent = "Chat";
  settingsBtn.setAttribute("aria-pressed", "false");
}

function setStatus(state, label) {
  statusPill.dataset.state = state;
  statusText.textContent = label;
  if (avatar) {
    if (state === "thinking") avatar.startThinking();
    else if (state !== "speaking") avatar.stopThinking();
    avatar.setState(state);
  }
  listenRing.hidden = state !== "listening";
}

function setUiEnabled(enabled) {
  textInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
  micBtn.disabled = !enabled || speechMode === "none";
  clearBtn.disabled = !enabled;
  uiReady = enabled;
}

function appendMessage(text, role) {
  const el = document.createElement("div");
  el.className = `msg msg--${role}`;
  const p = document.createElement("p");
  p.textContent = text;
  el.appendChild(p);
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
  return el;
}

/** In-chat bot bubble updated as SSE text deltas arrive. */
let streamingBotEl = null;

function updateStreamingBotMessage(text) {
  if (!text) return;
  if (!streamingBotEl) {
    streamingBotEl = appendMessage("", "bot");
    streamingBotEl.classList.add("msg--streaming");
  }
  streamingBotEl.querySelector("p").textContent = text;
  chatLog.scrollTop = chatLog.scrollHeight;
}

function finalizeStreamingBotMessage() {
  streamingBotEl?.classList.remove("msg--streaming");
  streamingBotEl = null;
}

/** Show reply text on the avatar stage while the LLM is still writing. */
function showLiveCaption(text) {
  const t = (text || "").trim();
  if (!t) return;
  clearCaptionTimers();
  aiCaption.hidden = false;
  aiCaptionText.textContent = t;
  requestAnimationFrame(() => aiCaption.classList.add("ai-caption--visible"));
}

async function playReplyAudio(base64, replyText) {
  setStatus("speaking", "Speaking…");
  await unlockAudioFromGesture();
  const { durationMs, done } = await avatar.speakBase64Wav(base64, replyText, "en");
  const captionPromise =
    durationMs > 0 ? streamAiCaption(replyText, durationMs) : hideAiCaption();
  await Promise.all([done, captionPromise]);
  scheduleHideAiCaption();
  setStatus("idle", "Ready");
}

function parseSseBlocks(buffer) {
  const events = [];
  let rest = buffer;
  let idx;
  while ((idx = rest.indexOf("\n\n")) !== -1) {
    const block = rest.slice(0, idx);
    rest = rest.slice(idx + 2);
    for (const line of block.split("\n")) {
      if (!line.startsWith("data:")) continue;
      const raw = line.startsWith("data: ") ? line.slice(6) : line.slice(5).trimStart();
      if (!raw) continue;
      try {
        events.push(JSON.parse(raw));
      } catch (e) {
        console.warn("SSE parse:", e, raw);
      }
    }
  }
  return { events, rest };
}

function handleStreamEvent(ev, state) {
  if (ev.type === "session") {
    sessionId = ev.session_id;
    return;
  }
  if (ev.type === "text_delta") {
    state.fullReply += ev.delta || "";
    updateStreamingBotMessage(state.fullReply);
    showLiveCaption(state.fullReply);
    return;
  }
  if (ev.type === "audio") {
    state.audioChunks.push(ev);
    if (!state.firstAudioScheduled) {
      state.firstAudioScheduled = true;
      avatar.stopThinking();
      setStatus("speaking", "Speaking…");
    }
    state.audioPlayChain = state.audioPlayChain.then(async () => {
      await unlockAudioFromGesture();
      const { done } = await avatar.speakBase64Wav(
        ev.audio_base64,
        ev.text,
        langSelect.value || "en"
      );
      await done;
    });
    return;
  }
  if (ev.type === "done") {
    if (state.doneHandled) return;
    state.doneHandled = true;
    state.fullReply = ev.reply || state.fullReply;
    sessionId = ev.session_id || sessionId;
    updateStreamingBotMessage(state.fullReply);
    showLiveCaption(state.fullReply);
    finalizeStreamingBotMessage();
    return;
  }
  if (ev.type === "error") {
    throw new Error(ev.detail || "Stream error");
  }
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, { ...fetchOpts, ...options });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Not signed in");
  }
  return res;
}

async function ensureSession() {
  if (sessionId) return sessionId;
  const res = await apiFetch("/api/sessions", { method: "POST" });
  if (!res.ok) throw new Error("Could not start chat session");
  const data = await res.json();
  sessionId = data.session_id;
  return sessionId;
}

async function initAuth() {
  try {
    const res = await apiFetch("/auth/me");
    if (!res.ok) return;
    currentUser = await res.json();
    const img = document.getElementById("userAvatar");
    const fallback = document.getElementById("userAvatarFallback");
    if (currentUser.picture && img) {
      img.src = currentUser.picture;
      img.hidden = false;
      if (fallback) fallback.hidden = true;
    }
    await ensureSession();
  } catch {
    /* redirect handled in apiFetch */
  }
}

async function consumeChatStream(message) {
  await ensureSession();
  const res = await apiFetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      voice: voiceSelect.value,
      lang: langSelect.value,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail) || res.statusText
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const state = {
    fullReply: "",
    audioChunks: [],
    audioPlayChain: Promise.resolve(),
    firstAudioScheduled: false,
    doneHandled: false,
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseBlocks(buffer);
    buffer = parsed.rest;
    for (const ev of parsed.events) {
      handleStreamEvent(ev, state);
    }
  }

  // Flush any events still in the buffer when the connection closes.
  if (buffer.trim()) {
    const parsed = parseSseBlocks(`${buffer}\n\n`);
    for (const ev of parsed.events) {
      handleStreamEvent(ev, state);
    }
  }

  return {
    reply: state.fullReply,
    audioChunks: state.audioChunks,
    audioPlayChain: state.audioPlayChain,
  };
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || busy || !uiReady) return;

  void unlockAudioFromGesture();

  busy = true;
  setUiEnabled(false);

  appendMessage(message, "user");
  textInput.value = "";
  setStatus("thinking", "Thinking…");

  streamingBotEl = null;

  try {
    const data = await consumeChatStream(message);
    if (!data.reply?.trim()) {
      appendMessage("(No response)", "bot");
    }
    await data.audioPlayChain;
    scheduleHideAiCaption();
    setStatus("idle", "Ready");
  } catch (e) {
    finalizeStreamingBotMessage();
    avatar?.stopThinking();
    avatar?.stop();
    hideAiCaption();
    const msg = e.message || "Something went wrong.";
    if (/audio|unlock|gesture/i.test(msg)) {
      appendMessage(`${msg} — tap the page once, then try again.`, "error");
    } else {
      appendMessage(msg, "error");
    }
    setStatus("idle", "Error");
    setTimeout(() => setStatus("idle", "Ready"), 2500);
  } finally {
    busy = false;
    setUiEnabled(true);
  }
}

function detectSpeechMode() {
  if (!window.isSecureContext) return "none";
  const hasMedia =
    navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
  const hasBrowserStt = SpeechRecognition && !isIOS;
  if (hasBrowserStt) return "browser";
  if (hasMedia) return "server";
  return "none";
}

function micHelpMessage() {
  if (!window.isSecureContext) {
    return "Microphone needs HTTPS. On your phone use https://YOUR-PC-IP:8765 (run scripts/run_web_https.sh) and accept the certificate warning.";
  }
  if (speechMode === "none") {
    return "Voice input is not supported in this browser. Use the text box.";
  }
  return "";
}

function speechErrorLabel(code) {
  const map = {
    "not-allowed": "Microphone permission denied — allow mic in browser settings.",
    "service-not-allowed": "Voice needs HTTPS or a supported browser (Chrome on Android, Safari on iOS with HTTPS).",
    "network": "Speech recognition needs internet.",
    "no-speech": "No speech heard — try again.",
    "audio-capture": "Could not access the microphone.",
    aborted: "",
  };
  return map[code] || `Mic error: ${code}`;
}

async function ensureMicAccess() {
  if (mediaStream) return true;
  if (!navigator.mediaDevices?.getUserMedia) {
    appendMessage(micHelpMessage() || "Microphone not available.", "error");
    return false;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    return true;
  } catch (e) {
    const name = e?.name || "";
    if (name === "NotAllowedError") {
      appendMessage("Microphone permission denied. Allow mic for this site in settings.", "error");
    } else if (name === "NotFoundError") {
      appendMessage("No microphone found on this device.", "error");
    } else if (!window.isSecureContext) {
      appendMessage(micHelpMessage(), "error");
    } else {
      appendMessage(e.message || "Microphone unavailable.", "error");
    }
    return false;
  }
}

function pickRecorderMime() {
  const types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  for (const t of types) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

async function transcribeBlob(blob, mimeType) {
  const ext = mimeType.includes("mp4")
    ? "m4a"
    : mimeType.includes("ogg")
      ? "ogg"
      : "webm";
  const form = new FormData();
  form.append("audio", blob, `recording.${ext}`);
  form.append("lang", langSelect.value || "en");
  const res = await apiFetch("/api/transcribe", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg || String(d)).join(", ")
      : detail;
    throw new Error(msg || `Transcription failed (${res.status})`);
  }
  const data = await res.json();
  return (data.text || "").trim();
}

function initBrowserSpeech() {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
    setStatus("listening", "Listening…");
    micBtn.classList.add("active");
  };

  recognition.onend = () => {
    micBtn.classList.remove("active");
    if (!busy && !recording) setStatus("idle", "Ready");
  };

  recognition.onerror = (e) => {
    micBtn.classList.remove("active");
    if (e.error !== "aborted") {
      const msg = speechErrorLabel(e.error);
      if (msg) appendMessage(msg, "error");
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        speechMode = "server";
        initSpeech();
        appendMessage("Trying server voice recognition — tap the mic again.", "bot");
      }
    }
    if (!busy) setStatus("idle", "Ready");
  };

  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    if (transcript) sendMessage(transcript);
  };

  updateRecognitionLang();
}

async function startServerRecording() {
  if (recording || busy || !uiReady) return;
  const ok = await ensureMicAccess();
  if (!ok) return;

  recordChunks = [];
  const mime = pickRecorderMime();
  const options = mime ? { mimeType: mime } : undefined;
  try {
    mediaRecorder = new MediaRecorder(mediaStream, options);
  } catch (e) {
    appendMessage(e.message || "Could not start recording.", "error");
    return;
  }

  mediaRecorder.ondataavailable = (ev) => {
    if (ev.data?.size) recordChunks.push(ev.data);
  };

  mediaRecorder.onstop = async () => {
    recording = false;
    micBtn.classList.remove("active");
    const blob = new Blob(recordChunks, {
      type: mediaRecorder.mimeType || mime || "audio/webm",
    });
    recordChunks = [];
    if (!blob.size) {
      if (!busy) setStatus("idle", "Ready");
      return;
    }
    setStatus("thinking", "Transcribing…");
    setUiEnabled(false);
    try {
      const text = await transcribeBlob(blob, blob.type);
      if (text) {
        await sendMessage(text);
      } else {
        appendMessage("No speech detected — try again.", "error");
        setStatus("idle", "Ready");
        setUiEnabled(true);
      }
    } catch (e) {
      appendMessage(e.message || "Transcription failed.", "error");
      setStatus("idle", "Ready");
      setUiEnabled(true);
    }
  };

  mediaRecorder.start();
  recording = true;
  setStatus("listening", "Listening… tap mic to stop");
  micBtn.classList.add("active");
}

function stopServerRecording() {
  if (!mediaRecorder || mediaRecorder.state === "inactive") return;
  try {
    mediaRecorder.stop();
  } catch {
    /* ignore */
  }
}

function initSpeech() {
  speechMode = detectSpeechMode();
  const help = micHelpMessage();

  if (speechMode === "browser") {
    micBtn.title = "Voice input";
    initBrowserSpeech();
    if (uiReady) micBtn.disabled = false;
    return;
  }

  if (speechMode === "server") {
    micBtn.title = "Tap to speak, tap again when done";
    if (uiReady) micBtn.disabled = false;
    return;
  }

  micBtn.title = help || "Voice input unavailable";
  if (help && statusText) {
    setStatus("idle", "Mic needs HTTPS — see chat hint");
    const hint = document.createElement("div");
    hint.className = "msg msg--bot";
    const p = document.createElement("p");
    p.innerHTML =
      "<strong>Voice on phone:</strong> run <code>bash scripts/run_web_https.sh</code> on your PC, open the <code>https://…</code> URL on your phone, accept the certificate warning, then allow the microphone.";
    hint.appendChild(p);
    chatLog?.appendChild(hint);
  }
}

function updateRecognitionLang() {
  if (!recognition) return;
  const map = {
    hi: "hi-IN",
    en: "en-US",
    es: "es-ES",
    fr: "fr-FR",
    de: "de-DE",
    ja: "ja-JP",
    ko: "ko-KR",
  };
  recognition.lang = map[langSelect.value] || "en-US";
}

function startListening() {
  if (busy || !uiReady || speechMode === "none") {
    const help = micHelpMessage();
    if (help) appendMessage(help, "error");
    return;
  }
  if (speechMode === "server") {
    startServerRecording();
    return;
  }
  if (!recognition) return;
  updateRecognitionLang();
  try {
    recognition.start();
  } catch {
    /* already listening */
  }
}

function stopListening() {
  if (speechMode === "server") {
    stopServerRecording();
    return;
  }
  if (recognition) {
    try {
      recognition.stop();
    } catch {
      /* ignore */
    }
  }
}

async function initAvatar() {
  avatarLoaderText.textContent = "Loading 3D engine…";
  setStatus("idle", "Loading 3D…");

  try {
    avatar = new Avatar3D(document.getElementById("avatar3d"));
    avatar.onProgress = (msg) => {
      avatarLoaderText.textContent = msg;
    };
    await avatar.init(avatarModelSelect.value || "brunette", moodSelect.value);
    avatarLoader.classList.add("avatar-loader--hidden");
    setStatus("idle", "Ready");
    setUiEnabled(true);
  } catch (e) {
    console.error("initAvatar:", e);
    avatarLoaderText.textContent = `Failed: ${e.message}`;
    setStatus("idle", "Avatar error");
    appendMessage(
      `Could not load 3D avatar: ${e.message}. Hard-refresh and run ./run_web.sh`,
      "error"
    );
  }
}

composer.addEventListener("submit", (e) => {
  e.preventDefault();
  unlockAudioFromGesture();
  sendMessage(textInput.value);
});

micBtn.addEventListener("click", () => {
  if (busy || !uiReady) return;
  unlockAudioFromGesture();
  if (speechMode === "server" && recording) {
    stopListening();
    return;
  }
  if (micBtn.classList.contains("active")) stopListening();
  else startListening();
});

clearBtn.addEventListener("click", async () => {
  if (sessionId) {
    await apiFetch(`/api/reset?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
    });
  }
  const created = await apiFetch("/api/sessions", { method: "POST" });
  if (created.ok) {
    const data = await created.json();
    sessionId = data.session_id;
  }
  avatar?.stop();
  hideAiCaption();
  chatLog.innerHTML =
    '<div class="msg msg--bot"><p>Chat cleared. Say hello!</p></div>';
  closeSettings();
});

avatarModelSelect.addEventListener("change", async () => {
  if (!avatar) return;
  avatarLoader.classList.remove("avatar-loader--hidden");
  avatarLoaderText.textContent = "Switching avatar…";
  try {
    await avatar.loadAvatar(avatarModelSelect.value || "brunette", moodSelect.value);
  } catch (e) {
    appendMessage(`Avatar switch failed: ${e.message}`, "error");
  }
  avatarLoader.classList.add("avatar-loader--hidden");
});

moodSelect.addEventListener("change", () => {
  avatar?.setMood(moodSelect.value);
});

langSelect.addEventListener("change", updateRecognitionLang);

settingsBtn.addEventListener("click", () => {
  if (settingsOpen) closeSettings();
  else openSettings();
});

settingsBack.addEventListener("click", closeSettings);

sidebarClose.addEventListener("click", () => setSidebarCollapsed(true));
sidebarToggle.addEventListener("click", () => setSidebarCollapsed(false));
mobileChatFab?.addEventListener("click", toggleChatPanel);
sidebarBackdrop?.addEventListener("click", () => setSidebarCollapsed(true));

mobileMq.addEventListener("change", () => {
  if (isMobileLayout()) {
    setSidebarCollapsed(true);
  } else if (sidebarBackdrop) {
    sidebarBackdrop.hidden = true;
  }
  window.dispatchEvent(new Event("resize"));
});

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", () => {
    window.dispatchEvent(new Event("resize"));
  });
}

document.addEventListener(
  "pointerdown",
  () => unlockAudioFromGesture(),
  { once: true, capture: true }
);

document.getElementById("logoutBtn")?.addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST", ...fetchOpts });
  window.location.href = "/login";
});

initAuth().then(() => {
  if (isMobileLayout()) {
    setSidebarCollapsed(true);
  }
  initSpeech();
  initAvatar();
});
