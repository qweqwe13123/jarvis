(() => {
  const STORE_KEY = "jarvis_workspace_v1";
  const WORKFLOW = [
    "Thinking", "Searching", "Reading Files", "Analyzing Code",
    "Creating Files", "Editing Files", "Finished",
  ];

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => [...document.querySelectorAll(sel)];

  function loadStore() {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY)) || defaultStore();
    } catch {
      return defaultStore();
    }
  }

  function saveStore(data) {
    localStorage.setItem(STORE_KEY, JSON.stringify(data));
  }

  function defaultStore() {
    return {
      activeWorkspace: "default",
      activeChat: null,
      workspaces: {
        default: { id: "default", name: "solver company", chats: [] },
        solver: { id: "solver", name: "solver", chats: [] },
        liquid: { id: "liquid", name: "liquid-dreams-land", chats: [] },
      },
      automations: [
        { id: "a1", name: "Daily standup summary", status: "active" },
        { id: "a2", name: "Deploy check", status: "paused" },
      ],
      settings: {
        prompt: "",
        temperature: 0.7,
        provider: "auto",
      },
      consoleEntries: [],
    };
  }

  function uid() {
    return Math.random().toString(36).slice(2, 10);
  }

  function md(text) {
    if (!text) return "";
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre class="code-block"><span class="lang">${lang || "code"}</span>${code.trim()}</pre>`
    );
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    html = html.replace(/^#{1,3}\s+(.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^[\-\*•]\s+(.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
    html = html.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");
    html = html.split("\n\n").map((p) => {
      if (p.startsWith("<")) return p;
      return `<p>${p.replace(/\n/g, " ")}</p>`;
    }).join("");
    return html;
  }

  function greeting() {
    const h = new Date().getHours();
    const period = h < 12 ? "MORNING" : h < 18 ? "AFTERNOON" : "EVENING";
    $("#greeting-time").textContent = `GOOD ${period},`;
  }

  function renderWorkspaces(store) {
    const list = $("#workspace-list");
    list.innerHTML = "";
    Object.values(store.workspaces).forEach((ws) => {
      const g = document.createElement("div");
      g.className = "workspace-item group-title";
      g.textContent = ws.name;
      g.dataset.ws = ws.id;
      list.appendChild(g);
      ws.chats.forEach((chat) => {
        const c = document.createElement("div");
        c.className = "workspace-item child" + (store.activeChat === chat.id ? " active" : "");
        c.textContent = (chat.pinned ? "📌 " : "") + chat.title;
        c.dataset.chat = chat.id;
        c.dataset.ws = ws.id;
        list.appendChild(c);
      });
    });
  }

  function renderAutomations(store) {
    const list = $("#automation-list");
    if (!list) return;
    list.innerHTML = store.automations.map((a) => `
      <div class="automation-row">
        <span>${a.name}</span>
        <span class="auto-status ${a.status}">${a.status}</span>
        <button class="run-auto" data-id="${a.id}">▸</button>
      </div>
    `).join("");
  }

  function renderChat(store) {
    const stream = $("#chat-stream");
    stream.innerHTML = "";
    const ws = store.workspaces[store.activeWorkspace];
    if (!ws || !store.activeChat) return;
    const chat = ws.chats.find((c) => c.id === store.activeChat);
    if (!chat) return;
    chat.messages.forEach((m) => {
      const card = document.createElement("article");
      card.className = `chat-card ${m.role}`;
      card.innerHTML = `<div class="chat-tag">${m.role === "user" ? "YOU" : "JARVIS"}</div><div class="chat-body">${md(m.content)}</div>`;
      stream.appendChild(card);
    });
    stream.scrollTop = stream.scrollHeight;
  }

  function renderConsole(store) {
    const out = $("#console-output");
    out.innerHTML = store.consoleEntries.map((e) => `
      <article class="console-card">
        <div class="console-card-title">${e.title}</div>
        <div class="console-card-body">${md(e.content)}</div>
      </article>
    `).join("");
    out.scrollTop = 0;
  }

  function setWorkflowStep(step) {
    const idx = WORKFLOW.indexOf(step);
    if (idx < 0) return;
    $$("#workflow-steps li").forEach((li, i) => {
      const name = WORKFLOW[i];
      if (i < idx) {
        li.className = "done";
        li.textContent = `✓ ${name}`;
      } else if (i === idx) {
        li.className = "active";
        li.textContent = `● ${name}`;
      } else {
        li.className = "";
        li.textContent = `○ ${name}`;
      }
    });
  }

  function resetWorkflow() {
    $$("#workflow-steps li").forEach((li, i) => {
      li.className = "";
      li.textContent = `○ ${WORKFLOW[i]}`;
    });
  }

  function getActiveChat(store) {
    const ws = store.workspaces[store.activeWorkspace];
    if (!ws) return null;
    return ws.chats.find((c) => c.id === store.activeChat) || null;
  }

  function createChat(store, title) {
    const ws = store.workspaces[store.activeWorkspace];
    const chat = {
      id: uid(),
      title: title || "New Chat",
      pinned: false,
      messages: [],
      updated: Date.now(),
    };
    ws.chats.unshift(chat);
    store.activeChat = chat.id;
    saveStore(store);
    return chat;
  }

  async function simulateAI(store, userText) {
    const steps = userText.match(/code|fix|bug|analyze|search|file/i)
      ? ["Thinking", "Reading Files", "Analyzing Code", "Finished"]
      : ["Thinking", "Searching", "Finished"];
    for (const step of steps.slice(0, -1)) {
      setWorkflowStep(step);
      setStatus(step.toUpperCase());
      await sleep(500 + Math.random() * 400);
    }
    setWorkflowStep("Finished");
    setStatus("LISTENING");

    const response = buildDemoResponse(userText);
    const chat = getActiveChat(store);
    if (chat) {
      chat.messages.push({ role: "assistant", content: response, ts: Date.now() });
      if (chat.title === "New Chat") {
        chat.title = userText.slice(0, 36) + (userText.length > 36 ? "…" : "");
      }
    }
    store.consoleEntries.unshift({
      id: uid(),
      title: "JARVIS Response",
      content: response,
      ts: Date.now(),
    });
    store.consoleEntries = store.consoleEntries.slice(0, 50);
    saveStore(store);
    renderChat(store);
    renderConsole(store);
    renderWorkspaces(store);
    $("#ai-model").textContent = $("#model-select").selectedOptions[0].textContent;
  }

  function buildDemoResponse(text) {
    return `Готово. Я проанализировал запрос.

**Что найдено:**

• проблема №1 — контекст: \`${text.slice(0, 40)}\`
• проблема №2 — требуется уточнение scope

**Что исправлено:**

• изменение №1 — обновлён workspace UI
• изменение №2 — подключена JARVIS CONSOLE

**Следующие шаги:**

• шаг №1 — запустить \`python main.py\`
• шаг №2 — проверить провайдер модели в Customize`;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function setStatus(s) {
    $("#top-status").textContent = `STATUS ${s}`;
    $("#hud-status").textContent = `● ${s}`;
    $("#ai-status").textContent = s.charAt(0) + s.slice(1).toLowerCase();
  }

  function tickUptime() {
    const start = window._jarvisStart || (window._jarvisStart = Date.now());
    const sec = Math.floor((Date.now() - start) / 1000);
    const m = String(Math.floor(sec / 60)).padStart(2, "0");
    const s = String(sec % 60).padStart(2, "0");
    $("#uptime").textContent = `${m}:${s}`;
  }

  function tickMetrics() {
    const cpu = 8 + Math.floor(Math.random() * 20);
    const mem = 60 + Math.floor(Math.random() * 25);
    const gpu = 5 + Math.floor(Math.random() * 20);
    const tmp = 30 + Math.floor(Math.random() * 8);
    $("#m-cpu").textContent = `${cpu}%`;
    $("#m-mem").textContent = `${mem}%`;
    $("#m-gpu").textContent = `${gpu}%`;
    $("#m-tmp").textContent = `${tmp}°C`;
    $("#m-cpu-bar").style.width = `${cpu}%`;
    $("#m-mem-bar").style.width = `${mem}%`;
    $("#m-gpu-bar").style.width = `${gpu}%`;
    $("#m-tmp-bar").style.width = `${tmp}%`;
    $("#m-net").textContent = `${Math.floor(Math.random() * 120)}KB/s`;
    $("#m-net-bar").style.width = `${Math.min(100, Math.random() * 30)}%`;
  }

  function init() {
    const store = loadStore();
    if (!store.activeChat) {
      const chat = createChat(store, "Placeholder conversation");
      store.workspaces.solver = store.workspaces.solver || { id: "solver", name: "solver", chats: [] };
      store.workspaces.solver.chats.push(chat);
    }
    greeting();
    renderWorkspaces(store);
    renderAutomations(store);
    renderChat(store);
    renderConsole(store);
    tickUptime();
    tickMetrics();
    setInterval(tickUptime, 1000);
    setInterval(tickMetrics, 2500);

    $("#btn-new-chat").addEventListener("click", () => {
      const s = loadStore();
      resetWorkflow();
      createChat(s, "New Chat");
      saveStore(s);
      renderWorkspaces(s);
      renderChat(s);
      $("#chat-stream").innerHTML = "";
    });

    $("#workspace-list").addEventListener("click", (e) => {
      const el = e.target.closest("[data-chat]");
      if (!el) return;
      const s = loadStore();
      s.activeWorkspace = el.dataset.ws;
      s.activeChat = el.dataset.chat;
      saveStore(s);
      renderWorkspaces(s);
      renderChat(s);
    });

    $$(".sidebar-action[data-section]").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".sidebar-action[data-section]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const sec = btn.dataset.section;
        $("#sidebar-section").classList.toggle("hidden", sec !== "workspaces");
        $("#panel-customize").classList.toggle("hidden", sec !== "customize");
        $("#panel-automations").classList.toggle("hidden", sec !== "automations");
      });
    });

    $("#btn-save-settings").addEventListener("click", () => {
      const s = loadStore();
      s.settings.prompt = $("#cfg-prompt").value;
      s.settings.temperature = Number($("#cfg-temp").value) / 100;
      s.settings.provider = $("#cfg-provider").value;
      saveStore(s);
    });

    $("#cfg-temp").addEventListener("input", (e) => {
      $("#cfg-temp-val").textContent = (e.target.value / 100).toFixed(1);
    });

    $("#btn-new-automation").addEventListener("click", () => {
      const s = loadStore();
      s.automations.unshift({ id: uid(), name: "New Automation", status: "draft" });
      saveStore(s);
      renderAutomations(s);
    });

    async function submit() {
      const text = $("#composer-input").value.trim();
      if (!text) return;
      $("#composer-input").value = "";
      const s = loadStore();
      if (!getActiveChat(s)) createChat(s, text.slice(0, 40));
      const chat = getActiveChat(s);
      chat.messages.push({ role: "user", content: text, ts: Date.now() });
      saveStore(s);
      renderChat(s);
      resetWorkflow();
      setWorkflowStep("Thinking");
      setStatus("THINKING");
      await simulateAI(s, text);
    }

    $("#btn-send").addEventListener("click", submit);
    $("#composer-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    });
    $("#btn-plan").addEventListener("click", () => {
      $("#composer-input").value = "Help me plan a new idea step by step.";
      submit();
    });

    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") {
        e.preventDefault();
        $("#btn-new-chat").click();
      }
    });

    const current = location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".nav a[data-page]").forEach((a) => {
      if (a.getAttribute("data-page") === current) a.classList.add("active");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
