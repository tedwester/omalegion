#!/bin/bash
set -euo pipefail

USER_NAME="${1:?usage: install-privilege.sh <username>}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPER_SRC="$SRC_DIR/omalegion-write"
HELPER_DST="/usr/local/bin/omalegion-write"
SUDOERS_DST="/etc/sudoers.d/omalegion"

if [ "$(id -u)" -ne 0 ]; then
  echo "install-privilege.sh must run as root (use pkexec)" >&2
  exit 1
fi

if [ ! -f "$HELPER_SRC" ]; then
  echo "helper not found: $HELPER_SRC" >&2
  exit 1
fi

if ! id "$USER_NAME" >/dev/null 2>&1; then
  echo "unknown user: $USER_NAME" >&2
  exit 1
fi

install -m 0755 "$HELPER_SRC" "$HELPER_DST"

TMP_FILE="$(mktemp)"
{
  printf '%s ALL=(root) NOPASSWD: %s --check\n' "$USER_NAME" "$HELPER_DST"
  printf '%s ALL=(root) NOPASSWD: %s write *\n' "$USER_NAME" "$HELPER_DST"
  printf '%s ALL=(root) NOPASSWD: %s write-pairs *\n' "$USER_NAME" "$HELPER_DST"
  printf '%s ALL=(root) NOPASSWD: %s efivar *\n' "$USER_NAME" "$HELPER_DST"
  printf '%s ALL=(root) NOPASSWD: %s hid-set *\n' "$USER_NAME" "$HELPER_DST"
  printf '%s ALL=(root) NOPASSWD: %s hid-get *\n' "$USER_NAME" "$HELPER_DST"
} > "$TMP_FILE"
chmod 0440 "$TMP_FILE"

if ! visudo -c -f "$TMP_FILE" >/dev/null 2>&1; then
  echo "sudoers syntax check failed, not installing" >&2
  rm -f "$TMP_FILE"
  exit 1
fi

mv "$TMP_FILE" "$SUDOERS_DST"
chmod 0440 "$SUDOERS_DST"

if ! visudo -c >/dev/null 2>&1; then
  echo "warning: full sudoers check reported an issue" >&2
fi

if sudo -U "$USER_NAME" -l 2>/dev/null | grep -q "$HELPER_DST"; then
  echo "omalegion passwordless hardware control installed for $USER_NAME"
else
  echo "warning: rule installed but not visible for $USER_NAME yet" >&2
  exit 1
fi

UDEV_DST="/etc/udev/rules.d/99-omalegion-rgb.rules"
# Session-scoped access: the keyboard is handed to whoever is physically
# logged in (systemd-logind ACLs), not opened to every local account.
# Other users keep only the per-user sudo-gated helper path, and only if a
# rule was installed for them. Never use a world-writable mode here: that
# would grant all local accounts raw HID access and bypass the helper's
# authorization.
{
  echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="048d", ATTRS{idProduct}=="c1*", TAG+="uaccess"'
  echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="048d", ATTRS{idProduct}=="c6*", TAG+="uaccess"'
  echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="048d", ATTRS{idProduct}=="c9*", TAG+="uaccess"'
} > "$UDEV_DST"
chmod 0644 "$UDEV_DST"
udevadm control --reload-rules >/dev/null 2>&1 || true
udevadm trigger --subsystem-match=hidraw --action=change >/dev/null 2>&1 || true
echo "omalegion keyboard RGB access installed (unplug/replug or reboot if the keyboard is not yet accessible)"
