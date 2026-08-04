/**
 * AI Customer Support SaaS -- embeddable chat widget.
 *
 * Drop-in usage on a tenant's site:
 *   <script
 *     src="https://your-domain.example/widget.js"
 *     data-tenant-slug="acme"
 *     data-api-url="https://api.your-domain.example"
 *     defer
 *   ></script>
 *
 * No dependencies, no build step -- this is meant to be served as-is and
 * embedded directly. Reads its own config off the <script> tag via
 * document.currentScript, which only works during initial synchronous
 * execution, so config is captured at the top before anything async runs.
 */
(function () {
  "use strict";

  var scriptTag = document.currentScript;
  var TENANT_SLUG = scriptTag.getAttribute("data-tenant-slug");
  var API_URL = (scriptTag.getAttribute("data-api-url") || "").replace(/\/$/, "");

  if (!TENANT_SLUG || !API_URL) {
    console.error(
      "[support-widget] Missing required data-tenant-slug or data-api-url attribute on the script tag -- widget will not load."
    );
    return;
  }

  var STORAGE_KEY = "support_saas_widget_conversation_" + TENANT_SLUG;

  // ---- State ----
  var conversationId = null;
  var messages = []; // { role: 'user' | 'assistant', content: string, escalated?: boolean }
  var isOpen = false;
  var isSending = false;

  try {
    var saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) conversationId = JSON.parse(saved).conversationId || null;
  } catch (e) {
    // sessionStorage unavailable (private browsing, etc.) -- fall back to
    // an in-memory-only conversation, which is fine, just doesn't survive reload.
  }

  // ---- Styles (scoped by prefixing every class with sw-) ----
  var style = document.createElement("style");
  style.textContent =
    ".sw-launcher{position:fixed;bottom:20px;right:20px;width:56px;height:56px;border-radius:50%;" +
    "background:#5b8def;color:#fff;border:none;box-shadow:0 4px 14px rgba(0,0,0,.25);cursor:pointer;" +
    "font-size:24px;z-index:999998;display:flex;align-items:center;justify-content:center;}" +
    ".sw-panel{position:fixed;bottom:88px;right:20px;width:340px;max-width:90vw;height:460px;" +
    "max-height:75vh;background:#171a21;border:1px solid #2a2f3a;border-radius:12px;" +
    "box-shadow:0 8px 30px rgba(0,0,0,.35);display:flex;flex-direction:column;overflow:hidden;" +
    "z-index:999999;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#e6e8eb;}" +
    ".sw-header{padding:14px 16px;border-bottom:1px solid #2a2f3a;font-weight:600;display:flex;justify-content:space-between;align-items:center;}" +
    ".sw-close{background:none;border:none;color:#9aa1ac;cursor:pointer;font-size:18px;}" +
    ".sw-messages{flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:10px;}" +
    ".sw-msg{max-width:85%;padding:8px 12px;border-radius:10px;font-size:14px;line-height:1.4;white-space:pre-wrap;}" +
    ".sw-msg-user{align-self:flex-end;background:#5b8def;color:#fff;}" +
    ".sw-msg-assistant{align-self:flex-start;background:#232732;color:#e6e8eb;}" +
    ".sw-msg-escalated{font-size:12px;color:#e0a940;margin-top:4px;}" +
    ".sw-empty{color:#9aa1ac;font-size:13px;text-align:center;margin-top:20px;}" +
    ".sw-inputrow{display:flex;gap:8px;padding:12px;border-top:1px solid #2a2f3a;}" +
    ".sw-input{flex:1;background:#0f1115;border:1px solid #2a2f3a;color:#e6e8eb;border-radius:8px;padding:8px 10px;font-size:14px;resize:none;}" +
    ".sw-send{background:#5b8def;color:#fff;border:none;border-radius:8px;padding:0 14px;font-weight:600;cursor:pointer;}" +
    ".sw-send:disabled{opacity:.5;cursor:not-allowed;}" +
    ".sw-typing{color:#9aa1ac;font-size:13px;padding:0 16px 8px;}";
  document.head.appendChild(style);

  // ---- DOM ----
  var launcher = document.createElement("button");
  launcher.className = "sw-launcher";
  launcher.setAttribute("aria-label", "Open support chat");
  launcher.textContent = "\uD83D\uDCAC"; // speech balloon emoji, avoids needing an icon asset

  var panel = document.createElement("div");
  panel.className = "sw-panel";
  panel.style.display = "none";
  panel.innerHTML =
    '<div class="sw-header"><span>Support</span><button class="sw-close" aria-label="Close chat">\u2715</button></div>' +
    '<div class="sw-messages"></div>' +
    '<div class="sw-typing" style="display:none;">Assistant is typing...</div>' +
    '<div class="sw-inputrow">' +
    '<textarea class="sw-input" rows="1" placeholder="Ask a question..."></textarea>' +
    '<button class="sw-send">Send</button>' +
    "</div>";

  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  var messagesEl = panel.querySelector(".sw-messages");
  var typingEl = panel.querySelector(".sw-typing");
  var inputEl = panel.querySelector(".sw-input");
  var sendBtn = panel.querySelector(".sw-send");
  var closeBtn = panel.querySelector(".sw-close");

  function render() {
    if (messages.length === 0) {
      messagesEl.innerHTML = '<div class="sw-empty">Ask us anything -- we\'re here to help.</div>';
      return;
    }
    messagesEl.innerHTML = "";
    messages.forEach(function (m) {
      var bubble = document.createElement("div");
      bubble.className = "sw-msg sw-msg-" + m.role;
      bubble.textContent = m.content;
      messagesEl.appendChild(bubble);
      if (m.escalated) {
        var note = document.createElement("div");
        note.className = "sw-msg-escalated";
        note.textContent = "A team member will follow up on this shortly.";
        messagesEl.appendChild(note);
      }
    });
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setOpen(open) {
    isOpen = open;
    panel.style.display = open ? "flex" : "none";
    if (open) {
      render();
      inputEl.focus();
    }
  }

  launcher.addEventListener("click", function () {
    setOpen(!isOpen);
  });
  closeBtn.addEventListener("click", function () {
    setOpen(false);
  });

  async function sendMessage() {
    var text = inputEl.value.trim();
    if (!text || isSending) return;

    isSending = true;
    sendBtn.disabled = true;
    inputEl.value = "";
    messages.push({ role: "user", content: text });
    render();
    typingEl.style.display = "block";

    try {
      var response = await fetch(API_URL + "/api/v1/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_slug: TENANT_SLUG,
          message: text,
          conversation_id: conversationId,
        }),
      });

      if (!response.ok) {
        throw new Error("Request failed with status " + response.status);
      }

      var data = await response.json();
      conversationId = data.conversation_id;
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ conversationId: conversationId }));
      } catch (e) {
        // ignore -- storage not available, conversation just won't persist across reloads
      }

      messages.push({
        role: "assistant",
        content: data.answer,
        escalated: !!data.escalated,
      });
    } catch (err) {
      messages.push({
        role: "assistant",
        content:
          "Sorry, something went wrong reaching support. Please try again in a moment.",
      });
    } finally {
      isSending = false;
      sendBtn.disabled = false;
      typingEl.style.display = "none";
      render();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
})();
