#!/bin/sh
# Stable security updates plus two ABI-compatible, signed Debian library fixes.
set -eu
apt-get update
apt-get install -y --no-install-recommends --only-upgrade zlib1g
# Stable has no fixed Expat/SQLite package yet. Restrict the additional signed
# repository to these exact libraries; never upgrade the rest of the distribution.
printf 'deb http://deb.debian.org/debian sid main\n' > /etc/apt/sources.list.d/spechelper-library-fixes.list
printf 'Package: *\nPin: release a=unstable\nPin-Priority: -1\n' > /etc/apt/preferences.d/spechelper-library-fixes
apt-get update
apt-get install -y --no-install-recommends libexpat1=2.10.0-1 libsqlite3-0=3.54.1-2
test "$(dpkg-query -W -f='${Version}' libexpat1)" = '2.10.0-1'
test "$(dpkg-query -W -f='${Version}' libsqlite3-0)" = '3.54.1-2'
rm /etc/apt/sources.list.d/spechelper-library-fixes.list /etc/apt/preferences.d/spechelper-library-fixes
rm -rf /var/lib/apt/lists/*
