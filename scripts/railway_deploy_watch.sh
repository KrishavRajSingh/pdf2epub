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
MARKER='Printed lines in the PDF'

for attempt in $(seq 1 720); do            # 720 x 60s = 12 hours
  out=$(timeout 150 railway redeploy --from-source --yes 2>&1 | tr '\n' ' ')
  echo "[$(date '+%H:%M:%S')] attempt $attempt: $out" >>"$LOG"
  case "$out" in
    *paused*) sleep 60; continue ;;
  esac
  echo "[$(date '+%H:%M:%S')] deploy accepted, waiting for the new build to serve" >>"$LOG"
  for _ in $(seq 1 80); do
    if curl -s --max-time 20 https://epub.ftak.net/ | grep -q "$MARKER"; then
      echo "[$(date '+%H:%M:%S')] DEPLOYED AND VERIFIED (landing page shows the new build)" >>"$LOG"
      exit 0
    fi
    sleep 15
  done
  echo "[$(date '+%H:%M:%S')] build did not go live in time, retrying" >>"$LOG"
done
echo "[$(date '+%H:%M:%S')] gave up after 12h" >>"$LOG"
