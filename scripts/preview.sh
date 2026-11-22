#!/usr/bin/env bash
# 本地预览：一条命令启动背单词站点的 Astro 开发服务器。
#
# 用法：
#   ./scripts/preview.sh                 # 默认 http://localhost:4321/
#   ./scripts/preview.sh -p 4400         # 换端口
#   ./scripts/preview.sh --host 0.0.0.0  # 允许局域网访问
#
# 环境变量：
#   NODE_BIN_DIR   Node 所在目录，默认 $HOME/.local/node/bin
#   SITE_DIR       站点工程目录，默认仓库下的 2026-11-19/vocab-site-plan/site

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
NODE_BIN_DIR="${NODE_BIN_DIR:-$HOME/.local/node/bin}"
SITE_DIR="${SITE_DIR:-$REPO_ROOT/2026-11-19/vocab-site-plan/site}"

PORT=4321
HOST=localhost

usage() {
  cat <<'EOF'
本地预览脚本

用法：scripts/preview.sh [选项]

选项：
  -p, --port <端口>   监听端口，默认 4321
      --host <地址>   监听地址，默认 localhost；用 0.0.0.0 允许局域网访问
  -h, --help          显示帮助

示例：
  scripts/preview.sh
  scripts/preview.sh --port 4400
  scripts/preview.sh --host 0.0.0.0 --port 4400
EOF
}

die() {
  echo "错误：$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)
      [[ $# -ge 2 ]] || die "$1 需要一个端口号"
      PORT="$2"
      shift 2
      ;;
    --port=*)
      PORT="${1#*=}"
      shift
      ;;
    --host)
      [[ $# -ge 2 ]] || die "--host 需要一个监听地址"
      HOST="$2"
      shift 2
      ;;
    --host=*)
      HOST="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "未知参数：$1"
      ;;
  esac
done

[[ "$PORT" =~ ^[0-9]+$ ]] || die "端口必须是数字，收到：$PORT"
(( PORT >= 1 && PORT <= 65535 )) || die "端口需在 1–65535 之间，收到：$PORT"

# 系统 PATH 里没有 node，优先使用本地安装目录。
if [[ -d "$NODE_BIN_DIR" ]]; then
  export PATH="$NODE_BIN_DIR:$PATH"
fi

command -v node >/dev/null 2>&1 || die "找不到 node。请确认 Node 已安装，或用 NODE_BIN_DIR 指定其 bin 目录（当前尝试：$NODE_BIN_DIR）"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || true)"
[[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] || die "无法读取 node 版本，请检查安装：$(command -v node)"
(( NODE_MAJOR >= 18 )) || die "Astro 需要 Node 18 及以上，当前版本：$(node -v)"

[[ -d "$SITE_DIR" ]] || die "站点目录不存在：$SITE_DIR"
[[ -d "$SITE_DIR/node_modules" ]] || die "站点依赖未安装：$SITE_DIR/node_modules 不存在。请先在站点目录执行 npm install"
[[ -x "$SITE_DIR/node_modules/.bin/astro" ]] || die "找不到 Astro 可执行文件：$SITE_DIR/node_modules/.bin/astro"

# 端口已被占用时直接报错，避免 Vite 自动换端口后打印的地址对不上。
# 用 node 在将要监听的地址上试绑一次，兼容 localhost 解析到 IPv6 的情况。
PORT_STATUS=0
node - "$HOST" "$PORT" <<'NODE' || PORT_STATUS=$?
const net = require('node:net');
const host = process.argv[2];
const port = Number(process.argv[3]);
const server = net.createServer();
server.once('error', (error) => {
  process.exit(error.code === 'EADDRINUSE' ? 10 : 11);
});
server.listen(port, host, () => server.close(() => process.exit(0)));
NODE
if (( PORT_STATUS == 10 )); then
  die "端口 $PORT 已被占用。请换一个端口，例如：scripts/preview.sh --port $((PORT + 1))"
elif (( PORT_STATUS != 0 )); then
  die "无法在 $HOST 上监听端口 $PORT，请确认监听地址是否正确"
fi

export ASTRO_TELEMETRY_DISABLED=1
export PATH="$SITE_DIR/node_modules/.bin:$PATH"

case "$HOST" in
  0.0.0.0|::)
    LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    URL="http://localhost:$PORT/"
    echo "本地预览地址：$URL"
    [[ -n "$LAN_IP" ]] && echo "局域网地址：http://$LAN_IP:$PORT/"
    ;;
  *)
    URL="http://$HOST:$PORT/"
    echo "本地预览地址：$URL"
    ;;
esac
echo "站点目录：$SITE_DIR"
echo "按 Ctrl+C 停止服务。"
echo

cd "$SITE_DIR"
exec "$SITE_DIR/node_modules/.bin/astro" dev --port "$PORT" --host "$HOST"
