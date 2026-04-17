#!/usr/bin/env bash
# Install the plugin-bridge launchd agent on macOS.
# Run once per user account. Idempotent — re-running reloads the agent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATER="$SCRIPT_DIR/update-symlink.sh"
TEMPLATE="$SCRIPT_DIR/com.codealive.plugin-bridge.plist.template"

LABEL="com.codealive.plugin-bridge"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

: "${CODEALIVE_PLUGIN_CACHE:=$HOME/.claude/plugins/cache/codealive-marketplace/codealive}"

chmod +x "$UPDATER"
mkdir -p "$HOME/Library/LaunchAgents"

sed -e "s|__UPDATER__|$UPDATER|g" \
    -e "s|__WATCH_PATH__|$CODEALIVE_PLUGIN_CACHE|g" \
    "$TEMPLATE" > "$PLIST"

DOMAIN="gui/$(id -u)"
if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    launchctl bootout "$DOMAIN/$LABEL" || true
fi
launchctl bootstrap "$DOMAIN" "$PLIST"

"$UPDATER" || true

echo "Installed launchd agent: $LABEL"
echo "Plist:  $PLIST"
echo "Logs:   /tmp/codealive-plugin-bridge.log (stdout), /tmp/codealive-plugin-bridge.err (stderr)"
