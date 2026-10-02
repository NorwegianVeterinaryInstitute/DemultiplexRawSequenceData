#!/usr/bin/env bash
#
# vault_status.sh - show whether the Bitwarden vault behind bw serve is unlocked, in plain words.
# Companion to vault_unlock.sh, for people who should not have to read JSON.
#
# Copyright (C) 2026  George Marselis <george.marselis@vetinst.no>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

response="$(/usr/bin/curl --no-progress-meter http://127.0.0.1:8087/status 2>/dev/null)"

if [ -z "${response}" ]; then
    echo "Bitwarden service is not running. Run: systemctl --user start bw-serve.service"
    exit 2
fi

status="$(printf '%s' "${response}" | /usr/bin/jq -r '.data.template.status')"

case "${status}" in
    unlocked)        echo "Vault is UNLOCKED. Everything is ready." ;;
    locked)          echo "Vault is LOCKED. Run: /usr/local/bin/vault_unlock.sh" ; exit 1 ;;
    unauthenticated) echo "Not logged in to Bitwarden. Run: /usr/local/bin/bw login, then continue from step 3 of the guide" ; exit 1 ;;
    *)               echo "Unexpected answer from Bitwarden: ${response}"; echo "Contact NVI support." ; exit 3 ;;
esac
