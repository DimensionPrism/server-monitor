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
    normalized_disk_interval = max(
        normalized_sample_interval, float(disk_interval_seconds)
    )
    disk_refresh_ticks = max(
        1, int(round(normalized_disk_interval / normalized_sample_interval))
    )
    tegrastats_refresh_ticks = 1
    sample_interval_ms = int(round(normalized_sample_interval * 1000))
    sleep_text = _format_decimal(normalized_sample_interval)

    return f"""
SAMPLE_INTERVAL_SECONDS={sleep_text}
DISK_REFRESH_TICKS={disk_refresh_ticks}
TEGRASTATS_REFRESH_TICKS={tegrastats_refresh_ticks}
TEGRASTATS_SAMPLE_MS={sample_interval_ms}
DISK_TICK=0
TEGRASTATS_TICK=0
SEQUENCE=0
PREV_RX_BYTES=""
PREV_TX_BYTES=""
JSON_LINE=""
DISK_VALUE=0
HAS_TEGRASTATS=0
TEGRASTATS_LOG=""
TEGRASTATS_PID=""
TEGRA_CPU_VALUE=0
TEGRA_MEM_USED_MB=0
TEGRA_MEM_TOTAL_MB=0
TEGRA_GPU_UTIL_VALUE=0
TEGRA_GPU_TEMP_C=0

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

refresh_tegrastats_cache() {{
  if [ "$HAS_TEGRASTATS" -ne 1 ]; then
    return
  fi

  if [ -z "$TEGRASTATS_LOG" ] || [ ! -f "$TEGRASTATS_LOG" ]; then
    return
  fi

  TEGRA_LINE=$(tail -n 1 "$TEGRASTATS_LOG" 2>/dev/null || true)
  if [ -z "$TEGRA_LINE" ]; then
    return
  fi

  TEGRA_CPU_VALUE=$(printf '%s\\n' "$TEGRA_LINE" | awk '
    match($0, /CPU \\[[^]]+\\]/) {{
      block = substr($0, RSTART + 5, RLENGTH - 6)
      n = split(block, items, ",")
      sum = 0
      count = 0
      for (i = 1; i <= n; i++) {{
        if (match(items[i], /[0-9]+%/)) {{
          pct = substr(items[i], RSTART, RLENGTH - 1)
          sum += pct
          count += 1
        }}
      }}
      if (count > 0) {{
        printf "%.2f", sum / count
      }} else {{
        printf "0"
      }}
      found = 1
      exit
    }}
    END {{
      if (!found) {{
        printf "0"
      }}
    }}
  ')

  TEGRA_MEM_USED_MB=$(printf '%s\\n' "$TEGRA_LINE" | awk '
    match($0, /RAM [0-9]+\\/[0-9]+MB/) {{
      block = substr($0, RSTART, RLENGTH)
      gsub(/^RAM /, "", block)
      split(block, parts, "/")
      print parts[1]
      found = 1
      exit
    }}
    END {{
      if (!found) {{
        print 0
      }}
    }}
  ')

  TEGRA_MEM_TOTAL_MB=$(printf '%s\\n' "$TEGRA_LINE" | awk '
    match($0, /RAM [0-9]+\\/[0-9]+MB/) {{
      block = substr($0, RSTART, RLENGTH)
      gsub(/^RAM /, "", block)
      split(block, parts, "/")
      gsub(/MB$/, "", parts[2])
      print parts[2]
      found = 1
      exit
    }}
    END {{
      if (!found) {{
        print 0
      }}
    }}
  ')

  TEGRA_GPU_UTIL_VALUE=$(printf '%s\\n' "$TEGRA_LINE" | awk '
    match($0, /GR3D_FREQ [0-9]+%/) {{
      block = substr($0, RSTART, RLENGTH)
      gsub(/^GR3D_FREQ /, "", block)
      gsub(/%$/, "", block)
      print block
      found = 1
      exit
    }}
    END {{
      if (!found) {{
        print 0
      }}
    }}
  ')

  TEGRA_GPU_TEMP_C=$(printf '%s\\n' "$TEGRA_LINE" | awk '
    match($0, /gpu@[0-9]+(\\.[0-9]+)?C/) {{
      block = substr($0, RSTART, RLENGTH)
      gsub(/^gpu@/, "", block)
      gsub(/C$/, "", block)
      print block
      found = 1
      exit
    }}
    END {{
      if (!found) {{
        print 0
      }}
    }}
  ')
}}

build_tegrastats_gpu_json() {{
  printf '[{{"index":0,"name":"Jetson iGPU","utilization_gpu_percent":%s,"memory_used_mib":%s,"memory_total_mib":%s,"temperature_celsius":%s}}]' \
    "${{TEGRA_GPU_UTIL_VALUE:-0}}" \
    "${{TEGRA_MEM_USED_MB:-0}}" \
    "${{TEGRA_MEM_TOTAL_MB:-0}}" \
    "${{TEGRA_GPU_TEMP_C:-0}}"
}}

build_gpu_json() {{
  if command -v nvidia-smi >/dev/null 2>&1; then
    GPU_LINES=$(nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null || true)
    if [ -n "$GPU_LINES" ]; then
      if printf '%s\\n' "$GPU_LINES" | grep -q '\\[N/A\\]'; then
        if [ "$HAS_TEGRASTATS" -eq 1 ]; then
          build_tegrastats_gpu_json
          return
        fi
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
          if (util !~ /^-?[0-9]+(\\.[0-9]+)?$/) util = 0
          if (mem_used !~ /^-?[0-9]+(\\.[0-9]+)?$/) mem_used = 0
          if (mem_total !~ /^-?[0-9]+(\\.[0-9]+)?$/) mem_total = 0
          if (temp !~ /^-?[0-9]+(\\.[0-9]+)?$/) temp = 0

          if (!first) printf ","
          printf "{{\\"index\\":%s,\\"name\\":\\"%s\\",\\"utilization_gpu_percent\\":%s,\\"memory_used_mib\\":%s,\\"memory_total_mib\\":%s,\\"temperature_celsius\\":%s}}", $1, name, util, mem_used, mem_total, temp
          first = 0
        }}
        END {{ printf "]" }}
      '
      return
    fi
  fi

  if [ "$HAS_TEGRASTATS" -eq 1 ]; then
    build_tegrastats_gpu_json
    return
  fi

  printf '[]'
}}

cleanup_tegrastats() {{
  if [ -n "$TEGRASTATS_PID" ]; then
    kill "$TEGRASTATS_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$TEGRASTATS_LOG" ]; then
    rm -f "$TEGRASTATS_LOG" >/dev/null 2>&1 || true
  fi
}}

trap cleanup_tegrastats EXIT INT TERM

NET_VALUES=$(read_net_bytes)
PREV_RX_BYTES=${{NET_VALUES%% *}}
PREV_TX_BYTES=${{NET_VALUES##* }}

if command -v tegrastats >/dev/null 2>&1; then
  HAS_TEGRASTATS=1
  TEGRASTATS_LOG=$(mktemp)
  tegrastats --interval "$TEGRASTATS_SAMPLE_MS" >"$TEGRASTATS_LOG" 2>/dev/null &
  TEGRASTATS_PID=$!
fi

while :; do
  if [ "$HAS_TEGRASTATS" -eq 1 ] && [ "$TEGRASTATS_TICK" -le 0 ]; then
    refresh_tegrastats_cache
    TEGRASTATS_TICK=$TEGRASTATS_REFRESH_TICKS
  fi
  if [ "$HAS_TEGRASTATS" -eq 1 ]; then
    TEGRASTATS_TICK=$((TEGRASTATS_TICK - 1))
  fi

  if [ "$HAS_TEGRASTATS" -eq 1 ] && [ "${{TEGRA_MEM_TOTAL_MB:-0}}" -gt 0 ]; then
    CPU_VALUE=${{TEGRA_CPU_VALUE:-0}}
    MEM_VALUE=$(awk "BEGIN {{printf \\"%.2f\\", (${{TEGRA_MEM_USED_MB:-0}}/${{TEGRA_MEM_TOTAL_MB:-1}})*100}}")
  else
    CPU_VALUE=$(top -bn1 | awk '/Cpu\\(s\\)/ {{print 100-$8; exit}}')
    MEM_VALUE=$(free | awk '/Mem:/ {{printf "%.2f", ($3/$2)*100}}')
  fi

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
  SERVER_TIME=$(date -u +"%Y-%m-%dT%H:%M:%S.%3N+00:00")
  SEQUENCE=$((SEQUENCE + 1))

  JSON_LINE=$(printf '{{"sequence":%s,"server_time":"%s","sample_interval_ms":%s,"cpu_percent":%s,"memory_percent":%s,"disk_percent":%s,"network_rx_kbps":%s,"network_tx_kbps":%s,"gpus":%s}}' \
    "$SEQUENCE" \
    "$SERVER_TIME" \
    "{sample_interval_ms}" \
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
