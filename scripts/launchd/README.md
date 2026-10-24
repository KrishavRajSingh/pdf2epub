# the three loops that keep the wait alive

`nohup` dies on reboot or when the terminal closes. launchd does not.

    cp scripts/launchd/net.ftak.pdf2epub.*.plist ~/Library/LaunchAgents/
    for j in deploywatch keys; do
      launchctl bootout gui/$(id -u)/net.ftak.pdf2epub.$j 2>/dev/null
      launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/net.ftak.pdf2epub.$j.plist
    done

`fulfil` is not in that loop on purpose. Loading it restarts free fulfilment.

- `deploywatch` - redeploys the moment Railway lifts the build freeze, then verifies `/shelf` + the checkout link. Exits after its 48h budget; KeepAlive only restarts it when it fails, so one good deploy is not redeployed again.
- `fulfil` - **paused 2026-10-24.** It converted any PDF emailed to the concierge address and mailed the EPUB back for free, which undercut Shelf. Run `python3 scripts/fulfil.py --once` by hand after a paid order. Do not restart the watcher until it checks for a paid key.
- `keys` - one HTTP call per cycle to check `/shelf` is live, then chases captured leads.

Logs: `/tmp/pdf2epub-{deploywatch,fulfil,keys}.{log,err}` and `/tmp/railway-deploy-watch.log`.
