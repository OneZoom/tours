#!/usr/bin/env python3
import argparse
import base64
import getpass
import json
import os.path
import urllib.request
import ssl
import sys

argparser = argparse.ArgumentParser(
    description=(
        "Upload OneZoom tour data to a OneZoom server. "
        "Usage: upload.py http://localhost:8000/ *.json"
    )
)
argparser.add_argument(
    'http_base',
    help='The base URL of the OneZoom server, e.g. http://localhost:8000/',
)
argparser.add_argument(
    'files',
    help='The JSON files to upload, e.g. *.json',
    nargs='+',
)
argparser.add_argument(
    '--user', '-u',
    help='The web2py user to use for authentication (default: admin)',
    default='admin',
)
argparser.add_argument(
    '--password', '-p',
    help='The web2py password to use for authentication (default: None, meaning you will be prompted)',
    default=None,
)

args = argparser.parse_args()

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Collect password
if args.password is not None:
    http_password = args.password
    print("Warning: using password from command line is insecure, ")
else:
    http_password = getpass.getpass(prompt='Password for %s: ' % args.user, stream=None)

if not args.http_base.startswith('http'):
    raise ValueError("Usage: upload.py http://localhost:8000/ *.json")
    sys.exit(1)

for file_path in args.files:
    url = "%s/tour/data.json/%s" % (
        args.http_base,
        os.path.splitext(os.path.basename(file_path))[0],
    )
    print("===== Uploading %s to %s" % (
        file_path,
        url
    ))

    with open(file_path, 'rb') as f:
        t = json.load(f)

    request = urllib.request.Request(url, method='PUT')
    request.add_header("Authorization", ("Basic %s" % base64.b64encode(':'.join((
        args.user,
        http_password
    )).encode('utf8')).decode('utf8')))
    request.add_header('Content-Type', 'application/json; charset=utf-8')
    bytes = json.dumps(t).encode('utf-8')
    request.add_header('Content-Length', len(bytes))

    with urllib.request.urlopen(request, bytes, context=ctx) as response:
        if response.status != 200:
            raise ValueError("Upload failed")
        out = json.load(response)
        print("Tour ID %d" % out['id'])

    request = urllib.request.Request("%s/tour/data.html/%s" % (
        args.http_base,
        os.path.splitext(os.path.basename(file_path))[0],
    ), method='GET')
    try:
        with urllib.request.urlopen(request, bytes, context=ctx) as response:
            if response.status != 200:
                print("Tour rendered as HTML")
    except urllib.error.HTTPError as e:
        print("Tour cannot be rendered by data.html, look at OneZoom error logs: %s" % e, file=sys.stderr)
        sys.exit(1)
