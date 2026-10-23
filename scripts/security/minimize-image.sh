#!/bin/sh
# Keep package metadata for scanning, but remove unused vulnerable tools and privilege bits.
set -eu
find /usr -xdev -type f -perm /6000 -exec chmod a-s '{}' +
rm -f /usr/bin/infocmp
find /usr/share -type f \( -path '*/Archive/Tar.pm' -o -path '*/Archive/Tar/*' \) -delete
if [ -x /usr/local/bin/python ]; then
  /usr/local/bin/python -m pip uninstall --yes pip
  rm -rf /usr/local/lib/python3.12/ensurepip
fi
