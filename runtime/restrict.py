"""Install an inherited syscall boundary after dropping the host UID and capabilities."""

import ctypes
import errno
import os
import resource
import sys

DENIED = (
    "mount", "umount2", "pivot_root", "chroot", "unshare", "setns",
    "ptrace", "process_vm_readv", "process_vm_writev", "bpf", "perf_event_open",
    "add_key", "request_key", "keyctl", "userfaultfd", "open_by_handle_at",
    "init_module", "finit_module", "delete_module", "reboot", "kexec_load",
    "kexec_file_load", "swapon", "swapoff",
)


def install():
    if os.getuid() != 10001 or os.getgid() != 10001:
        raise RuntimeError("Analysis identity isolation unavailable")
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not context:
        raise RuntimeError("Analysis syscall isolation unavailable")
    try:
        for name in DENIED:
            number = library.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and library.seccomp_rule_add(context, 0x00050000 | errno.EPERM, number, 0):
                raise RuntimeError("Analysis syscall isolation unavailable")
        if library.seccomp_load(context):
            raise RuntimeError("Analysis syscall isolation unavailable")
    finally:
        library.seccomp_release(context)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_CPU, (285, 290))


if __name__ == "__main__":
    try:
        install()
    except (OSError, RuntimeError):
        raise SystemExit("Analysis syscall isolation unavailable") from None
    os.execvp(sys.argv[1], sys.argv[1:])
