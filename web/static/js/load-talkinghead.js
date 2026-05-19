/**
 * Loads TalkingHead + Three.js (import map in index.html resolves bare "three" imports).
 */
async function loadTalkingHead() {
  try {
    await import("three");
    const module = await import("talkinghead");
    window.TalkingHead = module.TalkingHead;
    window.dispatchEvent(new Event("talkinghead-loaded"));
  } catch (err) {
    console.error("Failed to load TalkingHead:", err);
    window.dispatchEvent(new CustomEvent("talkinghead-error", { detail: err }));
  }
}

loadTalkingHead();
