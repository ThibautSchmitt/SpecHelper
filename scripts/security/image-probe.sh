#!/bin/sh
# Material evidence for exact-image applicability review; output contains no environment values.
set -eu
test -z "$(find /usr -xdev -type f -perm /6000 -print -quit)"
test ! -e /usr/bin/infocmp
test -z "$(find /usr/share -type f -path '*/Archive/Tar.pm' -print -quit)"
test ! -e /usr/lib/systemd/systemd-homed
test ! -e /usr/libexec/systemd/systemd-homed
test ! -e /usr/lib/gnupg/tpm2daemon
test ! -e /usr/libexec/gnupg/tpm2daemon
test ! -e /usr/bin/tiffcrop
test -z "${DISPLAY:-}"
test ! -e /tmp/.X11-unix
if [ -f /etc/fstab ]; then
  awk 'NF && $1 !~ /^#/ {exit 1}' /etc/fstab
fi
awk '$1 == "NoNewPrivs:" {if ($2 != 1) exit 1; seen=1} END {if (!seen) exit 1}' /proc/self/status
nonroot=true
if [ "$(id -u)" = 0 ]; then nonroot=false; fi
github_fixed=false
if command -v gh >/dev/null 2>&1; then
  case "$(gh --version)" in 'gh version 2.103.2'*) github_fixed=true ;; esac
fi
printf '{"no_suid_sgid":true,"no_infocmp":true,"no_perl_tar":true,"no_homed":true,"no_tpm_daemon":true,"no_tiffcrop":true,"no_x_server":true,"no_fstab_mounts":true,"no_new_privileges":true,"github_fixed_version":%s,"nonroot":%s}\n' "$github_fixed" "$nonroot"
