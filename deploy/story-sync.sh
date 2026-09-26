#!/bin/sh
# 每周同步剧情库：更新 SCTranslationData，再在后端容器里运行 `eidolon story sync`。
# 由主机上的 cron 运行，安装方法见 docs/deploy.md 的「每周自动同步」。
#
# 输出追加到仓库根目录的 logs/story-sync.log（可用 EIDOLON_SYNC_LOG 改到别处）。
# 额外的参数原样传给 `eidolon story sync`，例如 `deploy/story-sync.sh --idol 1`。
# 默认用 docker-compose.prod.yml；设置了 COMPOSE_FILE 时用它指定的配置。
#
# 退出码：
#   0  完全成功
#   1  同步命令：配置错误或向量化中断（重新运行即可继续）
#   2  同步命令：镜像出错，这次没拉到（全部）原文剧情；汉化版已照常导入
#   3  git 没能更新 SCTranslationData：有已下载的数据时照常同步（同步出错时仍报 1 或 2），
#      一份都没有时不运行同步
#   4  后端容器没有运行，或无法运行同步命令
#   5  上一次同步还没结束，这次没有运行

set -u

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root" || exit 4
PATH=/usr/local/bin:/usr/bin:/bin:$PATH # cron 的 PATH 很短
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
log=${EIDOLON_SYNC_LOG:-$root/logs/story-sync.log}
mkdir -p "$(dirname "$log")"
exec >>"$log" 2>&1

say() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

finish() {
  case $1 in
    0) meaning="完全成功" ;;
    1) meaning="同步命令出错：配置错误或向量化中断，重新运行即可继续" ;;
    2) meaning="镜像出错：汉化版已导入，原文剧情下次同步接着拉取" ;;
    3) meaning="SCTranslationData 没有更新，见上方 git 的输出" ;;
    4) meaning="后端容器没有运行，或无法运行同步命令" ;;
    5) meaning="上一次同步还没结束，这次没有运行" ;;
    *) meaning="未知" ;;
  esac
  say "==== 结束：退出码 $1（$meaning）"
  echo
  exit "$1"
}

say "==== 开始同步剧情库（$root）"

# 首次全量补齐要一到两个小时，手动运行时可能和 cron 撞上
exec 9>"$log.lock"
if ! flock -n 9; then
  finish 5
fi

corpus=corpus/SCTranslationData
git_failed=0
if [ -d "$corpus/.git" ]; then
  say "git pull $corpus"
  before=$(git -C "$corpus" rev-parse HEAD)
  if git -C "$corpus" pull --ff-only --quiet; then
    head=$(git -C "$corpus" log -1 --format='%h（%cs）')
    changed=$(git -C "$corpus" diff --shortstat "$before" HEAD)
    if [ -n "$changed" ]; then
      say "SCTranslationData 更新到 $head：$changed"
    else
      say "SCTranslationData 没有新提交，仍是 $head"
    fi
  else
    git_failed=1
  fi
else
  say "克隆 SCTranslationData 到 $corpus"
  mkdir -p corpus
  git clone --depth 1 https://github.com/ShinyGroup/SCTranslationData.git "$corpus" || git_failed=1
fi
if [ "$git_failed" = 1 ]; then
  if [ -d "$corpus/data/story" ]; then
    say "git 失败，用已有的 SCTranslationData 继续同步"
  else
    say "git 失败，而且没有可用的 SCTranslationData，这次不同步"
    finish 3
  fi
fi

if [ -z "$(docker compose ps --status running --quiet backend 2>/dev/null)" ]; then
  say "后端容器没有运行（docker compose ps 里找不到运行中的 backend）"
  finish 4
fi

say "docker compose exec backend eidolon story sync $*"
# -T：cron 里没有终端；PYTHONUNBUFFERED：进度日志和结果按实际顺序写进日志
docker compose exec -T -e PYTHONUNBUFFERED=1 backend eidolon story sync "$@"
code=$?
case $code in
  0 | 1 | 2) ;;
  *)
    say "docker compose exec 以 $code 结束"
    finish 4
    ;;
esac
if [ "$code" = 0 ] && [ "$git_failed" = 1 ]; then
  finish 3
fi
finish "$code"
