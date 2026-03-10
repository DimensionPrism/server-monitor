const state = {
  updates: new Map(),
  settings: null,
  gitOps: new Map(),
  panelOpenState: new Map(),
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatLastUpdate(timestampText) {
  if (!timestampText) {
    return "--";
  }
  const parsed = new Date(timestampText);
  if (Number.isNaN(parsed.getTime())) {
    return "--";
  }
  const ageSeconds = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000));
  let ageLabel = `${ageSeconds}s ago`;
  if (ageSeconds >= 3600) {
    ageLabel = `${Math.floor(ageSeconds / 3600)}h ago`;
  } else if (ageSeconds >= 60) {
    ageLabel = `${Math.floor(ageSeconds / 60)}m ago`;
  }
  return `${parsed.toLocaleTimeString()} (${ageLabel})`;
}

function renderLastUpdateLine(timestampText) {
  return `<div class="muted panel-updated">Last update: ${escapeHtml(formatLastUpdate(timestampText))}</div>`;
}

function clampPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return 0;
  }
  return Math.max(0, Math.min(100, number));
}

function repoKey(serverId, repoPath) {
  return `${serverId}::${repoPath}`;
}

function readGitOpState(serverId, repoPath) {
  return state.gitOps.get(repoKey(serverId, repoPath));
}

function writeGitOpState(serverId, repoPath, phase, message) {
  state.gitOps.set(repoKey(serverId, repoPath), { phase, message });
}

function panelStateKey(serverId, groupClass) {
  return `${serverId}::${groupClass}`;
}

function readPanelOpenState(serverId, groupClass, defaultOpen) {
  const key = panelStateKey(serverId, groupClass);
  if (!state.panelOpenState.has(key)) {
    return defaultOpen;
  }
  return state.panelOpenState.get(key) === true;
}

