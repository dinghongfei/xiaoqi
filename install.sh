#!/usr/bin/env bash
# 仓库入口：安装本机工具、写 .env、软链 Skills、构建演示站并启动。
# 不要交互提问。缺 App ID/Secret 时退出码 2，由 Agent 向用户要。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export BOT_ROOT="$ROOT"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

HUGO_VER="0.147.9"
APP_ID=""
APP_SECRET=""
NO_START=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id)
      APP_ID="${2:-}"
      shift 2
      ;;
    --app-id=*)
      APP_ID="${1#*=}"
      shift
      ;;
    --app-secret)
      APP_SECRET="${2:-}"
      shift 2
      ;;
    --app-secret=*)
      APP_SECRET="${1#*=}"
      shift
      ;;
    --no-start)
      NO_START=1
      shift
      ;;
    -h|--help)
      echo "用法: ./install.sh [--app-id ID] [--app-secret SECRET] [--no-start]"
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 1
      ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif have sudo && sudo -n true 2>/dev/null; then
    sudo -n "$@"
  else
    return 1
  fi
}

ensure_curl() {
  if have curl; then
    return 0
  fi
  echo "==> 安装 curl"
  if have brew; then
    brew install curl || true
  elif have apt-get; then
    privileged apt-get update -y && privileged apt-get install -y curl || true
  elif have dnf; then
    privileged dnf install -y curl || true
  elif have yum; then
    privileged yum install -y curl || true
  elif have pacman; then
    privileged pacman -Sy --noconfirm curl || true
  fi
  if have curl; then
    echo "✓ 已安装 curl"
    return 0
  fi
  echo "✗ 自动安装 curl 失败。Mac 请先安装 Homebrew（https://brew.sh），Linux 请在终端执行：sudo apt-get install -y curl ，然后对助手说「继续安装」。" >&2
  return 1
}

ensure_uv() {
  if have uv; then
    echo "✓ uv $(uv --version 2>/dev/null | head -n1)"
    return 0
  fi
  if ! ensure_curl; then
    return 1
  fi
  echo "安装 uv…"
  if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
    echo "✗ uv 安装失败。请检查网络后对助手说「继续安装」。" >&2
    return 1
  fi
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if have uv; then
    echo "✓ 已安装 uv"
    return 0
  fi
  echo "✗ uv 已下载但不在 PATH。请把 ~/.local/bin 加入 PATH 后对助手说「继续安装」。" >&2
  return 1
}

hugo_extended_ok() {
  have hugo && hugo version 2>/dev/null | grep -qi extended
}

install_hugo_binary() {
  local os arch hugo_arch asset url tmp
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) hugo_arch="amd64" ;;
    arm64|aarch64) hugo_arch="arm64" ;;
    *) hugo_arch="" ;;
  esac
  if [[ "$os" == "darwin" ]]; then
    asset="hugo_extended_${HUGO_VER}_darwin-universal.tar.gz"
  elif [[ "$os" == "linux" && -n "$hugo_arch" ]]; then
    asset="hugo_extended_${HUGO_VER}_linux-${hugo_arch}.tar.gz"
  else
    return 1
  fi
  url="https://github.com/gohugoio/hugo/releases/download/v${HUGO_VER}/${asset}"
  mkdir -p "$HOME/.local/bin"
  tmp="$(mktemp -d)"
  echo "下载 Hugo Extended ${HUGO_VER}…"
  if curl -fL "$url" -o "$tmp/hugo.tgz" && tar -C "$tmp" -xzf "$tmp/hugo.tgz" hugo; then
    install -m 0755 "$tmp/hugo" "$HOME/.local/bin/hugo"
    rm -rf "$tmp"
    export PATH="$HOME/.local/bin:$PATH"
    return 0
  fi
  rm -rf "$tmp"
  return 1
}

