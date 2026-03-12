"""Build the remote shell loop used for agentless metrics streaming."""

from __future__ import annotations


DEFAULT_SAMPLE_INTERVAL_SECONDS = 0.25
DEFAULT_DISK_REFRESH_SECONDS = 5.0


def build_metrics_stream_command(
    *,
    sample_interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
    disk_interval_seconds: float = DEFAULT_DISK_REFRESH_SECONDS,
) -> str:
    """Return a POSIX-shell metrics loop that emits one JSON sample per line."""

    normalized_sample_interval = max(0.1, float(sample_interval_seconds))
    normalized_disk_interval = max(normalized_sample_interval, float(disk_interval_seconds))
    disk_refresh_ticks = max(1, int(round(normalized_disk_interval / normalized_sample_interval)))
    sleep_text = _format_decimal(normalized_sample_interval)

    return f"""
SAMPLE_INTERVAL_SECONDS={sleep_text}
DISK_REFRESH_TICKS={disk_refresh_ticks}
DISK_TICK=0
SEQUENCE=0
PREV_RX_BYTES=""
PREV_TX_BYTES=""
JSON_LINE=""
DISK_VALUE=0

json_escape() {{
  printf '%s' "$1" | sed 's/\\\\/\\\\\\\\/g; s/"/\\\\"/g'
}}

read_net_bytes() {{
  awk -F'[: ]+' '
    $1 !~ /^(lo|)$/ {{
      rx += $3
      tx += $11
    }}
    END {{
      if (rx == "") rx = 0
      if (tx == "") tx = 0
      printf "%s %s", rx, tx
    }}
  ' /proc/net/dev
}}

build_gpu_json() {{
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    printf '[]'
    return
  fi

  GPU_LINES=$(nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null || true)
  if [ -z "$GPU_LINES" ]; then
    printf '[]'
    return
  fi

  printf '%s\\n' "$GPU_LINES" | awk -F',' '
    BEGIN {{ first = 1; printf "[" }}
    {{
      name = $2
      gsub(/^ +| +$/, "", name)
      gsub(/\\\\/, "\\\\\\\\", name)
      gsub(/"/, "\\\\\\"", name)

      util = $3
      mem_used = $4
      mem_total = $5
      temp = $6
      gsub(/^ +| +$/, "", util)
      gsub(/^ +| +$/, "", mem_used)
      gsub(/^ +| +$/, "", mem_total)
      gsub(/^ +| +$/, "", temp)

      if (!first) printf ","
      printf "{{\\"index\\":%s,\\"name\\":\\"%s\\",\\"utilization_gpu_percent\\":%s,\\"memory_used_mib\\":%s,\\"memory_total_mib\\":%s,\\"temperature_celsius\\":%s}}", $1, name, util, mem_used, mem_total, temp
      first = 0
    }}
    END {{ printf "]" }}
  '
}}

NET_VALUES=$(read_net_bytes)
PREV_RX_BYTES=${{NET_VALUES%% *}}
PREV_TX_BYTES=${{NET_VALUES##* }}

while :; do
  CPU_VALUE=$(top -bn1 | awk '/Cpu\\(s\\)/ {{print 100-$8; exit}}')
  MEM_VALUE=$(free | awk '/Mem:/ {{printf "%.2f", ($3/$2)*100}}')

  if [ "$DISK_TICK" -le 0 ]; then
    DISK_VALUE=$(df -P / | awk 'NR==2 {{gsub(/%/,"",$5); print $5}}')
    DISK_TICK=$DISK_REFRESH_TICKS
  fi
  DISK_TICK=$((DISK_TICK - 1))

  NET_VALUES=$(read_net_bytes)
  RX_BYTES=${{NET_VALUES%% *}}
  TX_BYTES=${{NET_VALUES##* }}
  RX_KBPS=$(awk "BEGIN {{printf \\"%.2f\\", (($RX_BYTES - $PREV_RX_BYTES) / 1024) / $SAMPLE_INTERVAL_SECONDS}}")
  TX_KBPS=$(awk "BEGIN {{printf \\"%.2f\\", (($TX_BYTES - $PREV_TX_BYTES) / 1024) / $SAMPLE_INTERVAL_SECONDS}}")
  PREV_RX_BYTES=$RX_BYTES
  PREV_TX_BYTES=$TX_BYTES

  GPU_JSON=$(build_gpu_json)
  SERVER_TIME=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")
  SEQUENCE=$((SEQUENCE + 1))

  JSON_LINE=$(printf '{{"sequence":%s,"server_time":"%s","sample_interval_ms":%s,"cpu_percent":%s,"memory_percent":%s,"disk_percent":%s,"network_rx_kbps":%s,"network_tx_kbps":%s,"gpus":%s}}' \
    "$SEQUENCE" \
    "$SERVER_TIME" \
    "{int(round(normalized_sample_interval * 1000))}" \
    "${{CPU_VALUE:-0}}" \
    "${{MEM_VALUE:-0}}" \
    "${{DISK_VALUE:-0}}" \
    "${{RX_KBPS:-0}}" \
    "${{TX_KBPS:-0}}" \
    "$GPU_JSON")
  printf '%s\\n' "$JSON_LINE"
  sleep {sleep_text}
done
""".strip()


def _format_decimal(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")
