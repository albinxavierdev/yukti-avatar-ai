/**
 * 3D avatar controller — TalkMateAI-style UI on top of your custom backend.
 * Uses met4citizen/TalkingHead; audio comes from Supertonic via POST /api/chat.
 */
const LIPSYNC_MODULE_BASE =
  "https://cdn.jsdelivr.net/gh/met4citizen/TalkingHead@1.4/modules/";

class Avatar3D {
  // Local GLBs (readyplayer.me blocked on this network)
  static AVATARS = {
    brunette: { url: "/static/avatars/brunette.glb", body: "F", label: "Brunette" },
    vroid: { url: "/static/avatars/vroid.glb", body: "F", label: "Vroid" },
    avaturn: { url: "/static/avatars/avaturn.glb", body: "F", label: "Avaturn" },
  };

  static HEAD_CAMERA = {
    cameraView: "head",
    cameraDistance: -0.25,
    cameraY: 0.02,
    cameraRotateEnable: false,
    cameraPanEnable: false,
    cameraZoomEnable: true,
  };

  static waitForLibrary(timeoutMs = 60000) {
    if (window.TalkingHead) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("TalkingHead load timeout")), timeoutMs);
      const onLoad = () => {
        clearTimeout(timer);
        resolve();
      };
      const onErr = (e) => {
        clearTimeout(timer);
        reject(e.detail || new Error("TalkingHead failed to load"));
      };
      window.addEventListener("talkinghead-loaded", onLoad, { once: true });
      window.addEventListener("talkinghead-error", onErr, { once: true });
    });
  }

  constructor(container) {
    this.container = container;
    this._head = null;
    this._audioCtx = null;
    this._audioUnlocked = false;
    this._speaking = false;
    this._modelId = "brunette";
    this._mood = "neutral";
    this._avatarReady = false;
    /** @type {(msg: string, ratio?: number) => void} */
    this.onProgress = null;
  }

  _reportProgress(msg, ratio) {
    if (this.onProgress) this.onProgress(msg, ratio);
  }

  _applyHeadCloseUp() {
    if (!this._head?.setView) return;
    const v = Avatar3D.HEAD_CAMERA;
    this._head.setView("head", {
      cameraDistance: v.cameraDistance,
      cameraY: v.cameraY,
    });
  }

  async init(modelId = "brunette", mood = "neutral") {
    this._reportProgress("Loading 3D engine…");
    await Avatar3D.waitForLibrary();
    const TalkingHead = window.TalkingHead;
    if (!TalkingHead) throw new Error("TalkingHead not available");

    this._modelId = modelId;
    this._mood = mood;
    const cam = Avatar3D.HEAD_CAMERA;

    this._reportProgress("Starting renderer…");
    // Do not pass audioCtx on init — TalkingHead creates one internally; we replace after unlock.
    this._head = new TalkingHead(this.container, {
      ttsEndpoint: "https://texttospeech.googleapis.com/v1/text:synthesize",
      jwtGet: () => Promise.resolve(""),
      lipsyncModules: ["en"],
      lipsyncLang: "en",
      pcmSampleRate: 22050,
      modelFPS: 30,
      cameraView: cam.cameraView,
      cameraDistance: cam.cameraDistance,
      cameraY: cam.cameraY,
      cameraRotateEnable: cam.cameraRotateEnable,
      cameraPanEnable: cam.cameraPanEnable,
      cameraZoomEnable: cam.cameraZoomEnable,
      avatarMute: false,
      avatarMood: mood,
    });

    await this.loadAvatar(modelId, mood);

    // Must run after armature exists — otherwise the scene never animates.
    if (this._head.start) this._head.start();

    // Lip-sync rules load in background; do not block avatar display.
    this._preloadLipsync("en");
  }

  _preloadLipsync(lang = "en") {
    if (!this._head) return;
    this._head.lipsyncGetProcessor(lang, LIPSYNC_MODULE_BASE);
  }

  /** Wait for lipsync-en before speakAudio (not required for GLB display). */
  async _ensureLipsync(lang = "en") {
    if (!this._head) return;
    this._head.lipsyncGetProcessor(lang, LIPSYNC_MODULE_BASE);
    const deadline = Date.now() + 15000;
    while (!this._head.lipsync[lang]) {
      if (Date.now() > deadline) {
        console.warn(`Lipsync "${lang}" not loaded — mouth sync may be limited`);
        return;
      }
      await new Promise((r) => setTimeout(r, 50));
    }
  }

  async _verifyAvatarUrl(url) {
    const res = await fetch(url, { method: "HEAD" });
    if (!res.ok) {
      throw new Error(`Avatar file not found (${res.status}): ${url}`);
    }
  }

  async loadAvatar(modelId = "brunette", mood = this._mood) {
    if (!this._head) return;
    this._avatarReady = false;
    this._modelId = modelId;
    const spec = Avatar3D.AVATARS[modelId] || Avatar3D.AVATARS.brunette;

    this._reportProgress(`Loading ${spec.label}…`, 0);
    await this._verifyAvatarUrl(spec.url);

    try {
      await this._head.showAvatar(
        {
          url: spec.url,
          body: spec.body,
          avatarMood: mood,
          lipsyncLang: "en",
        },
        (ev) => {
          if (ev.lengthComputable && ev.total > 0) {
            const pct = Math.round((ev.loaded / ev.total) * 100);
            this._reportProgress(`Loading ${spec.label}… ${pct}%`, pct / 100);
          }
        }
      );
    } catch (e) {
      throw new Error(`Could not load ${spec.label}: ${e.message || e}`);
    }

    this._applyHeadCloseUp();
    if (this._head.start) this._head.start();
    this._avatarReady = true;
    this._reportProgress("Avatar ready", 1);
  }

  setMood(mood) {
    this._mood = mood;
    if (!this._avatarReady || !this._head?.setMood) return;
    try {
      this._head.setMood(mood);
    } catch (e) {
      console.warn("setMood skipped:", e.message);
    }
  }

  setState(state) {
    this.container.dataset.state = state;
    if (!this._avatarReady) return;
    // Do not call setMood while speaking — it fights viseme blendshapes
    if (state === "speaking") return;
    if (state === "thinking") this.setMood("neutral");
    if (state === "listening") this.setMood("happy");
    if (state === "idle") this.setMood(this._mood);
  }

  /**
   * Resume TalkingHead's built-in AudioContext (do not replace it — nodes are wired to it).
   */
  async unlockAudio() {
    if (!this._head?.audioCtx) {
      throw new Error("Avatar audio not ready");
    }
    const ctx = this._head.audioCtx;
    if (ctx.state === "suspended" || ctx.state === "interrupted") {
      await ctx.resume();
    }
    this._audioCtx = ctx;
    this._audioUnlocked = true;
    if (this._head.armature && this._head.start && !this._head.isRunning) {
      this._head.start();
    }
    return ctx;
  }

  async _getAudioContext() {
    return this.unlockAudio();
  }

  /** Resample to 22050 Hz — TalkingHead pcmSampleRate default. */
  async _resampleBuffer(buffer, targetRate = 22050) {
    if (buffer.sampleRate === targetRate) return buffer;
    const ctx = await this._getAudioContext();
    const offline = new OfflineAudioContext(
      1,
      Math.ceil(buffer.duration * targetRate),
      targetRate
    );
    const src = offline.createBufferSource();
    src.buffer = buffer;
    src.connect(offline.destination);
    src.start(0);
    return offline.startRendering();
  }

  /** Fallback mouth motion when English rules cannot parse text (e.g. Hindi). */
  _fallbackVisemes(durationMs) {
    const visemes = [];
    const vtimes = [];
    const vdurations = [];
    const pattern = ["aa", "E", "O", "PP"];
    const step = 110;
    for (let t = 0, i = 0; t < durationMs; t += step, i++) {
      visemes.push(pattern[i % pattern.length]);
      vtimes.push(t);
      vdurations.push(step * 0.75);
    }
    return { visemes, vtimes, vdurations };
  }

  /**
   * Build speakAudio payload for TalkingHead.
   * REQUIRED: words + wtimes + wdurations — speakAudio() only runs lip-sync inside `if (r.words)`.
   * Audio-only payloads play sound but never move the mouth (root cause of broken lip sync).
   */
  _buildSpeakPayload(audioBuffer, replyText, lipsyncLang = "en") {
    const durationMs = Math.max(audioBuffer.duration * 1000, 200);
    const payload = { audio: audioBuffer };
    const text = (replyText || "").trim();
    if (!text || !this._head) {
      return payload;
    }

    const words = text.split(/\s+/).filter((w) => w.length > 0);
    if (!words.length) {
      return payload;
    }

    const weights = words.map((w) => Math.max(1, [...w].length));
    const totalWeight = weights.reduce((a, b) => a + b, 0) || 1;
    const wtimes = [];
    const wdurations = [];
    let cursor = 0;

    for (let i = 0; i < words.length; i++) {
      const wordMs = (weights[i] / totalWeight) * durationMs;
      wtimes.push(Math.round(cursor));
      wdurations.push(Math.max(40, Math.round(wordMs)));
      cursor += wordMs;
    }

    payload.words = words;
    payload.wtimes = wtimes;
    payload.wdurations = wdurations;

    // Optional pre-baked visemes (still requires words above for speakAudio to read them)
    const lipsyncReady = Boolean(this._head.lipsync?.[lipsyncLang]);
    if (!lipsyncReady || !this._head.lipsyncWordsToVisemes) {
      const fb = this._fallbackVisemes(durationMs);
      payload.visemes = fb.visemes;
      payload.vtimes = fb.vtimes;
      payload.vdurations = fb.vdurations;
      return payload;
    }

    const visemes = [];
    const vtimes = [];
    const vdurations = [];
    cursor = 0;

    for (let i = 0; i < words.length; i++) {
      const wordMs = wdurations[i];
      const wrd = this._head.lipsyncPreProcessText(words[i], lipsyncLang);
      const val = this._head.lipsyncWordsToVisemes(wrd, lipsyncLang);

      if (val?.visemes?.length) {
        const dTotal =
          val.times[val.visemes.length - 1] + val.durations[val.visemes.length - 1];
        for (let j = 0; j < val.visemes.length; j++) {
          vtimes.push(cursor + (val.times[j] / dTotal) * wordMs);
          vdurations.push((val.durations[j] / dTotal) * wordMs);
          visemes.push(val.visemes[j]);
        }
      }
      cursor += wordMs;
    }

    if (visemes.length) {
      payload.visemes = visemes;
      payload.vtimes = vtimes.map((t) => Math.round(t));
      payload.vdurations = vdurations.map((d) => Math.max(30, Math.round(d)));
    } else {
      const fb = this._fallbackVisemes(durationMs);
      payload.visemes = fb.visemes;
      payload.vtimes = fb.vtimes;
      payload.vdurations = fb.vdurations;
    }

    return payload;
  }

  /**
   * Play Supertonic WAV (base64) and lip-sync the 3D avatar.
   * Your backend: POST /api/chat → { audio_base64, reply }
   */
  async speakBase64Wav(base64, replyText = "", lipsyncLang = "en") {
    if (!this._head) throw new Error("Avatar not initialized");
    if (!base64?.length) throw new Error("No audio in response");

    await this._ensureLipsync("en");
    const ctx = await this.unlockAudio();

    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

    const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    let audioBuffer = await ctx.decodeAudioData(ab);
    audioBuffer = await this._resampleBuffer(audioBuffer, 22050);
    const durationMs = Math.ceil(audioBuffer.duration * 1000);
    return {
      durationMs,
      done: this.speakAudioBuffer(audioBuffer, replyText, lipsyncLang),
    };
  }

  speakAudioBuffer(audioBuffer, replyText = "", lipsyncLang = "en") {
    if (!this._head) return Promise.resolve({ durationMs: 0 });

    this._speaking = true;
    this.setState("speaking");

    const durationMs = Math.ceil(audioBuffer.duration * 1000);
    const payload = this._buildSpeakPayload(audioBuffer, replyText, lipsyncLang);

    return new Promise((resolve) => {
      const finish = (ms = durationMs) => {
        this._speaking = false;
        this.setState("idle");
        resolve({ durationMs: ms });
      };

      try {
        if (this._head.stopSpeaking) this._head.stopSpeaking();
        this._head.speakAudio(payload, {
          lipsyncLang: "en",
          isRaw: true,
        });
        if (this._head.audioCtx?.state === "suspended") {
          this._head.audioCtx.resume().catch(() => {});
        }
      } catch (e) {
        console.error("speakAudio error:", e);
        finish(0);
        return;
      }

      setTimeout(() => finish(durationMs), durationMs + 400);
    });
  }

  stop() {
    try {
      if (this._head?.stopSpeaking) this._head.stopSpeaking();
    } catch {
      /* ignore */
    }
    this._speaking = false;
  }

  startThinking() {
    this.setState("thinking");
  }

  stopThinking() {
    if (!this._speaking) this.setState("idle");
  }
}

window.Avatar3D = Avatar3D;
