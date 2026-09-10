#!/bin/sh

# DO NOT run this script directly.
# It is sent to the server and run by the setup_upload script.

set -eu

: "${SSH_HOSTNAME:?}"
: "${UPLOAD_USER:?}"
: "${UPLOAD_PASSWORD:?}"

WEB2PY_ROOT=/home/web2py/${SSH_HOSTNAME}
if [ ! -x "${WEB2PY_ROOT}/bin/python" ] || [ ! -f "${WEB2PY_ROOT}/web2py.py" ]; then
  echo "web2py install not found at ${WEB2PY_ROOT}" >&2
  exit 1
fi

sudo chown web2py /tmp/create_tour_uploader.py
sudo chmod 600 /tmp/create_tour_uploader.py
cd "$WEB2PY_ROOT"
sudo -u web2py \
  env UPLOAD_USER="$UPLOAD_USER" UPLOAD_PASSWORD="$UPLOAD_PASSWORD" \
  ./bin/python web2py.py -S OZtree -M -R /tmp/create_tour_uploader.py
sudo rm -f /tmp/create_tour_uploader.py
rm -f /tmp/setup_tour_uploader.sh
