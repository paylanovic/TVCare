#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 -m tvbakim "$@"
fi
printf 'Kaynak sürüm için Python 3.10+ gerekli. Hazır TVCare paketini kullanabilir veya python.org üzerinden kurabilirsiniz.\n'
read -r answer
