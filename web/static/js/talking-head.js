/**
 * 3D avatar controller — TalkMateAI-style UI on top of your custom backend.
 * Uses met4citizen/TalkingHead; audio comes from bizfyvoice via POST /api/chat.
 */
/** Served from web/static/vendor/talkinghead/modules/ (see scripts/vendor_frontend.sh) */
const LIPSYNC_MODULE_BASE = "/static/vendor/talkinghead/modules/";

class Avatar3D {
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

  /** 360° scene backgrounds — Poly Haven CC0 panoramas in /static/backgrounds/ */
  static BACKGROUNDS = {
    default: { label: "Default (gradient)", type: "css" },
    studio: {
      label: "Photo studio",
      type: "panorama",
      url: "/static/backgrounds/studio.jpg",
    },
    office: {
      label: "Office room",
      type: "panorama",
      url: "/static/backgrounds/office.jpg",
    },
    outdoor: {
      label: "Outdoor park",
      type: "panorama",
      url: "/static/backgrounds/outdoor.jpg",
    },
  };

  /** Warm browser cache for panorama JPGs (non-blocking). */
  static preloadBackgrounds() {
    const urls = Object.values(Avatar3D.BACKGROUNDS)
      .filter((b) => b.type === "panorama" && b.url)
      .map((b) => b.url);
    urls.forEach((url) => {
      fetch(url, { cache: "force-cache" }).catch(() => {});
    });
  }

  static STORAGE_KEY_BG = "yukti-background";

  /** Map removed preset ids saved in older localStorage values. */
  static _normalizeBackgroundId(id) {
    const legacy = {
      dawn: "outdoor",
      violet: "office",
      ocean: "outdoor",
      warm: "studio",
    };
    if (legacy[id]) return legacy[id];
    return Avatar3D.BACKGROUNDS[id] ? id : "default";
  }

  /** Fetch all avatar GLBs into the browser cache (non-blocking after default load). */
  static preloadAllAvatars() {
    const urls = [...new Set(Object.values(Avatar3D.AVATARS).map((a) => a.url))];
    return Promise.all(
      urls.map((url) =>
        fetch(url, { cache: "force-cache" }).then((res) => {
          if (!res.ok) throw new Error(`Preload failed ${url}: ${res.status}`);
          return res.arrayBuffer();
        })
      )
    ).catch((e) => console.warn("Avatar preload:", e.message));
  }

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
    this._modelId = "avaturn";
    this._mood = "neutral";
    this._backgroundId = "default";
    this._bgTexture = null;
    this._bgLoadGen = 0;
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

  async init(modelId = "avaturn", mood = "neutral") {
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

    const savedBg = localStorage.getItem(Avatar3D.STORAGE_KEY_BG);
    await this.setBackground(savedBg || "default");
  }

  _stageEl() {
    return this.container?.closest(".avatar-stage");
  }

  _disposeBgTexture() {
    if (this._bgTexture) {
      this._bgTexture.dispose();
      this._bgTexture = null;
    }
  }

