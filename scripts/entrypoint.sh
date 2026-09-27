#!/bin/sh
# entrypoint.sh
#
# Container start for the FEIDE proxy: fill the templates from .env,
# load the organisation entry, print the settings and run slapd.
#
# Copyright (C) 2026 George Marselis <george.marselis@vetinst.no>
#
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
#
# Reads /etc/feide/.env, written on the host by orchestrator.sh, and
# refuses to start if any value it needs is missing. Derives the LDAP
# base DN from DOMAIN (dfo.no -> dc=dfo,dc=no). Fills slapd.conf and
# the organisation LDIF from their templates, checks the configuration
# with slaptest, loads the organisation entry into the empty local
# database on first start, prints every setting with the organisation
# number first and hands over to slapd on LDAPS only.
#
# Nothing here is interactive and nothing here writes a secret: the
# keytab, the certificate and the key are mounted in by the host.

set -eu

ENTRYPOINT_ENV_FILE="${ENTRYPOINT_ENV_FILE:-/etc/feide/.env}"
ENTRYPOINT_KEYTAB="${KRB5_CLIENT_KTNAME:-/etc/krb5.keytab}"
ENTRYPOINT_CERT=/etc/openldap/certs/fullchain.pem
ENTRYPOINT_KEY=/etc/openldap/certs/privkey.pem
ENTRYPOINT_CONF=/etc/openldap/slapd.conf
ENTRYPOINT_ORG_LDIF=/etc/openldap/org.ldif
ENTRYPOINT_DB_DIR=/var/lib/ldap

entrypoint_fail() {
	echo "entrypoint: $1" >&2
	exit 1
}

# Takes a variable name. Fails if it is unset or empty.
entrypoint_require() {
	eval "[ -n \"\${$1:-}\" ]" || entrypoint_fail "$1 is not set in $ENTRYPOINT_ENV_FILE; run orchestrator.sh on the host"
}

entrypoint_load_env() {
	[ -f "$ENTRYPOINT_ENV_FILE" ] || entrypoint_fail "no env file at $ENTRYPOINT_ENV_FILE"
	. "$ENTRYPOINT_ENV_FILE"
	for name in DOMAIN NAVN ORGANISASJONSNUMMER NOREDUORGACRONYM NOREDUORGSCHEMAVERSION AD_SERVER SIKT_BIND_DN ORG_MAIL; do
		entrypoint_require "$name"
	done
}

# Takes a domain, prints its base DN: dfo.no -> dc=dfo,dc=no
entrypoint_base_dn() {
	echo "$1" | /usr/bin/sed 's/\./,dc=/g; s/^/dc=/'
}

entrypoint_derive() {
	BASE_DN=$(entrypoint_base_dn "$DOMAIN")
	AD_BASE_DN=$(echo "$BASE_DN" | /usr/bin/tr 'a-z' 'A-Z')
	DC=$(echo "$DOMAIN" | /usr/bin/cut -d. -f1)
	ORG_MAIL_LINES=$(entrypoint_mail_lines)
	export BASE_DN AD_BASE_DN DC ORG_MAIL_LINES DOMAIN NAVN ORGANISASJONSNUMMER NOREDUORGACRONYM NOREDUORGSCHEMAVERSION AD_SERVER SIKT_BIND_DN ORG_MAIL
}

# ORG_MAIL is a space separated list of addresses. mail is a
# multi-valued attribute, so the organisation entry gets one line
# per address.
entrypoint_mail_lines() {
	for addr in $ORG_MAIL; do
		echo "mail: $addr"
	done
}

entrypoint_check_mounts() {
	[ -r "$ENTRYPOINT_KEYTAB" ] || entrypoint_fail "keytab $ENTRYPOINT_KEYTAB is missing or not readable by $(/usr/bin/id -un)"
	[ -r "$ENTRYPOINT_CERT" ] || entrypoint_fail "certificate $ENTRYPOINT_CERT is missing"
	[ -r "$ENTRYPOINT_KEY" ] || entrypoint_fail "key $ENTRYPOINT_KEY is missing"
}

entrypoint_render() {
	/usr/bin/envsubst < /etc/openldap/slapd.conf.template > "$ENTRYPOINT_CONF"
	/usr/bin/envsubst < /etc/openldap/org.ldif.template > "$ENTRYPOINT_ORG_LDIF"
	/usr/sbin/slaptest -Q -f "$ENTRYPOINT_CONF" || entrypoint_fail "slapd.conf did not pass slaptest"
}

# Loads the organisation entry once. mdb creates data.mdb on first
# use, so its absence means the database has never been populated.
entrypoint_load_org() {
	[ -f "$ENTRYPOINT_DB_DIR/data.mdb" ] && return 0
	/usr/sbin/slapadd -q -f "$ENTRYPOINT_CONF" -b "$BASE_DN" -l "$ENTRYPOINT_ORG_LDIF" || entrypoint_fail "could not load the organisation entry"
}

entrypoint_summary() {
	echo "FEIDE proxy starting with:"
	echo
	echo "  ORGANISASJONSNUMMER     $ORGANISASJONSNUMMER"
	echo "  NAVN                    $NAVN"
	echo "  NOREDUORGACRONYM        $NOREDUORGACRONYM"
	echo "  DOMAIN                  $DOMAIN"
	echo "  BASE_DN                 $BASE_DN"
	echo "  NOREDUORGSCHEMAVERSION  $NOREDUORGSCHEMAVERSION"
	echo "  AD_SERVER               $AD_SERVER"
	echo "  SIKT_BIND_DN            $SIKT_BIND_DN"
	for addr in $ORG_MAIL; do
		echo "  ORG_MAIL                $addr"
	done
	echo "  keytab                  $ENTRYPOINT_KEYTAB"
	echo "  certificate             $ENTRYPOINT_CERT"
	echo
	echo "The organisation number must match Brønnøysundregisteret exactly."
	echo
}

entrypoint_main() {
	entrypoint_load_env
	entrypoint_derive
	entrypoint_check_mounts
	entrypoint_render
	entrypoint_load_org
	entrypoint_summary
	exec /usr/sbin/slapd -d stats -f "$ENTRYPOINT_CONF" -h "ldaps:///"
}

case "$0" in
	*entrypoint.sh) entrypoint_main "$@" ;;
esac
