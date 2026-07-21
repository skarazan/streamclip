#!/bin/zsh
cd ~/streamclip && set -a && source .env && set +a
echo "=== $(date) CASEOH 2824292950 ===" >> run.log
~/clipfarm/.venv/bin/python -u -m clipfarm run --clips 3 --vod https://www.twitch.tv/videos/2824292950 >> run.log 2>&1
echo "=== $(date) JYNXZI 2824608282 ===" >> run.log
~/clipfarm/.venv/bin/python -u -m clipfarm run --clips 3 --config config.jynxzi.yaml --vod https://www.twitch.tv/videos/2824608282 >> run.log 2>&1
echo "=== BOTH DONE $(date) ===" >> run.log