  _makeEquirectGradient(THREE, topHex, bottomHex) {
    const w = 1024;
    const h = 512;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    const top = `#${topHex.toString(16).padStart(6, "0")}`;
    const bottom = `#${bottomHex.toString(16).padStart(6, "0")}`;
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, top);
    grad.addColorStop(0.55, top);
    grad.addColorStop(1, bottom);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
    const tex = new THREE.CanvasTexture(canvas);
    tex.mapping = THREE.EquirectangularReflectionMapping;
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  /**
   * Apply a 360° Three.js background (works with avatar zoom) or revert to CSS gradient.
   */
  async setBackground(backgroundId = "default") {
    const id = Avatar3D._normalizeBackgroundId(backgroundId);
    const spec = Avatar3D.BACKGROUNDS[id];
    this._backgroundId = id;
    localStorage.setItem(Avatar3D.STORAGE_KEY_BG, id);
    const loadGen = ++this._bgLoadGen;

    const stage = this._stageEl();
    if (!this._head?.scene) {
      if (spec.type === "css") stage?.classList.remove("avatar-stage--3d-bg");
      else stage?.classList.add("avatar-stage--3d-bg");
      return;
    }

    const THREE = await import("three");
    if (loadGen !== this._bgLoadGen) return;
    this._disposeBgTexture();

    if (spec.type === "css") {
      this._head.scene.background = null;
      this._head.renderer.setClearAlpha(0);
      stage?.classList.remove("avatar-stage--3d-bg");
      return;
    }

    stage?.classList.add("avatar-stage--3d-bg");
    this._head.renderer.setClearAlpha(1);

    if (spec.type === "color") {
      this._head.scene.background = new THREE.Color(spec.color);
      return;
    }

    if (spec.type === "gradient") {
      this._bgTexture = this._makeEquirectGradient(THREE, spec.top, spec.bottom);
      this._head.scene.background = this._bgTexture;
      return;
    }

    if (spec.type === "panorama" && spec.url) {
      this._reportProgress("Loading background…");
      try {
        const loader = new THREE.TextureLoader();
        const tex = await loader.loadAsync(spec.url);
        if (loadGen !== this._bgLoadGen) {
          tex.dispose();
          return;
        }
        tex.mapping = THREE.EquirectangularReflectionMapping;
        tex.colorSpace = THREE.SRGBColorSpace;
        this._bgTexture = tex;
        this._head.scene.background = tex;
      } catch (e) {
        console.warn("Background load failed:", spec.url, e);
        if (loadGen === this._bgLoadGen) {
          this._head.scene.background = new THREE.Color(0x141c2e);
        }
      }
      if (this._avatarReady) this._reportProgress("Avatar ready", 1);
    }
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

  async loadAvatar(modelId = "avaturn", mood = this._mood) {
    if (!this._head) return;
    this._avatarReady = false;
    this._modelId = modelId;
    const spec = Avatar3D.AVATARS[modelId] || Avatar3D.AVATARS.avaturn;

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
   * Play TTS WAV (base64) and lip-sync the 3D avatar.
   * Your backend: POST /api/chat → { audio_base64, reply }
   */
  async speakBase64Wav(base64, replyText = "", lipsyncLang = "en", { interrupt = false } = {}) {
    if (!this._head) throw new Error("Avatar not initialized");
    if (!base64?.length) throw new Error("No audio in response");

    await this._ensureLipsync("en");
    const ctx = await this.unlockAudio();

    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

    const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    let audioBuffer = await ctx.decodeAudioData(ab.slice(0));
    // Piper/bizfyvoice is 16 kHz — skip resample to avoid OfflineAudioContext delay.
    if (audioBuffer.sampleRate !== 16000 && audioBuffer.sampleRate !== 22050) {
      audioBuffer = await this._resampleBuffer(audioBuffer, 22050);
    }
    const durationMs = Math.ceil(audioBuffer.duration * 1000);
    return {
      durationMs,
      done: this.speakAudioBuffer(audioBuffer, replyText, lipsyncLang, { interrupt }),
    };
  }

  speakAudioBuffer(audioBuffer, replyText = "", lipsyncLang = "en", { interrupt = false } = {}) {
    if (!this._head) return Promise.resolve({ durationMs: 0 });

    this._speaking = true;
    this.setState("speaking");

    const durationMs = Math.ceil(audioBuffer.duration * 1000);
    const payload = this._buildSpeakPayload(audioBuffer, replyText, lipsyncLang);

    return new Promise((resolve) => {
      const finish = (ms = durationMs) => {
        this._speaking = false;
        if (!this._head?.isSpeaking && !this._head?.isAudioPlaying) {
          this.setState("idle");
        }
        resolve({ durationMs: ms });
      };

      try {
        // Only clear the queue when starting a new user turn — not between SSE chunks.
        if (interrupt && this._head.stopSpeaking) {
          this._head.stopSpeaking();
        }
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

      // Wait for playback (TalkingHead queues chunks; do not stop mid-stream).
      const waitMs = durationMs + 450;
      setTimeout(() => finish(durationMs), waitMs);
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
