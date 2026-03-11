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
            addEventListener() {{}},
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
          fetch: async () => ({{
            status: 204,
            ok: true,
            json: async () => ({{ servers: [] }}),
            text: async () => "",
          }}),
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
          }};
          `,
          sandbox,
        );
        const __testExports = sandbox.__testExports;

        {js_test}
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
