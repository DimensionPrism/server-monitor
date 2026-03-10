const state = {
  updates: new Map(),
  settings: null,
};

function byId(id) {
  return document.getElementById(id);
}

function toLines(raw) {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function setTabs() {
  const monitorBtn = byId("tab-monitor");
  const settingsBtn = byId("tab-settings");
  const monitorView = byId("view-monitor");
  const settingsView = byId("view-settings");

  function activate(view) {
    const isMonitor = view === "monitor";
    monitorBtn.classList.toggle("active", isMonitor);
    settingsBtn.classList.toggle("active", !isMonitor);
    monitorView.classList.toggle("active", isMonitor);
    settingsView.classList.toggle("active", !isMonitor);
  }

  monitorBtn.addEventListener("click", () => activate("monitor"));
  settingsBtn.addEventListener("click", () => activate("settings"));
}

function renderMonitor() {
  const grid = byId("monitor-grid");
  const cards = [];

  if (state.updates.size === 0) {
    grid.innerHTML = '<p class="muted">Waiting for server updates...</p>';
    return;
  }

  for (const update of state.updates.values()) {
    const panels = new Set(update.enabled_panels || ["system", "gpu", "git", "clash"]);
    const snapshot = update.snapshot || {};
    const repoText = JSON.stringify(update.repos || [], null, 2);
    const clashText = JSON.stringify(update.clash || {}, null, 2);
    const gpuText = JSON.stringify(snapshot.gpus || [], null, 2);
    const stale = update.stale ? "yes" : "no";

    let html = `
      <article class="card">
        <h3>${update.server_id}</h3>
        <div class="muted">stale: ${stale}</div>
    `;

    if (panels.has("system")) {
      html += `
        <section class="panel">
          <h4>System</h4>
          <pre>CPU: ${snapshot.cpu_percent ?? "--"}%\nMEM: ${snapshot.memory_percent ?? "--"}%\nDISK: ${snapshot.disk_percent ?? "--"}%\nNET RX/TX: ${snapshot.network_rx_kbps ?? "--"} / ${snapshot.network_tx_kbps ?? "--"}</pre>
        </section>
      `;
    }

    if (panels.has("gpu")) {
      html += `
        <section class="panel">
          <h4>GPU</h4>
          <pre>${gpuText}</pre>
        </section>
      `;
    }

    if (panels.has("git")) {
      html += `
        <section class="panel">
          <h4>Git</h4>
          <pre>${repoText}</pre>
        </section>
      `;
    }

    if (panels.has("clash")) {
      html += `
        <section class="panel">
          <h4>Clash</h4>
          <pre>${clashText}</pre>
        </section>
      `;
    }

    html += "</article>";
    cards.push(html);
  }

  grid.innerHTML = cards.join("\n");
}

async function api(method, url, body) {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (response.status === 204) {
    return null;
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status}`);
  }

  return response.json();
}

function serverEditorTemplate(server) {
  const panelSet = new Set(server.enabled_panels || []);
  const dirs = (server.working_dirs || []).join("\n");
  return `
    <div class="server-editor" data-server-id="${server.server_id}">
      <h3>${server.server_id}</h3>
      <label>
        SSH Alias
        <input data-field="ssh_alias" type="text" value="${server.ssh_alias}" />
      </label>
      <label>
        Working Directories (one per line)
        <textarea data-field="working_dirs" rows="4">${dirs}</textarea>
      </label>
      <fieldset>
        <legend>Enabled Panels</legend>
        <label><input data-panel="system" type="checkbox" ${panelSet.has("system") ? "checked" : ""} /> System</label>
        <label><input data-panel="gpu" type="checkbox" ${panelSet.has("gpu") ? "checked" : ""} /> GPU</label>
        <label><input data-panel="git" type="checkbox" ${panelSet.has("git") ? "checked" : ""} /> Git</label>
        <label><input data-panel="clash" type="checkbox" ${panelSet.has("clash") ? "checked" : ""} /> Clash</label>
      </fieldset>
      <button class="btn-primary" data-action="save" type="button">Save</button>
      <button class="btn-danger" data-action="delete" type="button">Delete</button>
      <div class="status" data-role="status"></div>
    </div>
  `;
}

function bindServerEditorEvents() {
  const editors = document.querySelectorAll(".server-editor");
  editors.forEach((editor) => {
    const serverId = editor.getAttribute("data-server-id");
    const statusEl = editor.querySelector('[data-role="status"]');

    editor.querySelector('[data-action="save"]').addEventListener("click", async () => {
      const alias = editor.querySelector('[data-field="ssh_alias"]').value.trim();
      const dirsRaw = editor.querySelector('[data-field="working_dirs"]').value;
      const enabledPanels = Array.from(editor.querySelectorAll("input[data-panel]:checked")).map((el) => el.getAttribute("data-panel"));
      const workingDirs = toLines(dirsRaw);
      try {
        await api("PUT", `/api/servers/${serverId}`, {
          server_id: serverId,
          ssh_alias: alias,
          working_dirs: workingDirs,
          enabled_panels: enabledPanels,
        });
        statusEl.textContent = "Saved";
        await loadSettings();
      } catch (err) {
        statusEl.textContent = `Save failed: ${err.message}`;
      }
    });

    editor.querySelector('[data-action="delete"]').addEventListener("click", async () => {
      try {
        await api("DELETE", `/api/servers/${serverId}`);
        await loadSettings();
      } catch (err) {
        statusEl.textContent = `Delete failed: ${err.message}`;
      }
    });
  });
}

function renderSettings() {
  const list = byId("settings-list");
  const servers = (state.settings && state.settings.servers) || [];

  if (servers.length === 0) {
    list.innerHTML = '<p class="muted">No servers configured yet.</p>';
    return;
  }

  list.innerHTML = servers.map(serverEditorTemplate).join("\n");
  bindServerEditorEvents();
}

async function loadSettings() {
  const settings = await api("GET", "/api/settings");
  state.settings = settings;
  renderSettings();
}

function bindAddServerForm() {
  const form = byId("add-server-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const serverId = byId("new-server-id").value.trim();
    const alias = byId("new-server-alias").value.trim();
    const dirs = toLines(byId("new-server-dirs").value);
    const panels = Array.from(document.querySelectorAll('input[name="new-panel"]:checked')).map((el) => el.value);

    await api("POST", "/api/servers", {
      server_id: serverId,
      ssh_alias: alias,
      working_dirs: dirs,
      enabled_panels: panels,
    });

    form.reset();
    document.querySelectorAll('input[name="new-panel"]').forEach((el) => {
      el.checked = true;
    });
    await loadSettings();
  });
}

function connectWs() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      state.updates.set(payload.server_id, payload);
      renderMonitor();
    } catch (_) {
      // Ignore malformed events.
    }
  };

  ws.onclose = () => {
    setTimeout(connectWs, 1000);
  };
}

async function init() {
  setTabs();
  bindAddServerForm();
  await loadSettings();
  renderMonitor();
  connectWs();
}

init();
