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
        "Upload OneZoom tour data to a OneZoom server, "
        "or preview it without saving. "
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
argparser.add_argument(
    '--dry-run',
    action='store_true',
    help='POST each tour to /tour/preview.html instead of uploading. No login required.',
)

args = argparser.parse_args()

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

if not args.http_base.startswith('http'):
    raise ValueError("Usage: upload.py http://localhost:8000/ *.json")

if args.dry_run:
    failed = False
    for file_path in args.files:
        url = "%s/tour/preview.html" % args.http_base
        print("===== Previewing %s at %s" % (file_path, url), flush=True)

        try:
            with open(file_path, 'rb') as f:
                t = json.load(f)
        except json.JSONDecodeError as e:
            print("Preview failed: %s is not valid JSON: %s" % (file_path, e), file=sys.stderr)
            failed = True
            continue

        request = urllib.request.Request(url, method='POST')
        request.add_header('Content-Type', 'application/json; charset=utf-8')
        payload = json.dumps(t).encode('utf-8')
        request.add_header('Content-Length', len(payload))

        try:
            with urllib.request.urlopen(request, payload, context=ctx) as response:
                if response.status != 200:
                    raise ValueError("Preview failed")
                print("Preview OK")
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            print("Preview failed: %s" % e, file=sys.stderr)
            if body:
                print(body, file=sys.stderr)
            failed = True

    if failed:
        sys.exit(1)
    sys.exit(0)

# Collect password
if args.password is not None:
    http_password = args.password
    print("Warning: using password from command line is insecure, ")
else:
    http_password = getpass.getpass(prompt='Password for %s: ' % args.user, stream=None)

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

    try:
        with urllib.request.urlopen(request, bytes, context=ctx) as response:
            if response.status != 200:
                raise ValueError("Upload failed")
            out = json.load(response)
            print("Tour ID %d" % out['id'])
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print("Upload failed: %s" % e, file=sys.stderr)
        if body:
            print(body, file=sys.stderr)
        sys.exit(1)

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
