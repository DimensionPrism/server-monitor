import json
import subprocess
import textwrap
from pathlib import Path


APP_JS_PATH = Path(__file__).resolve().parents[2] / "src" / "server_monitor" / "dashboard" / "static" / "app.js"


def _run_app_js_test(js_test: str) -> None:
    runner = textwrap.dedent(
        f"""
        const fs = require("fs");
        const vm = require("vm");

        let source = fs.readFileSync({json.dumps(str(APP_JS_PATH))}, "utf8");
        source = source.replace(/\\r?\\ninit\\(\\);\\s*$/, "\\n");

        function makeElement(id = "") {{
          const listeners = {{}};
          return {{
            id,
            innerHTML: "",
            dataset: {{}},
            value: "",
            checked: false,
            disabled: false,
            open: false,
            textContent: "",
            style: {{}},
            classList: {{
              toggle() {{}},
              add() {{}},
              remove() {{}},
            }},
            __listeners: listeners,
            addEventListener(type, handler) {{
              listeners[type] = handler;
            }},
            querySelector() {{ return null; }},
            querySelectorAll() {{ return []; }},
            closest() {{ return null; }},
            appendChild() {{}},
            removeChild() {{}},
            setAttribute() {{}},
            select() {{}},
          }};
        }}

        const elements = new Map();
        const document = {{
          body: {{
            appendChild() {{}},
            removeChild() {{}},
          }},
          execCommand() {{
            return true;
          }},
          getElementById(id) {{
            if (!elements.has(id)) {{
              elements.set(id, makeElement(id));
            }}
            return elements.get(id);
          }},
          querySelector(selector) {{
            return globalThis.__querySelector ? globalThis.__querySelector(selector) : null;
          }},
          querySelectorAll(selector) {{
            return globalThis.__querySelectorAll ? globalThis.__querySelectorAll(selector) : [];
          }},
          createElement(tag) {{
            return makeElement(tag);
          }},
        }};

        const window = {{
          location: {{ protocol: "http:", host: "example.test" }},
          open() {{}},
          isSecureContext: false,
        }};

        const navigator = {{
          clipboard: {{
            async writeText() {{}},
          }},
        }};

        function WebSocket() {{
          this.close = () => {{}};
        }}

        const sandbox = {{
          console,
          document,
          window,
          navigator,
          WebSocket,
          setTimeout() {{}},
          clearTimeout() {{}},
          fetch: async (...args) => {{
            if (globalThis.__fetch) {{
              return globalThis.__fetch(...args);
            }}
            return {{
              status: 204,
              ok: true,
              json: async () => ({{ servers: [] }}),
              text: async () => "",
            }};
          }},
          Map,
          Set,
          Date,
          Math,
          Number,
          String,
          Boolean,
          Array,
          Object,
          Promise,
          JSON,
        }};
        Object.defineProperty(sandbox, "Notification", {{
          get() {{
            return globalThis.Notification;
          }},
          set(value) {{
            globalThis.Notification = value;
          }},
        }});

        vm.createContext(sandbox);
        vm.runInContext(
          source + `
          globalThis.__testExports = {{
            state,
            renderMonitor,
            renderSettings,
            renderSettingsEditorPanel,
              renderSettingsOverview,
              renderServerSummary: typeof renderServerSummary !== "undefined" ? renderServerSummary : undefined,
              selectSettingsServer: typeof selectSettingsServer !== "undefined" ? selectSettingsServer : undefined,
              captureCurrentServerEditorDraft: typeof captureCurrentServerEditorDraft !== "undefined" ? captureCurrentServerEditorDraft : undefined,
              extractServerEditorDraft: typeof extractServerEditorDraft !== "undefined" ? extractServerEditorDraft : undefined,
              bindAddServerForm: typeof bindAddServerForm !== "undefined" ? bindAddServerForm : undefined,
              resetAddServerForm: typeof resetAddServerForm !== "undefined" ? resetAddServerForm : undefined,
              setSettingsAddExpanded: typeof setSettingsAddExpanded !== "undefined" ? setSettingsAddExpanded : undefined,
              renderSettingsAddCard: typeof renderSettingsAddCard !== "undefined" ? renderSettingsAddCard : undefined,
              exportDiagnostics: typeof exportDiagnostics !== "undefined" ? exportDiagnostics : undefined,
              saveNotificationSettings: typeof saveNotificationSettings !== "undefined" ? saveNotificationSettings : undefined,
              processNotificationTransitions: typeof processNotificationTransitions !== "undefined" ? processNotificationTransitions : undefined,
            }};
            `,
          sandbox,
        );
        const __testExports = sandbox.__testExports;

        (async () => {{
        {js_test}
        }})().catch((error) => {{
          console.error(error && error.stack ? error.stack : error);
          process.exit(1);
        }});
        """
    )
    proc = subprocess.run(
        ["node", "-e", runner],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_render_monitor_summary_respects_enabled_panels():
    _run_app_js_test(
        """
        const grid = document.getElementById("monitor-grid");
        globalThis.__querySelectorAll = () => [];

        __testExports.state.updates = new Map([
          [
            "server-a",
            {
              server_id: "server-a",
              enabled_panels: ["git"],
              freshness: {
                system: { state: "cached", reason: "stale" },
                git: { state: "live", reason: "fresh" },
              },
              snapshot: {
                cpu_percent: 81,
                memory_percent: 62,
                disk_percent: 47,
                gpus: [{ index: 0, name: "A100", utilization_gpu: 93 }],
                metadata: {},
              },
              repos: [
                {
                  path: "/repo-a",
                  branch: "main",
                  dirty: false,
                  ahead: 0,
                  behind: 0,
                  staged: 0,
                  unstaged: 0,
                  untracked: 0,
                  last_updated_at: null,
                  freshness: { state: "live", reason: "fresh" },
                },
              ],
              clash: {},
            },
          ],
        ]);

        __testExports.renderMonitor();

        if (grid.innerHTML.includes("server-summary-rail")) {
          throw new Error("summary rail rendered for server without system/gpu panels");
        }
        if (grid.innerHTML.includes("freshness-cached")) {
          throw new Error("freshness badge leaked from disabled panels");
        }
        """
    )


def test_render_monitor_displays_command_health_strip_for_enabled_panels():
    _run_app_js_test(
        """
        const grid = document.getElementById("monitor-grid");
        globalThis.__querySelectorAll = () => [];

        __testExports.state.updates = new Map([
          [
            "server-a",
            {
              server_id: "server-a",
              enabled_panels: ["system", "git"],
              command_health: {
                system: { state: "healthy", label: "182ms", detail: "Last poll succeeded" },
                git: { state: "failed", label: "failed", detail: "Repo failed" },
              },
              freshness: {},
              snapshot: {
                cpu_percent: 10,
                memory_percent: 20,
                disk_percent: 30,
                gpus: [],
                metadata: {},
              },
              repos: [],
              clash: {},
            },
          ],
        ]);

        __testExports.renderMonitor();

        if (!grid.innerHTML.includes("command-health-strip")) {
          throw new Error("missing command health strip");
        }
        if (!grid.innerHTML.includes("182ms")) {
          throw new Error("healthy latency label missing");
        }
        if (!grid.innerHTML.includes(">failed<")) {
          throw new Error("degraded state label missing");
        }
        """
    )


def test_render_monitor_command_health_strip_preserves_panel_order_and_hides_ok_text():
    _run_app_js_test(
        """
        const grid = document.getElementById("monitor-grid");
        globalThis.__querySelectorAll = () => [];

        __testExports.state.updates = new Map([
          [
            "server-a",
            {
              server_id: "server-a",
              enabled_panels: ["gpu", "git", "clash"],
              command_health: {
                gpu: { state: "healthy", label: "244ms", detail: "GPU ok" },
                git: { state: "retrying", label: "retry x2", detail: "Git retry" },
                clash: { state: "cooldown", label: "cooldown", detail: "Clash cooling down" },
              },
              freshness: {},
              snapshot: {
                cpu_percent: 10,
                memory_percent: 20,
                disk_percent: 30,
                gpus: [],
                metadata: {},
              },
              repos: [],
              clash: {},
            },
          ],
        ]);

        __testExports.renderMonitor();

        const gpuIndex = grid.innerHTML.indexOf('data-command-health-panel="gpu"');
        const gitIndex = grid.innerHTML.indexOf('data-command-health-panel="git"');
        const clashIndex = grid.innerHTML.indexOf('data-command-health-panel="clash"');

        if (!(gpuIndex >= 0 && gpuIndex < gitIndex && gitIndex < clashIndex)) {
          throw new Error(`unexpected command health order: ${grid.innerHTML}`);
        }
        if (grid.innerHTML.includes(">ok<")) {
          throw new Error("healthy chips should not render ok text");
        }
        """
    )


def test_add_server_card_defaults_open_only_when_no_servers():
    _run_app_js_test(
        """
        const shell = document.getElementById("settings-shell");
        const addCard = document.getElementById("settings-add-card");

        __testExports.state.settings = { servers: [] };
        __testExports.state.settingsAddTouched = false;
        __testExports.renderSettings();
        const emptyState = shell.dataset.addExpanded || addCard.dataset.expanded || "missing";

        __testExports.state.settings = {
          servers: [
            {
              server_id: "server-a",
              ssh_alias: "alias-a",
              working_dirs: ["/work/a"],
              enabled_panels: ["system"],
              clash_api_probe_url: "http://127.0.0.1:9090/version",
              clash_ui_probe_url: "http://127.0.0.1:9090/ui",
            },
          ],
        };
        __testExports.state.settingsAddTouched = false;
        __testExports.renderSettings();
        const existingState = shell.dataset.addExpanded || addCard.dataset.expanded || "missing";

        if (emptyState !== "open") {
          throw new Error(`expected empty-state add card to be open, got ${emptyState}`);
        }
        if (existingState !== "collapsed") {
          throw new Error(`expected existing-state add card to be collapsed, got ${existingState}`);
        }
        """
    )


def test_render_settings_includes_global_notification_controls():
    _run_app_js_test(
        """
        const card = document.getElementById("settings-notifications-card");

        __testExports.state.settings = {
          notifications: {
            desktop_enabled: true,
            webhook_enabled: false,
            webhook_url: "https://hooks.example.test/server-monitor",
          },
          servers: [],
        };

        __testExports.renderSettings();

        if (!card.innerHTML.includes("Notification Settings")) {
          throw new Error("global notifications card missing");
        }
        if (!card.innerHTML.includes("https://hooks.example.test/server-monitor")) {
          throw new Error("notification webhook url missing");
        }
        """
    )


def test_export_diagnostics_downloads_json_bundle():
    _run_app_js_test(
        """
        let fetchedUrl = "";

        globalThis.__fetch = async (url) => {
          fetchedUrl = url;
          return {
            ok: true,
            status: 200,
            json: async () => ({ generated_at: "2026-03-11T15:20:00Z", servers: [] }),
            text: async () => "",
          };
        };

        if (typeof __testExports.exportDiagnostics !== "function") {
          throw new Error("exportDiagnostics missing");
        }

        await __testExports.exportDiagnostics();

        if (fetchedUrl !== "/api/diagnostics") {
          throw new Error(`unexpected diagnostics url: ${fetchedUrl}`);
        }
        """
    )


def test_command_health_transition_notifies_only_once_until_recovery():
    _run_app_js_test(
        """
        const sent = [];
        globalThis.Notification = function(title, options) {
          sent.push({ title, body: options && options.body ? options.body : "" });
        };
        globalThis.Notification.permission = "granted";

        __testExports.state.settings = {
          notifications: {
            desktop_enabled: true,
            webhook_enabled: false,
            webhook_url: "",
          },
          servers: [],
        };

        if (typeof __testExports.processNotificationTransitions !== "function") {
          throw new Error("processNotificationTransitions missing");
        }

        await __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            git: { state: "failed", detail: "One or more repos failed", updated_at: "2026-03-11T15:20:00Z" },
          },
        });
        await __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            git: { state: "failed", detail: "One or more repos failed", updated_at: "2026-03-11T15:21:00Z" },
          },
        });
        await __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            git: { state: "healthy", detail: "All repos healthy", updated_at: "2026-03-11T15:22:00Z" },
          },
        });
        await __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            git: { state: "cooldown", detail: "One or more repos are cooling down", updated_at: "2026-03-11T15:23:00Z" },
          },
        });

        if (sent.length !== 2) {
          throw new Error(`expected 2 notifications, got ${sent.length}`);
        }
        """
    )


def test_command_health_transition_posts_webhook_payload():
    _run_app_js_test(
        """
        const webhookCalls = [];
        globalThis.Notification = undefined;
        globalThis.__fetch = async (url, options = {}) => {
          webhookCalls.push({ url, options });
          return {
            ok: true,
            status: 200,
            json: async () => ({}),
            text: async () => "",
          };
        };

        __testExports.state.settings = {
          notifications: {
            desktop_enabled: false,
            webhook_enabled: true,
            webhook_url: "https://hooks.example.test/server-monitor",
          },
          servers: [],
        };

        if (typeof __testExports.processNotificationTransitions !== "function") {
          throw new Error("processNotificationTransitions missing");
        }

        await __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            clash: { state: "cooldown", detail: "Command cooling down after repeated failures", updated_at: "2026-03-11T15:20:00Z" },
          },
        });

        if (webhookCalls.length !== 1) {
          throw new Error(`expected 1 webhook call, got ${webhookCalls.length}`);
        }
        if (webhookCalls[0].url !== "https://hooks.example.test/server-monitor") {
          throw new Error("webhook url mismatch");
        }
        if (!String(webhookCalls[0].options.body).includes("\\"panel\\":\\"clash\\"")) {
          throw new Error("webhook payload missing panel");
        }
        """
    )


def test_add_server_card_collapses_and_resets_after_add():
    _run_app_js_test(
        """
        const shell = document.getElementById("settings-shell");
        const form = document.getElementById("add-server-form");
        const serverIdInput = document.getElementById("new-server-id");
        const aliasInput = document.getElementById("new-server-alias");
        const dirsInput = document.getElementById("new-server-dirs");
        const apiProbeInput = document.getElementById("new-clash-api-probe-url");
        const uiProbeInput = document.getElementById("new-clash-ui-probe-url");

        const panelInputs = [
          { value: "system", checked: true },
          { value: "gpu", checked: true },
          { value: "git", checked: true },
          { value: "clash", checked: true },
        ];

        globalThis.__querySelectorAll = (selector) => {
          if (selector === 'input[name="new-panel"]:checked') {
            return panelInputs.filter((input) => input.checked);
          }
          if (selector === 'input[name="new-panel"]') {
            return panelInputs;
          }
          return [];
        };

        globalThis.__fetch = async (url, options = {}) => {
          if (url === "/api/servers" && options.method === "POST") {
            return {
              status: 204,
              ok: true,
              json: async () => null,
              text: async () => "",
            };
          }
          if (url === "/api/settings" && options.method === "GET") {
            return {
              status: 200,
              ok: true,
              json: async () => ({
                servers: [
                  {
                    server_id: "server-a",
                    ssh_alias: "gpu-a",
                    working_dirs: ["/work/a"],
                    enabled_panels: ["system", "gpu", "git", "clash"],
                    clash_api_probe_url: "http://127.0.0.1:9090/version",
                    clash_ui_probe_url: "http://127.0.0.1:9090/ui",
                  },
                ],
              }),
              text: async () => "",
            };
          }
          return {
            status: 204,
            ok: true,
            json: async () => null,
            text: async () => "",
          };
        };

        serverIdInput.value = "server-a";
        aliasInput.value = "gpu-a";
        dirsInput.value = "/work/a";
        apiProbeInput.value = "http://127.0.0.1:19090/version";
        uiProbeInput.value = "http://127.0.0.1:19090/ui";
        form.reset = () => {
          serverIdInput.value = "";
          aliasInput.value = "";
          dirsInput.value = "";
          apiProbeInput.value = "";
          uiProbeInput.value = "";
        };

        if (typeof __testExports.bindAddServerForm !== "function") {
          throw new Error("bindAddServerForm missing");
        }

        __testExports.bindAddServerForm();
        await form.__listeners.submit({ preventDefault() {} });

        const collapsedAfterAdd = (shell.dataset.addExpanded || "missing") === "collapsed";
        const serverIdAfterCollapse = serverIdInput.value;

        if (!collapsedAfterAdd) {
          throw new Error("add card did not collapse after successful add");
        }
        if (serverIdAfterCollapse !== "") {
          throw new Error("add form did not reset after collapsing");
        }
        """
    )


def test_settings_editor_footer_reflects_dirty_state():
    _run_app_js_test(
        """
        const panel = document.getElementById("settings-editor-panel");

        __testExports.state.settings = {
          servers: [
            {
              server_id: "server-a",
              ssh_alias: "alias-a",
              working_dirs: ["/work/a"],
              enabled_panels: ["system", "gpu"],
              clash_api_probe_url: "http://127.0.0.1:9090/version",
              clash_ui_probe_url: "http://127.0.0.1:9090/ui",
            },
          ],
        };
        __testExports.state.selectedSettingsServerId = "server-a";
        __testExports.state.settingsDrafts.clear();

        __testExports.renderSettingsEditorPanel(__testExports.state.settings.servers);
        const cleanState = panel.innerHTML.includes('data-dirty-state="clean"') ? "clean" : "missing";

        __testExports.state.settingsDrafts.set("server-a", {
          server_id: "server-a",
          ssh_alias: "edited-alias-a",
          working_dirs_raw: "/work/a\\n/work/b",
          clash_api_probe_url: "http://127.0.0.1:9090/version",
          clash_ui_probe_url: "http://127.0.0.1:9090/ui",
          enabled_panels: ["system", "gpu"],
        });

        __testExports.renderSettingsEditorPanel(__testExports.state.settings.servers);
        const dirtyState = panel.innerHTML.includes('data-dirty-state="dirty"') ? "dirty" : "clean";

        if (cleanState !== "clean") {
          throw new Error("editor footer did not render a clean state");
        }
        if (dirtyState !== "dirty") {
          throw new Error("editor footer did not render a dirty state");
        }
        """
    )


def test_settings_split_view_keeps_drafts_when_switching_rows():
    _run_app_js_test(
        """
        const panel = document.getElementById("settings-editor-panel");
        document.getElementById("settings-overview");

        const editorFields = {
          '[data-field="ssh_alias"]': { value: "draft-alias-a" },
          '[data-field="working_dirs"]': { value: "/work/a\\n/work/b" },
          '[data-field="clash_api_probe_url"]': { value: "http://127.0.0.1:19090/version" },
          '[data-field="clash_ui_probe_url"]': { value: "http://127.0.0.1:19090/ui" },
        };

        const activeEditor = {
          getAttribute(name) {
            return name === "data-server-id" ? "server-a" : null;
          },
          querySelector(selector) {
            return editorFields[selector] || null;
          },
          querySelectorAll(selector) {
            if (selector === "input[data-panel]:checked") {
              return [
                { getAttribute() { return "system"; } },
                { getAttribute() { return "git"; } },
              ];
            }
            return [];
          },
        };

        globalThis.__querySelector = (selector) =>
          selector === ".server-editor[data-server-id]" ? activeEditor : null;
        globalThis.__querySelectorAll = () => [];

        __testExports.state.settings = {
          servers: [
            {
              server_id: "server-a",
              ssh_alias: "alias-a",
              working_dirs: ["/work/a"],
              enabled_panels: ["system"],
              clash_api_probe_url: "http://127.0.0.1:9090/version",
              clash_ui_probe_url: "http://127.0.0.1:9090/ui",
            },
            {
              server_id: "server-b",
              ssh_alias: "alias-b",
              working_dirs: ["/work/b"],
              enabled_panels: ["git"],
              clash_api_probe_url: "http://127.0.0.1:9090/version",
              clash_ui_probe_url: "http://127.0.0.1:9090/ui",
            },
          ],
        };
        __testExports.state.selectedSettingsServerId = "server-a";

        if (typeof __testExports.selectSettingsServer !== "function") {
          throw new Error("selectSettingsServer missing");
        }

        __testExports.selectSettingsServer("server-b");

        if (!(__testExports.state.settingsDrafts instanceof Map)) {
          throw new Error("settings drafts store missing");
        }
        const draft = __testExports.state.settingsDrafts.get("server-a");
        if (!draft) {
          throw new Error("current editor draft was not captured");
        }
        if (draft.ssh_alias !== "draft-alias-a") {
          throw new Error("ssh alias draft was not preserved");
        }
        if (!draft.working_dirs_raw.includes("/work/b")) {
          throw new Error("working directory draft was not preserved");
        }
        if (__testExports.state.selectedSettingsServerId !== "server-b") {
          throw new Error("settings selection did not change");
        }

        globalThis.__querySelector = () => null;
        __testExports.selectSettingsServer("server-a");
        if (!panel.innerHTML.includes("draft-alias-a")) {
          throw new Error("draft was not restored when returning to the server");
        }
        if (!panel.innerHTML.includes('data-dirty-state="dirty"')) {
          throw new Error("restored draft did not mark the footer as dirty");
        }
        """
    )


def test_render_server_summary_uses_active_gpu_count_and_peak_utilization():
    _run_app_js_test(
        """
        if (typeof __testExports.renderServerSummary !== "function") {
          throw new Error("renderServerSummary missing");
        }

        const html = __testExports.renderServerSummary(
          {
            gpus: [
              { index: 0, utilization_gpu: 97 },
              { index: 1, utilization_gpu: 41 },
              { index: 2, utilization_gpu: 4 },
            ],
          },
          new Set(["gpu"])
        );

        if (!html.includes("2/3 active")) {
          throw new Error("gpu summary does not show active/total usage");
        }
        if (!html.includes("peak 97%")) {
          throw new Error("gpu summary does not show peak utilization");
        }
        if (html.includes(">97%<")) {
          throw new Error("gpu summary still uses peak utilization as the primary value");
        }
        """
    )
