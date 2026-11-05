#!/bin/zsh
# Tests first, then Railway. A failing test stops the deploy.
cd "${0:A:h}/.."
scripts/check.sh || { print "tests failed, not deploying"; exit 1; }
railway up --detach
