#!/bin/zsh
cd ~/streamclip && set -a && source .env && set +a
echo "=== $(date) jynxzi shorts ===" >> run.log
~/clipfarm/.venv/bin/python -m clipfarm run --clips 3 --config config.jynxzi.yaml --vod https://www.twitch.tv/videos/2816011147 >> run.log 2>&1
echo "=== $(date) caseoh comp ===" >> run.log
~/clipfarm/.venv/bin/python -m clipfarm.compile --channel caseoh_ --streams 4 --target-min 14 --title "CaseOh's Funniest Moments This Week" >> run.log 2>&1
echo "=== $(date) ALL DONE ===" >> run.log
