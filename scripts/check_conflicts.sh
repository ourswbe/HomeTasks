#!/usr/bin/env bash
set -euo pipefail

echo "[1/3] Проверка merge markers в файлах..."
if rg "^(<<<<<<<|=======|>>>>>>>)" . >/tmp/conflict_markers.txt 2>/dev/null; then
  echo "Найдены conflict markers:"
  cat /tmp/conflict_markers.txt
  exit 1
else
  echo "OK: conflict markers не найдены."
fi

echo "[2/3] Проверка незакоммиченных изменений..."
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Есть незакоммиченные изменения. Сначала commit/stash."
  git status --short
  exit 1
else
  echo "OK: рабочее дерево чистое."
fi

echo "[3/3] Подсказка по синхронизации ветки с main:"
echo "  git fetch origin"
echo "  git rebase origin/main"
echo "  # решить конфликты, затем:"
echo "  git add <files>"
echo "  git rebase --continue"
echo "  git push --force-with-lease"

echo "Готово."
