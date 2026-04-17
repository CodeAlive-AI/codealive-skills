#!/usr/bin/env bash
# Remove the plugin-bridge launchd agent. Does not touch existing symlinks.

set -euo pipefail

LABEL="com.codealive.plugin-bridge"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    launchctl bootout "$DOMAIN/$LABEL" || true
fi
rm -f "$PLIST"

echo "Removed launchd agent: $LABEL"
