#!/usr/bin/env bash
cd "$(dirname "$0")"
exec /root/qoder-suite/.venv/bin/python main.py "$@"
