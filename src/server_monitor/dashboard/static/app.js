function setText(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
  }
}

function render(update) {
  const targetId = update.server_id === "server-a" ? "server-a-metrics" : "server-b-metrics";
  const metrics = update.snapshot || {};
  const metricsText = [
    `CPU: ${metrics.cpu_percent ?? "--"}%`,
    `MEM: ${metrics.memory_percent ?? "--"}%`,
    `DISK: ${metrics.disk_percent ?? "--"}%`,
    `NET RX/TX: ${metrics.network_rx_kbps ?? "--"} / ${metrics.network_tx_kbps ?? "--"}`,
  ].join("\n");
  setText(targetId, metricsText);

  setText("gpu-status", JSON.stringify(metrics.gpus ?? [], null, 2));
  setText("repo-status", JSON.stringify(update.repos ?? [], null, 2));
  setText("clash-status", JSON.stringify(update.clash ?? {}, null, 2));
}

function connect() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      render(payload);
    } catch (_) {
      // Ignore malformed frames.
    }
  };
  ws.onclose = () => {
    setTimeout(connect, 1000);
  };
}

connect();

