# the three loops that keep the wait alive

`nohup` dies on reboot or when the terminal closes. launchd does not.

    cp scripts/launchd/net.ftak.pdf2epub.*.plist ~/Library/LaunchAgents/
    for j in deploywatch fulfil keys; do
      launchctl bootout gui/$(id -u)/net.ftak.pdf2epub.$j 2>/dev/null
      launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/net.ftak.pdf2epub.$j.plist
    done

- `deploywatch` - redeploys the moment Railway lifts the build freeze, then verifies `/shelf` + the checkout link. Exits after its 48h budget; KeepAlive only restarts it when it fails, so one good deploy is not redeployed again.
- `fulfil` - converts a PDF emailed to the concierge address and mails the EPUB back. The only money path that works before the deploy lands.
- `keys` - one HTTP call per cycle to check `/shelf` is live, then chases captured leads.

Logs: `/tmp/pdf2epub-{deploywatch,fulfil,keys}.{log,err}` and `/tmp/railway-deploy-watch.log`.
