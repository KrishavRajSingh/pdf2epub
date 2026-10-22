#!/bin/bash
# Wait for Railway to resume builds, deploy the latest commit, verify it is live.
#
# why: Railway paused all builds platform-wide on 2026-10-20 and their status page says deploys
# triggered during the pause have to be re-triggered. So we retry until the API accepts, then
# confirm the new build is actually serving (the landing page only prints the proof panel in the
# new build) before we call it done.
#
# usage: nohup scripts/railway_deploy_watch.sh >> /tmp/railway-deploy-watch.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
LOG=/tmp/railway-deploy-watch.log
# ponytail: /shelf and the checkout link exist only in the pending build, so they cannot pass
# against the old one. bump these if a later change needs proof instead.

for attempt in $(seq 1 576); do            # 576 x 300s = 48 hours
  # why 48h: railway re-enables builds per tier (enterprise, pro, hobby, then free/trial last),
  # and this workspace is on the free trial, so it is in the final wave with no published ETA.
  # why 5 min not 60s: their api is in a major outage, 2880 calls a day is rude. the build
  # itself takes minutes, so a 5 min poll costs nothing in deploy time.
  out=$(timeout -k 10 150 railway redeploy --from-source --yes 2>&1 | tr '\n' ' ')
  echo "[$(date '+%H:%M:%S')] attempt $attempt: $out" >>"$LOG"
  case "$out" in
    *[Pp]aused*) sleep 300; continue ;;
    *"Failed to fetch"*|*"error sending request"*) sleep 300; continue ;;   # railway api unreachable, not a deploy
    *Unauthorized*) sleep 300; continue ;;   # railway invalidated the oauth token, `railway login` fixes it
  esac
  echo "[$(date '+%H:%M:%S')] deploy accepted, waiting for the new build to serve" >>"$LOG"
  for _ in $(seq 1 80); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://epub.ftak.net/shelf)" = 200 ] \
       && curl -s --max-time 20 https://epub.ftak.net/ | grep -q 'buy.polar.sh'; then
      echo "[$(date '+%H:%M:%S')] DEPLOYED AND VERIFIED (/shelf + checkout link are live)" >>"$LOG"
      exit 0
    fi
    sleep 15
  done
  echo "[$(date '+%H:%M:%S')] build did not go live in time, retrying" >>"$LOG"
done
echo "[$(date '+%H:%M:%S')] gave up after 12h" >>"$LOG"