function writePanelOpenState(serverId, groupClass, isOpen) {
  state.panelOpenState.set(panelStateKey(serverId, groupClass), isOpen);
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

function metricBar(label, value) {
  const percent = clampPercent(value);
  const valueText = Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}%` : "--";
  return `
    <div class="meter-row">
      <div class="meter-label">${escapeHtml(label)}</div>
      <div class="meter-track"><div class="meter-fill" style="width:${percent}%"></div></div>
      <div class="meter-value">${valueText}</div>
    </div>
  `;
}

function renderPanelGroup(title, contentHtml, options = {}) {
  const groupClass = options.groupClass ? `panel-group panel-group-${options.groupClass}` : "panel-group";
  const serverId = String(options.serverId || "");
  const groupName = String(options.groupClass || "unknown");
  const shouldOpen = readPanelOpenState(serverId, groupName, options.open === true);
  const openAttr = shouldOpen ? " open" : "";
  return `
    <details class="${groupClass}" data-panel-server-id="${escapeHtml(serverId)}" data-panel-group="${escapeHtml(groupName)}"${openAttr}>
      <summary>${escapeHtml(title)}</summary>
      <div class="panel-group-body">${contentHtml}</div>
    </details>
  `;
}

function renderSystemPanel(snapshot) {
  const systemLastUpdated = snapshot && snapshot.metadata ? snapshot.metadata.system_last_updated_at : null;
  return `
    ${metricBar("CPU", snapshot.cpu_percent)}
    ${metricBar("Memory", snapshot.memory_percent)}
    ${metricBar("Disk", snapshot.disk_percent)}
    <div class="muted">Net RX/TX: ${snapshot.network_rx_kbps ?? "--"} / ${snapshot.network_tx_kbps ?? "--"} KB/s</div>
    ${renderLastUpdateLine(systemLastUpdated)}
  `;
}

function renderGpuPanel(snapshot) {
  const gpus = Array.isArray(snapshot.gpus) ? snapshot.gpus : [];
  const gpuLastUpdated = snapshot && snapshot.metadata ? snapshot.metadata.gpu_last_updated_at : null;
  if (gpus.length === 0) {
    return `<div class="muted">No GPU metrics.</div>${renderLastUpdateLine(gpuLastUpdated)}`;
  }

  const rows = gpus
    .map((gpu) => {
      const utilization = gpu.utilization_gpu_percent ?? gpu.utilization_gpu;
      const memoryUsed = gpu.memory_used_mib ?? gpu.memory_used_mb;
      const memoryTotal = gpu.memory_total_mib ?? gpu.memory_total_mb;
      const memoryUtil =
        gpu.memory_utilization_percent ??
        (Number.isFinite(Number(memoryUsed)) && Number.isFinite(Number(memoryTotal)) && Number(memoryTotal) > 0
          ? (Number(memoryUsed) / Number(memoryTotal)) * 100
          : 0);
      const temperature = gpu.temperature_celsius ?? gpu.temperature_c;

      return `
      <div class="gpu-card">
        <div class="gpu-head">GPU ${gpu.index}: ${escapeHtml(gpu.name || "unknown")}</div>
        ${metricBar("Util", utilization)}
        ${metricBar("Mem", memoryUtil)}
        <div class="muted">Temp: ${temperature ?? "--"} C, VRAM: ${memoryUsed ?? "--"}/${memoryTotal ?? "--"} MiB</div>
      </div>
    `;
    })
    .join("\n");

  return `<div class="gpu-grid">${rows}</div>${renderLastUpdateLine(gpuLastUpdated)}`;
}

function renderClashPanel(clash) {
  const running = clash && clash.running ? "running" : "stopped";
  const message = clash && clash.message ? clash.message : "--";
  return `
    <div class="kv"><span>Status</span><strong>${escapeHtml(running)}</strong></div>
    <div class="kv"><span>API</span><strong>${clash && clash.api_reachable ? "reachable" : "unreachable"}</strong></div>
    <div class="kv"><span>UI</span><strong>${clash && clash.ui_reachable ? "reachable" : "unreachable"}</strong></div>
    <div class="kv"><span>Message</span><strong>${escapeHtml(message)}</strong></div>
    ${renderLastUpdateLine(clash && clash.last_updated_at)}
  `;
}

function repoSummary(repo) {
  const dirtyClass = repo.dirty ? "warn" : "ok";
  const dirtyLabel = repo.dirty ? "dirty" : "clean";
  return `
    <div class="repo-summary">
      <span class="badge">${escapeHtml(repo.branch || "unknown")}</span>
      <span class="badge ${dirtyClass}">${dirtyLabel}</span>
      <span class="badge">ahead ${repo.ahead ?? 0}</span>
      <span class="badge">behind ${repo.behind ?? 0}</span>
      <span class="badge">staged ${repo.staged ?? 0}</span>
      <span class="badge">unstaged ${repo.unstaged ?? 0}</span>
      <span class="badge">untracked ${repo.untracked ?? 0}</span>
    </div>
  `;
}

function renderGitPanel(update) {
  const repos = Array.isArray(update.repos) ? update.repos : [];
  if (repos.length === 0) {
    return '<div class="muted">No configured repositories.</div>';
  }

  const rows = repos
    .map((repo) => {
      const opState = readGitOpState(update.server_id, repo.path);
      const statusClass = opState ? `git-op-status ${opState.phase}` : "git-op-status";
      const statusText = opState ? escapeHtml(opState.message) : "idle";
      const safePath = escapeHtml(repo.path);
      return `
        <div class="git-repo" data-server-id="${escapeHtml(update.server_id)}" data-repo-path="${safePath}">
          <div class="git-repo-path">${safePath}</div>
          ${repoSummary(repo)}
          ${renderLastUpdateLine(repo.last_updated_at)}
          <div class="git-actions">
            <button class="btn-pill" type="button" data-git-op="refresh">Refresh</button>
            <button class="btn-pill" type="button" data-git-op="fetch">Fetch</button>
            <button class="btn-pill" type="button" data-git-op="pull">Pull</button>
            <input class="branch-input" data-role="branch" type="text" placeholder="branch/name" />
            <button class="btn-pill" type="button" data-git-op="checkout">Checkout</button>
          </div>
          <div class="${statusClass}">${statusText}</div>
        </div>
      `;
    })
    .join("\n");

  return `<div class="git-repo-list">${rows}</div>`;
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
    const stale = update.stale ? "yes" : "no";

    let html = `
      <article class="card server-card">
        <header class="server-card-head">
          <h3>${escapeHtml(update.server_id)}</h3>
          <div class="muted">stale: ${stale}</div>
        </header>
    `;

    if (panels.has("system")) {
      html += renderPanelGroup("System", renderSystemPanel(snapshot), { groupClass: "system", open: true, serverId: update.server_id });
    }

    if (panels.has("gpu")) {
      html += renderPanelGroup("GPU", renderGpuPanel(snapshot), { groupClass: "gpu", open: true, serverId: update.server_id });
    }

    if (panels.has("git")) {
      html += renderPanelGroup("Git", renderGitPanel(update), { groupClass: "git", open: false, serverId: update.server_id });
    }

    if (panels.has("clash")) {
      html += renderPanelGroup("Clash", renderClashPanel(update.clash || {}), { groupClass: "clash", open: false, serverId: update.server_id });
    }

    html += "</article>";
    cards.push(html);
  }

  grid.innerHTML = `<div class="server-board">${cards.join("\n")}</div>`;
  bindPanelGroupEvents();
  bindGitControlEvents();
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

function updateRepoInState(serverId, repo) {
  const current = state.updates.get(serverId);
  if (!current) {
    return;
  }

  const repos = Array.isArray(current.repos) ? current.repos.slice() : [];
  const index = repos.findIndex((item) => item.path === repo.path);
  if (index >= 0) {
    repos[index] = repo;
  } else {
    repos.push(repo);
  }
  current.repos = repos;
  state.updates.set(serverId, current);
}

async function runGitOperation(serverId, repoPath, operation, branch) {
  writeGitOpState(serverId, repoPath, "running", `${operation} running...`);
  renderMonitor();

  const payload = { repo_path: repoPath, operation };
  if (operation === "checkout") {
    payload.branch = (branch || "").trim();
    if (!payload.branch) {
      writeGitOpState(serverId, repoPath, "fail", "checkout requires branch name");
      renderMonitor();
      return;
    }
  }

  try {
    const response = await api("POST", `/api/servers/${encodeURIComponent(serverId)}/git/ops`, payload);
    if (response && response.repo) {
      updateRepoInState(serverId, response.repo);
    }
    const stderr = response && typeof response.stderr === "string" ? response.stderr.trim() : "";
    const errorHint = stderr ? `: ${stderr.split("\n")[0]}` : "";
    const message = response && response.ok ? `${operation} ok` : `${operation} failed${errorHint}`;
    writeGitOpState(serverId, repoPath, response && response.ok ? "ok" : "fail", message);
  } catch (err) {
    writeGitOpState(serverId, repoPath, "fail", `${operation} failed: ${err.message}`);
  }

  renderMonitor();
}

function bindGitControlEvents() {
  const buttons = document.querySelectorAll("button[data-git-op]");
  buttons.forEach((button) => {
    if (button.dataset.bound === "1") {
      return;
    }
    button.dataset.bound = "1";
    button.addEventListener("click", async () => {
      const repoNode = button.closest(".git-repo");
      if (!repoNode) {
        return;
      }
      const serverId = repoNode.getAttribute("data-server-id");
      const repoPath = repoNode.getAttribute("data-repo-path");
      const operation = button.getAttribute("data-git-op");
      const branchInput = repoNode.querySelector('input[data-role="branch"]');
      const branch = branchInput ? branchInput.value : "";
      if (!serverId || !repoPath || !operation) {
        return;
      }
      await runGitOperation(serverId, repoPath, operation, branch);
    });
  });
}

function bindPanelGroupEvents() {
  const groups = document.querySelectorAll("details[data-panel-server-id][data-panel-group]");
  groups.forEach((group) => {
    if (group.dataset.bound === "1") {
      return;
    }
    group.dataset.bound = "1";
    group.addEventListener("toggle", () => {
      const serverId = group.getAttribute("data-panel-server-id");
      const panelGroup = group.getAttribute("data-panel-group");
      if (!serverId || !panelGroup) {
        return;
      }
      writePanelOpenState(serverId, panelGroup, group.open);
    });
  });
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
