#!/bin/sh
# UI is an observer. A missing framebuffer/UI never affects updater safety gates.
BB=/bin/busybox
$BB rm -f /run/updater-ui.progress
printf '%s\n%s\n%s\n%s\n%s\n' "$1" "${2:-}" "${3:-0}" "${4:-0}" "${5:-}" >/run/updater-ui.state.tmp || exit 0
$BB mv /run/updater-ui.state.tmp /run/updater-ui.state || :