ensure_hugo() {
  if hugo_extended_ok; then
    echo "✓ Hugo $(hugo version 2>/dev/null | head -n1)"
    return 0
  fi
  echo "==> 安装 Hugo Extended ${HUGO_VER}"
  if ! ensure_curl; then
    return 1
  fi
  install_hugo_binary || true
  if ! hugo_extended_ok && have brew; then
    brew install hugo || true
  fi
  if hugo_extended_ok; then
    echo "✓ 已安装 Hugo $(hugo version 2>/dev/null | head -n1)"
    return 0
  fi
  echo "✗ 缺少 Hugo Extended。请检查网络后对助手说「继续安装」。" >&2
  return 1
}

ensure_node() {
  if have npx || have npm; then
    echo "✓ Node.js"
    return 0
  fi
  echo "==> 安装 Node.js（飞书命令行 lark-cli 需要）"
  if have brew; then
    brew install node || true
  elif have apt-get; then
    privileged apt-get update -y && privileged apt-get install -y nodejs npm || true
  fi
  if have npx || have npm; then
    echo "✓ 已安装 Node.js"
    return 0
  fi
  echo "✗ 缺少 Node.js，没法安装飞书命令行 lark-cli。请到 https://nodejs.org 安装 LTS，装好后说「继续安装」。" >&2
  return 1
}

ensure_lark_cli() {
  if have lark-cli; then
    echo "✓ lark-cli（$(command -v lark-cli)）"
    return 0
  fi
  echo "==> 安装 lark-cli"
  if have npx; then
    npx --yes @larksuite/cli@latest install || true
    export PATH="$HOME/.local/bin:$PATH"
  elif have npm; then
    npm install -g @larksuite/cli || true
    export PATH="$HOME/.local/bin:$PATH"
  fi
  if have lark-cli; then
    echo "✓ 已安装 lark-cli"
    return 0
  fi
  echo "✗ 缺少 lark-cli。请确认已安装 Node.js 后说「继续安装」。" >&2
  return 1
}

ensure_ffmpeg() {
  if have ffmpeg; then
    echo "✓ ffmpeg"
    return 0
  fi
  echo "==> 尝试安装 ffmpeg"
  if have brew; then
    brew install ffmpeg || true
  elif have apt-get; then
    privileged apt-get install -y ffmpeg || true
  fi
  if have ffmpeg; then
    echo "✓ 已安装 ffmpeg"
    return 0
  fi
  echo "⚠ 未安装 ffmpeg。压缩媒体时会跳过；官网预览仍可用。"
}

echo "==> 准备本机工具"

if ! ensure_uv; then
  exit 1
fi
if ! ensure_hugo; then
  exit 1
fi
if ! ensure_node; then
  exit 1
fi
if ! ensure_lark_cli; then
  exit 1
fi
ensure_ffmpeg

echo "==> 同步项目依赖"
if ! uv sync --all-groups; then
  echo "✗ Python 依赖安装失败。请检查网络后对助手说「继续安装」。" >&2
  exit 1
fi

echo "==> 写入项目配置"
set +e
uv run python -m bot.initialize --root "$ROOT" --app-id "$APP_ID" --app-secret "$APP_SECRET"
cfg="$?"
set -e
if [[ "$cfg" -ne 0 ]]; then
  exit "$cfg"
fi

echo "==> 首次构建演示站"
if ! uv run python "$ROOT/skills/deploy-local/scripts/run.py" --root "$ROOT"; then
  echo "⚠ 演示站首次构建失败。依赖已装好的话，可以说「继续安装」。"
fi

if [[ "$NO_START" -eq 0 ]]; then
  echo "==> 启动飞书机器人与预览"
  if ! bash "$ROOT/scripts/start.sh"; then
    echo "⚠ 未能自动启动。可以说「启动」让我再试 ./scripts/start.sh"
  fi
fi

echo
echo "安装完成。"
echo "  预览: http://127.0.0.1:1314/"
echo "  去飞书把机器人拉进群，发一篇云文档链接即可。"
