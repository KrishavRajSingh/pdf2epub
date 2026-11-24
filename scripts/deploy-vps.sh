#!/bin/zsh
# Tests first, then ship the COMMITTED tree (git archive HEAD, never the working dir) to the VPS and rebuild.
# Usage: scripts/deploy-vps.sh   (host from PDF2EPUB_HOST, default root@77.237.235.155 (Contabo))
cd "${0:A:h}/.."
host=${PDF2EPUB_HOST:-root@77.237.235.155}
scripts/check.sh || { print "tests failed, not deploying"; exit 1; }
print "deploying $(git rev-parse --short HEAD) to $host"
ssh $host 'rm -rf /opt/pdf2epub/src.new && mkdir -p /opt/pdf2epub/src.new' || exit 1
git archive HEAD | ssh $host 'tar -x -C /opt/pdf2epub/src.new' || exit 1
ssh $host 'cd /opt/pdf2epub && rm -rf src && mv src.new src && cp src/deploy/docker-compose.yml . \
  && docker compose up -d --build && docker image prune -f >/dev/null' || exit 1
for i in {1..30}; do
  code=$(ssh $host 'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/stats')
  [[ $code == 200 ]] && { print "live: /stats 200"; exit 0 }
  sleep 5
done
print "app not answering on the box after 150 s"; exit 1
