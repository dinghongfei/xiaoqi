# 解析本机 uv 的绝对路径。由 install.sh / start.sh source，不要单独执行。
# 沙箱 PATH 常常没有 ~/.local/bin，command -v uv 会失败，但二进制已装好。

_try_uv() {
  local cand="$1"
  [[ -n "$cand" && -f "$cand" && -x "$cand" ]] || return 1
  if [[ "$cand" != /* ]]; then
    cand="$(cd "$(dirname "$cand")" && pwd)/$(basename "$cand")"
  fi
  UV="$cand"
  export UV
  export PATH="$(dirname "$UV"):${PATH:-}"
  return 0
}

resolve_uv() {
  if [[ -n "${UV_BIN:-}" ]] && _try_uv "$UV_BIN"; then
    return 0
  fi
  local from_path
  from_path="$(command -v uv 2>/dev/null || true)"
  if _try_uv "$from_path"; then
    return 0
  fi
  _try_uv "${HOME}/.local/bin/uv" && return 0
  _try_uv "${HOME}/.cargo/bin/uv" && return 0
  return 1
}
