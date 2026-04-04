"""Pure helper functions extracted from runtime.py."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import TYPE_CHECKING

from server_monitor.dashboard.command_policy import CommandPolicy

if TYPE_CHECKING:
    from server_monitor.dashboard.settings import ServerSettings

DEFAULT_CLASH = {
    "running": False,
    "api_reachable": False,
    "ui_reachable": False,
    "message": "not-collected",
    "ip_location": "",
    "controller_port": "",
}
GIT_OPERATION_TIMEOUT_SECONDS = 20.0
STATUS_COMMAND_TIMEOUT_SECONDS = 3.0
STATUS_POLL_INLINE_BUDGET_SECONDS = 0.05
COMMAND_HEALTH_HISTORY_LIMIT = 20


def _needs_status_poll(
    *, last: datetime | None, now: datetime, interval_seconds: float
) -> bool:
    if last is None:
        return True
    return (now - last).total_seconds() >= interval_seconds


def _metrics_sleep_seconds(*, interval_seconds: float, elapsed_seconds: float) -> float:
    target_interval_seconds = max(0.5, interval_seconds)
    return max(0.05, target_interval_seconds - elapsed_seconds)


def _find_server(servers: list[ServerSettings], server_id: str) -> ServerSettings:
    for server in servers:
        if server.server_id == server_id:
            return server
    raise KeyError(f"unknown server '{server_id}'")


def _serialize_runtime_settings(settings) -> dict:
    return {
        "metrics_interval_seconds": settings.metrics_interval_seconds,
        "status_interval_seconds": settings.status_interval_seconds,
        "servers": [
            {
                "server_id": server.server_id,
                "ssh_alias": server.ssh_alias,
                "working_dirs": list(server.working_dirs),
                "enabled_panels": list(server.enabled_panels),
                "clash_api_probe_url": server.clash_api_probe_url,
                "clash_ui_probe_url": server.clash_ui_probe_url,
            }
            for server in settings.servers
        ],
    }


def _is_ssh_unreachable(result) -> bool:
    blob = f"{result.error or ''} {result.stderr or ''}".lower()
    return any(
        token in blob
        for token in [
            "timeout",
            "timed out",
            "could not resolve hostname",
            "connection refused",
            "network is unreachable",
            "no route to host",
        ]
    )


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _group_batch_sections(sections) -> dict[tuple[str, str], dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for section in sections:
        grouped.setdefault((section.kind, section.target), {})[section.stream] = section
    return grouped


def _empty_repo_status(path: str) -> dict[str, str | int | bool | None]:
    return {
        "path": path,
        "branch": "unknown",
        "dirty": False,
        "ahead": 0,
        "behind": 0,
        "staged": 0,
        "unstaged": 0,
        "untracked": 0,
        "last_commit_age_seconds": 0,
        "last_updated_at": None,
    }


def _empty_system_snapshot() -> dict[str, float]:
    return {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "disk_percent": 0.0,
        "network_rx_kbps": 0.0,
        "network_tx_kbps": 0.0,
    }


def _system_command() -> str:
    return (
        "CPU=$(top -bn1 | awk '/Cpu\\(s\\)/ {print 100-$8; exit}'); "
        "MEM=$(free | awk '/Mem:/ {printf \"%.2f\", ($3/$2)*100}'); "
        "DISK=$(df -P / | awk 'NR==2 {gsub(/%/,\"\",$5); print $5}'); "
        'echo "CPU: ${CPU:-0}"; '
        'echo "MEM: ${MEM:-0}"; '
        'echo "DISK: ${DISK:-0}"; '
        'echo "RX_KBPS: 0"; '
        'echo "TX_KBPS: 0"'
    )


def _gpu_command() -> str:
    return "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits"


def _git_status_command(repo: str) -> str:
    return f"git -C {_shell_quote(repo)} status --porcelain --branch"


SAFE_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _git_operation_command(
    *, repo_path: str, operation: str, branch: str | None
) -> str:
    quoted_repo = _shell_quote(repo_path)

    if operation == "refresh":
        return _git_status_command(repo_path)
    if operation == "fetch":
        return f"git -C {quoted_repo} fetch --prune --tags"
    if operation == "pull":
        return f"git -C {quoted_repo} pull --ff-only"
    if operation == "checkout":
        if branch is None or branch.strip() == "":
            raise ValueError("branch is required for checkout")
        normalized_branch = branch.strip()
        if not _is_valid_branch_name(normalized_branch):
            raise ValueError("invalid branch name")
        return f"git -C {quoted_repo} checkout {_shell_quote(normalized_branch)}"
    raise ValueError(f"unsupported operation '{operation}'")


def _is_valid_branch_name(branch: str) -> bool:
    if not SAFE_BRANCH_RE.fullmatch(branch):
        return False
    if branch.startswith("-"):
        return False
    if ".." in branch or "@{" in branch:
        return False
    return True


def _should_retry(*, policy: CommandPolicy, failure_class: str) -> bool:
    if failure_class == "timeout":
        return policy.retry_on_timeout
    if failure_class == "ssh_unreachable":
        return policy.retry_on_ssh_error
    if failure_class == "nonzero_exit":
        return policy.retry_on_nonzero_exit
    return False


def _build_freshness_entry(
    *,
    now: datetime,
    last_updated_at: str | None,
    last_poll_ok: bool | None,
    threshold_seconds: float,
    keep_live_while_inflight: bool = False,
) -> dict[str, str | int | float | None]:
    age_seconds = _age_seconds_from_iso(now=now, timestamp_iso=last_updated_at)
    normalized_threshold = float(max(1.0, threshold_seconds))

    if last_poll_ok is False:
        state = "cached"
        reason = "poll_error"
    elif age_seconds is None:
        state = "cached"
        reason = "no_data"
    elif age_seconds > normalized_threshold:
        if keep_live_while_inflight:
            state = "live"
            reason = "poll_inflight"
        else:
            state = "cached"
            reason = "age_expired"
    else:
        state = "live"
        reason = "ok"

    return {
        "state": state,
        "reason": reason,
        "last_updated_at": last_updated_at,
        "age_seconds": age_seconds if age_seconds is not None else 0,
        "threshold_seconds": normalized_threshold,
    }


def _age_seconds_from_iso(*, now: datetime, timestamp_iso: str | None) -> int | None:
    if not timestamp_iso:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _metrics_stream_transport_latency_ms(
    *,
    sample_server_time: str | None,
    received_at: datetime,
    sample_interval_ms: int | None = None,
) -> int | None:
    if not sample_server_time:
        return None
    try:
        parsed = datetime.fromisoformat(sample_server_time)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    latency_ms = int((received_at - parsed).total_seconds() * 1000)
    if latency_ms < 0:
        return None
    max_latency_ms = _metrics_stream_latency_upper_bound_ms(sample_interval_ms)
    if latency_ms > max_latency_ms:
        return None
    return latency_ms


def _metrics_stream_latency_upper_bound_ms(sample_interval_ms: int | None) -> int:
    floor_ms = 5000
    multiplier = 20
    if sample_interval_ms is None:
        return floor_ms
    try:
        interval_ms = int(sample_interval_ms)
    except (TypeError, ValueError):
        return floor_ms
    if interval_ms <= 0:
        return floor_ms
    return max(floor_ms, interval_ms * multiplier)


def _extract_clash_secret(output: str) -> str | None:
    if not output:
        return None
    ansi_cleaned = re.sub(r"\x1b\[[0-9;]*m", "", output)
    patterns = [
        r"当前密钥\s*[:：]\s*(\S+)",
        r"current\s+secret\s*[:：]\s*(\S+)",
        r"secret\s*[:：]\s*(\S+)",
    ]
    for raw_line in ansi_cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                secret = match.group(1).strip().strip("'\"")
                if secret:
                    return secret
    return None


def _parse_required_clash_secret(output: str) -> str:
    secret = _extract_clash_secret(output)
    if secret:
        return secret
    raise ValueError("secret-unavailable")


def _batched_clash_secret_command() -> str:
    secret_command = _clash_secret_command()
    return (
        "__sm_secret_out=$(mktemp); "
        "__sm_secret_err=$(mktemp); "
        f'sh -lc {_shell_quote(secret_command)} >"$__sm_secret_out" 2>"$__sm_secret_err"; '
        "__sm_secret_exit=$?; "
        'cat "$__sm_secret_out"; '
        'cat "$__sm_secret_err" >&2; '
        'if [ "$__sm_secret_exit" -eq 0 ]; then '
        "__sm_clash_secret=$(sed -nE "
        '"s/.*当前密钥[[:space:]]*[:：][[:space:]]*([^[:space:]]+).*/\\1/p; '
        "s/.*[Cc]urrent[[:space:]]+[Ss]ecret[[:space:]]*[:：][[:space:]]*([^[:space:]]+).*/\\1/p; "
        's/.*[Ss]ecret[[:space:]]*[:：][[:space:]]*([^[:space:]]+).*/\\1/p" '
        "\"$__sm_secret_out\" | head -n1 | tr -d '\\r' | tr -d '\"' | tr -d \"'\" | xargs); "
        "else __sm_clash_secret=''; fi; "
        'rm -f "$__sm_secret_out" "$__sm_secret_err"; '
        '[ "$__sm_secret_exit" -eq 0 ]'
    )


def _clash_secret_command() -> str:
    return (
        "if command -v clashsecret >/dev/null 2>&1; then "
        "clashsecret; "
        "elif command -v clashctl >/dev/null 2>&1; then "
        "clashctl secret; "
        "else "
        "for CANDIDATE in "
        "$HOME/clashctl/resources/runtime.yaml "
        "$HOME/clash-for-linux-install/resources/runtime.yaml "
        "; do "
        'if [ -r "$CANDIDATE" ]; then '
        "SECRET=$(sed -n 's/^secret:[[:space:]]*//p' \"$CANDIDATE\" | head -n1 | tr -d '\\r' | xargs); "
        'if [ -n "$SECRET" ]; then echo "当前密钥：$SECRET"; exit 0; fi; '
        "fi; "
        "done; "
        "echo 'secret-unavailable' >&2; "
        "exit 1; "
        "fi"
    )


def _batched_clash_probe_command(
    *,
    api_probe_url: str = "http://127.0.0.1:9090/version",
    ui_probe_url: str = "http://127.0.0.1:9090/ui",
) -> str:
    api_url = _shell_quote(api_probe_url)
    ui_url = _shell_quote(ui_probe_url)
    return (
        'if [ -z "$__sm_clash_secret" ]; then '
        "echo 'secret-unavailable' >&2; "
        "exit 1; "
        "fi; "
        'AUTH_HEADER="Authorization: Bearer $__sm_clash_secret"; '
        f"API_URL={api_url}; "
        f"UI_URL={ui_url}; "
        "if pgrep -f clash >/dev/null; then echo running=true; else echo running=false; fi; "
        "if command -v curl >/dev/null 2>&1; then "
        'API_CODE=$(curl -sS -o /dev/null -w \'%{http_code}\' --connect-timeout 1 --max-time 2 -H "$AUTH_HEADER" "$API_URL" || echo 000); '
        'UI_CODE=$(curl -sS -o /dev/null -w \'%{http_code}\' --connect-timeout 1 --max-time 2 -H "$AUTH_HEADER" "$UI_URL" || echo 000); '
        'if [ "$API_CODE" -ge 200 ] && [ "$API_CODE" -lt 400 ]; then echo api_reachable=true; else echo api_reachable=false; fi; '
        'if [ "$UI_CODE" -ge 200 ] && [ "$UI_CODE" -lt 400 ]; then echo ui_reachable=true; else echo ui_reachable=false; fi; '
        'if [ "$API_CODE" -ge 200 ] && [ "$API_CODE" -lt 400 ] && [ "$UI_CODE" -ge 200 ] && [ "$UI_CODE" -lt 400 ]; then echo message=ok; else echo message=probe-error; fi; '
        "CTRL_PORT=unknown; "
        "PROXY_URL=; "
        "for CANDIDATE in "
        "$HOME/clashctl/resources/runtime.yaml "
        "$HOME/clash-for-linux-install/resources/runtime.yaml "
        "; do "
        'if [ -r "$CANDIDATE" ]; then '
        "CTRL_LINE=$(grep -m1 '^external-controller:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\"' | tr -d \"'\" | tr -d '\\r' | xargs); "
        'if [ -n "$CTRL_LINE" ]; then '
        "CTRL_PORT=$(printf '%s' \"$CTRL_LINE\" | awk -F: '{print $NF}' | tr -d '\\r' | xargs); "
        "fi; "
        "PROXY_PORT=$(grep -m1 '^mixed-port:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\\r' | xargs); "
        'if [ -z "$PROXY_PORT" ]; then '
        "PROXY_PORT=$(grep -m1 '^port:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\\r' | xargs); "
        "fi; "
        'if [ -n "$PROXY_PORT" ]; then PROXY_URL="http://127.0.0.1:$PROXY_PORT"; fi; '
        'if [ -n "$CTRL_PORT" ] && [ -n "$PROXY_URL" ]; then break; fi; '
        "fi; "
        "done; "
        'if [ -n "$PROXY_URL" ] && command -v curl >/dev/null 2>&1; then '
        'IP_LOCATION=$(curl -sS --proxy "$PROXY_URL" --connect-timeout 2 --max-time 4 https://speed.cloudflare.com/meta 2>/dev/null | tr -d \'\\r\' | awk -F\'"city"|"region"|"country"|"ip"\' \'NF>1 {print $0}\' | sed -n '
        '"s/.*\\"city\\":\\"\\\([^\\"]*\\\)\\".*\\"region\\":\\"\\\([^\\"]*\\\)\\".*\\"country\\":\\"\\\([^\\"]*\\\)\\".*\\"ip\\":\\"\\\([^\\"]*\\\)\\".*/\\1, \\2, \\3 (\\4)/p"); '
        'if [ -n "$IP_LOCATION" ]; then echo "ip_location=$IP_LOCATION"; else echo ip_location=unknown; fi; '
        "else "
        "echo ip_location=unknown; "
        "fi; "
        "echo controller_port=$CTRL_PORT; "
        "else "
        "echo api_reachable=false; "
        "echo ui_reachable=false; "
        "echo message=curl-missing; "
        "echo ip_location=unknown; "
        "echo controller_port=unknown; "
        "fi"
    )


def _clash_command(
    api_probe_url: str = "http://127.0.0.1:9090/version",
    ui_probe_url: str = "http://127.0.0.1:9090/ui",
    secret: str = "",
) -> str:
    auth_header = _shell_quote(f"Authorization: Bearer {secret}")
    api_url = _shell_quote(api_probe_url)
    ui_url = _shell_quote(ui_probe_url)
    return (
        "if pgrep -f clash >/dev/null; then echo running=true; else echo running=false; fi; "
        f"AUTH_HEADER={auth_header}; "
        f"API_URL={api_url}; "
        f"UI_URL={ui_url}; "
        "if command -v curl >/dev/null 2>&1; then "
        'API_CODE=$(curl -sS -o /dev/null -w \'%{http_code}\' --connect-timeout 1 --max-time 2 -H "$AUTH_HEADER" "$API_URL" || echo 000); '
        'UI_CODE=$(curl -sS -o /dev/null -w \'%{http_code}\' --connect-timeout 1 --max-time 2 -H "$AUTH_HEADER" "$UI_URL" || echo 000); '
        'if [ "$API_CODE" -ge 200 ] && [ "$API_CODE" -lt 400 ]; then echo api_reachable=true; else echo api_reachable=false; fi; '
        'if [ "$UI_CODE" -ge 200 ] && [ "$UI_CODE" -lt 400 ]; then echo ui_reachable=true; else echo ui_reachable=false; fi; '
        'if [ "$API_CODE" -ge 200 ] && [ "$API_CODE" -lt 400 ] && [ "$UI_CODE" -ge 200 ] && [ "$UI_CODE" -lt 400 ]; then echo message=ok; else echo message=probe-error; fi; '
        "CTRL_PORT=unknown; "
        "PROXY_URL=; "
        "for CANDIDATE in "
        "$HOME/clashctl/resources/runtime.yaml "
        "$HOME/clash-for-linux-install/resources/runtime.yaml "
        "; do "
        'if [ -r "$CANDIDATE" ]; then '
        "CTRL_LINE=$(grep -m1 '^external-controller:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\"' | tr -d \"'\" | tr -d '\\r' | xargs); "
        'if [ -n "$CTRL_LINE" ]; then '
        "CTRL_PORT=$(printf '%s' \"$CTRL_LINE\" | awk -F: '{print $NF}' | tr -d '\\r' | xargs); "
        "fi; "
        "PROXY_PORT=$(grep -m1 '^mixed-port:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\\r' | xargs); "
        'if [ -z "$PROXY_PORT" ]; then '
        "PROXY_PORT=$(grep -m1 '^port:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\\r' | xargs); "
        "fi; "
        'if [ -n "$PROXY_PORT" ]; then PROXY_URL="http://127.0.0.1:$PROXY_PORT"; fi; '
        'if [ -n "$CTRL_PORT" ] && [ -n "$PROXY_URL" ]; then break; fi; '
        "fi; "
        "done; "
        "IP_LOCATION=unknown; "
        'if [ -n "$PROXY_URL" ]; then '
        "IP_INFO=$(curl -sS --proxy \"$PROXY_URL\" --connect-timeout 1 --max-time 2 'http://ip-api.com/line/?fields=query,country,regionName,city' || true); "
        "else "
        "IP_INFO=$(curl -sS --connect-timeout 1 --max-time 2 'http://ip-api.com/line/?fields=query,country,regionName,city' || true); "
        "fi; "
        "IP_COUNTRY=$(printf '%s\\n' \"$IP_INFO\" | sed -n '1p' | tr -d '\\r'); "
        "IP_REGION=$(printf '%s\\n' \"$IP_INFO\" | sed -n '2p' | tr -d '\\r'); "
        "IP_CITY=$(printf '%s\\n' \"$IP_INFO\" | sed -n '3p' | tr -d '\\r'); "
        "IP_ADDR=$(printf '%s\\n' \"$IP_INFO\" | sed -n '4p' | tr -d '\\r'); "
        'if [ -n "$IP_ADDR$IP_COUNTRY$IP_REGION$IP_CITY" ] && [ "$IP_ADDR" != "fail" ]; then '
        'IP_LOCATION="$IP_CITY"; '
        'if [ -n "$IP_REGION" ]; then IP_LOCATION="${IP_LOCATION}, ${IP_REGION}"; fi; '
        'if [ -n "$IP_COUNTRY" ]; then IP_LOCATION="${IP_LOCATION}, ${IP_COUNTRY}"; fi; '
        'if [ -n "$IP_ADDR" ]; then IP_LOCATION="${IP_LOCATION} (${IP_ADDR})"; fi; '
        "IP_LOCATION=$(printf '%s' \"$IP_LOCATION\" | sed 's/^, //; s/^ *//; s/ *$//'); "
        "fi; "
        "echo ip_location=$IP_LOCATION; "
        "else "
        "echo api_reachable=false; "
        "echo ui_reachable=false; "
        "echo message=curl-missing; "
        "echo ip_location=unknown; "
        "fi; "
        "echo controller_port=$CTRL_PORT"
    )


def _serialize_metrics_stream_status(health_history: list, *, limit: int) -> dict:
    if not health_history:
        return {
            "state": "unknown",
            "label": "--",
            "latency_ms": None,
            "detail": "No stream history yet",
            "updated_at": None,
        }
    latest = health_history[-1]
    state = "healthy" if latest.ok else "failed"
    return {
        "state": state,
        "label": f"{latest.latency_ms}ms"
        if latest.latency_ms is not None and state == "healthy"
        else "--",
        "latency_ms": latest.latency_ms,
        "detail": f"Stream {'healthy' if latest.ok else 'broke'} {latest.age_seconds}s ago",
        "updated_at": latest.recorded_at,
    }


def _metrics_stream_status_for(
    server_id: str, stream_name: str, history_by_stream: dict
) -> dict:
    key = (server_id, stream_name)
    if key not in history_by_stream:
        return {
            "state": "unknown",
            "label": "--",
            "latency_ms": None,
            "detail": "No stream history yet",
            "updated_at": None,
        }
    return _serialize_metrics_stream_status(
        history_by_stream[key], limit=COMMAND_HEALTH_HISTORY_LIMIT
    )
