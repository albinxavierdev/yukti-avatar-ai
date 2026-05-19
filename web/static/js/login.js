(async function initLogin() {
  const hint = document.getElementById("loginHint");
  const googleBtn = document.getElementById("googleBtn");
  const form = document.getElementById("loginForm");

  const params = new URLSearchParams(window.location.search);
  if (params.get("error") === "invalid") {
    const err = document.createElement("p");
    err.className = "login__error";
    err.textContent = "Invalid username or password.";
    form?.parentElement?.insertBefore(err, form);
  }

  try {
    const res = await fetch("/auth/status", { credentials: "include" });
    const data = await res.json();

    if (data.auth_disabled) {
      window.location.href = "/";
      return;
    }

    const me = await fetch("/auth/me", { credentials: "include" });
    if (me.ok) {
      window.location.href = "/";
      return;
    }

    if (!data.google_configured) {
      googleBtn.classList.add("login__google--disabled");
      hint.hidden = false;
      hint.textContent =
        "Google sign-in is not configured yet. Use username/password above.";
    }
  } catch {
    hint.hidden = false;
    hint.textContent = "Could not reach the server. Start with: bash scripts/run_web.sh";
  }
})();
