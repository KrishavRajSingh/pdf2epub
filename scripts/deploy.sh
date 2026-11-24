#!/bin/zsh
# Since 2026-11-24 pdf2epub runs on a Contabo VPS (77.237.235.155), not Railway.
# Tests first, then ship the committed tree. A failing test stops the deploy.
exec "${0:A:h}/deploy-vps.sh" "$@"
