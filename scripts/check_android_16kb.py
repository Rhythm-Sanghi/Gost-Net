#!/usr/bin/env python3
"""
Gost-Net — Android 16 KB memory-page compatibility gate.

Audits a built APK for modern-Android page-size correctness. This is a RELEASE
GATE: it exits non-zero if any packaged ARM64 native library fails.

What it verifies
----------------
A) ELF LOAD-segment alignment.  Every ``lib/<abi>/*.so`` that is a real ELF
   object must have *all* PT_LOAD segments aligned to at least 2**14 (16384)
   bytes.  A library reporting 2**12 (4096) FAILS -- it cannot be loaded
   correctly by a 16 KB-page kernel.  We additionally require
   ``(p_vaddr - p_offset) % p_align == 0`` for every PT_LOAD, because a large
   declared alignment with a non-congruent offset still faults at mmap time.

B) CPU architecture.  Each ELF must be built for the architecture of the ABI
   directory it was packaged under (arm64-v8a => EM_AARCH64, and so on).  A
   library built for the build host's CPU cannot load on device, so it FAILS
   even if its alignment were correct.  This check exists because
   python-for-android installs recipe-less pure-Python requirements with an
   unconstrained ``pip install --target``, which resolves host-platform wheels
   (observed: an x86-64 manylinux ``chardet`` wheel inside an arm64 APK).

C) ELF LOAD segments nested inside data containers.  python-for-android ships
   Python C-extension modules inside ``libpybundle.so``, which is a *gzip'd tar
   archive*, not an ELF file.  Those inner modules are dlopen()ed at runtime and
   must therefore satisfy exactly the same rules.  They are audited recursively.

D) GNU_RELRO presence per ELF library (reported; see --strict-relro).

E) APK packaging alignment via ``zipalign -c -P 16 -v 4`` (Build-Tools 35+).
   This is checked *separately* from (A)-(C) on purpose: a correctly aligned ELF
   inside a badly packed APK still fails to load, and vice versa.

F) APK payload hygiene. Every zip entry name is matched against a deny-list
   covering research modules, the test suite, scratch/dev caches, environment
   files, secret and signing keys, developer credentials, database files,
   developer machine paths, crash logs and VCS metadata.

G) Python C-API runtime linkage.  Page alignment does not imply loadability:
   on Android every dlopen() resolves against a linker namespace, so a Python
   extension that leaves ``Py*`` symbols undefined must itself declare the
   interpreter in ``DT_NEEDED``.  For every ELF object in the APK (packaged
   directly or nested in ``libpybundle.so``) that references the Python C-API,
   this group requires that a packaged interpreter is named in ``DT_NEEDED`` and
   that it really exports every symbol the extension left undefined, with
   default visibility.  A module missing that edge is reported by the device as
   ``ImportError: dlopen failed: cannot locate symbol "PyExc_TypeError"`` and
   is invisible to both a page-size audit and the desktop test suite.

Nothing is special-cased by library name: any ELF under lib/<abi>/ is audited,
and any non-ELF container is decompressed and audited internally.

Usage
-----
    python3 scripts/check_android_16kb.py <apk> [<apk> ...] [options]

Exit codes
----------
    0  every ELF library is 16 KB compliant (and packaging verified)
    1  at least one library failed, or a required tool was unavailable
    2  usage error
"""

from __future__ import annotations

import argparse
import glob
import gzip
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile

PAGE_SIZE_16KB = 1 << 14          # 16384
PT_LOAD = 1
PT_GNU_RELRO = 0x6474E552

# e_machine values we expect per APK ABI directory. A native object whose
# architecture does not match the ABI it was packaged under cannot load, so it
# is reported as a hard failure regardless of its page alignment.
EM_386 = 3
EM_ARM = 40
EM_X86_64 = 62
EM_AARCH64 = 183

ABI_MACHINE = {
    "arm64-v8a": EM_AARCH64,
    "armeabi-v7a": EM_ARM,
    "x86_64": EM_X86_64,
    "x86": EM_386,
}

MACHINE_NAME = {
    EM_386: "x86",
    EM_ARM: "ARM",
    EM_X86_64: "x86-64",
    EM_AARCH64: "AArch64",
}


def _machine_label(value: int) -> str:
    return MACHINE_NAME.get(value, f"unknown(0x{value:x})")


# --------------------------------------------------------------------------
# ELF parsing
# --------------------------------------------------------------------------
def _align_label(value: int) -> str:
    if value <= 0:
        return "none"
    return f"2**{value.bit_length() - 1} ({value})"


def parse_elf(data: bytes) -> dict:
    """Parse an ELF64 little-endian object's program headers."""
    if len(data) < 64 or not data.startswith(b"\x7fELF"):
        return {"is_elf": False}

    ei_class = data[4]
    ei_data = data[5]
    if ei_class != 2:
        return {"is_elf": False, "reason": f"not ELF64 (EI_CLASS={ei_class})"}
    if ei_data != 1:
        return {"is_elf": False, "reason": "not little-endian"}

    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]
    e_machine = struct.unpack_from("<H", data, 18)[0]

    loads: list[int] = []
    has_relro = False
    non_congruent = False

    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if off + 56 > len(data):
            return {"is_elf": False, "reason": "truncated program header table"}

        p_type = struct.unpack_from("<I", data, off)[0]
        p_offset = struct.unpack_from("<Q", data, off + 8)[0]
        p_vaddr = struct.unpack_from("<Q", data, off + 16)[0]
        p_align = struct.unpack_from("<Q", data, off + 48)[0]

        if p_type == PT_LOAD:
            loads.append(p_align)
            if p_align > 0 and (p_vaddr - p_offset) % p_align != 0:
                non_congruent = True
        elif p_type == PT_GNU_RELRO:
            has_relro = True

    if not loads:
        return {"is_elf": False, "reason": "no PT_LOAD segments"}

    min_align = min(loads)
    return {
        "is_elf": True,
        "machine": e_machine,
        "load_count": len(loads),
        "min_align": min_align,
        "max_align": max(loads),
        "has_relro": has_relro,
        "congruent": not non_congruent,
        "ok": min_align >= PAGE_SIZE_16KB and not non_congruent,
    }


# --------------------------------------------------------------------------
# ELF dynamic linking: DT_NEEDED and .dynsym
# --------------------------------------------------------------------------
# Both readers are pure standard library on purpose. The gate has to run on a
# bare CI runner and inside a p4a build where no NDK toolchain is guaranteed, so
# it must not shell out to llvm-readelf in order to reach a verdict.
SHT_STRTAB = 3
SHT_DYNSYM = 11
STV_DEFAULT = 0

_DT_NULL = 0
_DT_NEEDED = 1
_DT_STRTAB = 5
_PT_DYNAMIC = 2


def _elf64(data: bytes) -> bool:
    return len(data) >= 64 and data[:4] == b"\x7fELF" and data[4] == 2 and data[5] == 1


def _phdrs(data: bytes) -> list[tuple[int, int, int, int, int]]:
    """Program headers as ``(p_type, p_offset, p_vaddr, p_filesz, p_align)``.

    Every read is bounds-checked. A truncated or corrupt object yields fewer
    headers instead of raising ``struct.error``: a gate that aborts on the
    first malformed library would skip auditing all the others, which is the
    one thing a gate must never do.
    """
    if not _elf64(data):
        return []
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]
    if e_phentsize < 56:
        return []
    out = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if off + 56 > len(data):
            break
        out.append((
            struct.unpack_from("<I", data, off)[0],
            struct.unpack_from("<Q", data, off + 8)[0],
            struct.unpack_from("<Q", data, off + 16)[0],
            struct.unpack_from("<Q", data, off + 32)[0],
            struct.unpack_from("<Q", data, off + 48)[0],
        ))
    return out


def _load_segments(data: bytes) -> list[tuple[int, int, int]]:
    return [(vaddr, offset, filesz)
            for p_type, offset, vaddr, filesz, _al in _phdrs(data)
            if p_type == PT_LOAD]


def _vaddr_to_offset(loads: list[tuple[int, int, int]], vaddr: int) -> int | None:
    for lvaddr, loff, lsz in loads:
        if lvaddr <= vaddr < lvaddr + lsz:
            return loff + (vaddr - lvaddr)
    return None


def elf_dt_needed(data: bytes) -> list[str]:
    """DT_NEEDED library names of an ELF64 LE object ([] when there are none).

    Malformed input yields ``[]`` rather than an exception, so a single
    corrupt library cannot abort the audit of every other library.
    """
    if not _elf64(data):
        return []

    loads: list[tuple[int, int, int]] = []
    dynamic = None
    for p_type, p_offset, p_vaddr, p_filesz, _al in _phdrs(data):
        if p_type == PT_LOAD:
            loads.append((p_vaddr, p_offset, p_filesz))
        elif p_type == _PT_DYNAMIC:
            dynamic = (p_offset, p_filesz)

    if dynamic is None:
        return []

    entries: list[tuple[int, int]] = []
    pos = dynamic[0]
    while pos + 16 <= min(dynamic[0] + dynamic[1], len(data)):
        tag, value = struct.unpack_from("<qQ", data, pos)
        pos += 16
        if tag == _DT_NULL:
            break
        entries.append((tag, value))

    strtab = next((v for t, v in entries if t == _DT_STRTAB), None)
    if strtab is None:
        return []
    strtab_off = _vaddr_to_offset(loads, strtab)
    if strtab_off is None or strtab_off >= len(data):
        return []

    needed = []
    for tag, value in entries:
        if tag != _DT_NEEDED:
            continue
        start = strtab_off + value
        if start >= len(data):
            continue
        end = data.find(b"\0", start)
        if end < 0:
            continue
        needed.append(data[start:end].decode("utf-8", "replace"))
    return needed


def elf_dynsyms(data: bytes) -> dict[str, tuple[bool, int]]:
    """Map every ``.dynsym`` name to ``(is_defined, st_other_visibility)``.

    A name that appears both undefined and defined is recorded as defined,
    which is what the dynamic linker itself does.
    """
    out: dict[str, tuple[bool, int]] = {}
    if not _elf64(data):
        return out

    e_shoff = struct.unpack_from("<Q", data, 40)[0]
    e_shentsize = struct.unpack_from("<H", data, 58)[0]
    e_shnum = struct.unpack_from("<H", data, 60)[0]
    if e_shoff == 0 or e_shnum == 0 or e_shentsize < 64:
        return out
    # Bounds-check the section header table up front. Without this a truncated
    # object raises struct.error and the whole audit stops here.
    if e_shoff + e_shnum * e_shentsize > len(data):
        return out

    sections = [struct.unpack_from("<IIQQQQIIQQ", data, e_shoff + i * e_shentsize)
                for i in range(e_shnum)]

    for sec in sections:
        _nm, stype, _fl, _ad, soff, ssize, slink, _inf, _al, sentsize = sec
        if stype != SHT_DYNSYM or sentsize == 0 or slink >= len(sections):
            continue
        strtab = sections[slink]
        stroff, strsize = strtab[4], strtab[5]
        if stroff + strsize > len(data):
            continue
        if soff + ssize > len(data):
            continue
        for k in range(ssize // sentsize):
            so = soff + k * sentsize
            if so + 24 > len(data):
                break
            st_name, _st_info, st_other, st_shndx = struct.unpack_from(
                "<IBBH", data, so)
            if st_name == 0 or stroff + st_name >= stroff + strsize:
                continue
            start = stroff + st_name
            end = data.find(b"\0", start, stroff + strsize)
            if end < 0:
                continue
            name = data[start:end].decode("utf-8", "replace")
            defined = st_shndx != 0
            prev = out.get(name)
            if prev is None or (not prev[0] and defined):
                out[name] = (defined, st_other & 0x3)
    return out


def _audit_blob(name: str, data: bytes, failures: list, relro_missing: list,
                expected_machine: int, depth: int = 0,
                samples: list | None = None, abi: str = "") -> dict:
    """Recursively audit one packaged blob.

    ``expected_machine`` is the e_machine the ABI directory requires; pass None
    to skip the architecture check.
    """
    info = parse_elf(data)

    if info.get("is_elf"):
        machine = info["machine"]
        arch_ok = expected_machine is None or machine == expected_machine
        if not info["has_relro"]:
            relro_missing.append(name)
        if samples is not None:
            # Retained for the Python C-API linkage audit: a dlopen()ed extension
            # must be checked for loadability, not only for page alignment.
            samples.append((name, data, abi))
        return {
            "name": name,
            "kind": "ELF",
            "machine": machine,
            "arch_ok": arch_ok,
            "min_align": info["min_align"],
            "congruent": info["congruent"],
            "relro": info["has_relro"],
            "ok": info["ok"] and arch_ok,
        }

    # Not an ELF. If it is a gzip'd tar (python-for-android's libpybundle.so),
    # its contents are dlopen()ed at runtime and must be audited too.
    if depth < 3 and data[:2] == b"\x1f\x8b":
        inner_bad: list[str] = []
        inner_total = 0
        inner_worst = 0
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                with tarfile.open(fileobj=gz) as tar:
                    for member in tar.getmembers():
                        if not member.isfile() or not member.name.endswith(".so"):
                            continue
                        fh = tar.extractfile(member)
                        if fh is None:
                            continue
                        blob = fh.read()
                        r = parse_elf(blob)
                        inner_total += 1
                        if samples is not None and r.get("is_elf"):
                            samples.append((member.name, blob, abi))
                        if not r.get("is_elf"):
                            inner_bad.append(f"{member.name} (not ELF)")
                            continue

                        # Track the weakest module in the container whether or
                        # not it passes, so the summary can never look better
                        # than the contents actually are.
                        if inner_worst == 0:
                            inner_worst = r["min_align"]
                        else:
                            inner_worst = min(inner_worst, r["min_align"])

                        arch_ok = expected_machine is None or \
                            r["machine"] == expected_machine
                        if not arch_ok:
                            inner_bad.append(
                                f"{member.name} [wrong architecture: "
                                f"{_machine_label(r['machine'])}, "
                                f"expected {_machine_label(expected_machine)}]"
                            )
                        elif not r["ok"]:
                            inner_bad.append(
                                f"{member.name} [{_align_label(r['min_align'])}]"
                            )
        except (OSError, tarfile.TarError, EOFError) as exc:
            failures.append((f"{name}: cannot unpack archive ({exc})", "UNREADABLE"))
            return {"name": name, "kind": "ARCHIVE", "ok": False,
                    "members": 0, "bad_members": 0, "min_align": 0}

        if inner_bad:
            failures.append(
                (f"{name}: {len(inner_bad)}/{inner_total} bundled modules "
                 f"not 16 KB aligned or wrong architecture",
                 ", ".join(inner_bad[:5]) + (" ..." if len(inner_bad) > 5 else ""))
            )
        return {
            "name": name,
            "kind": "ARCHIVE",
            "members": inner_total,
            "min_align": inner_worst,
            "bad_members": len(inner_bad),
            "ok": not inner_bad,
        }

    failures.append((f"{name}: {info.get('reason', 'not a valid ELF object')}", "INVALID"))
    return {"name": name, "kind": "INVALID", "ok": False}


# --------------------------------------------------------------------------
# APK audit
# --------------------------------------------------------------------------
def _build_tools_rank(bt_dir: str) -> tuple[int, ...]:
    """Rank a build-tools directory by its numeric version.

    Plain string sorting is wrong here: "34.0.0" sorts before "35.0.0" and
    also before "9.0.0", so the first match is not the newest. A real CI run
    failed for exactly that reason: the runner had both 34.0.0 and 35.0.0,
    the lexicographically first one won, and it rejected the -P flag that
    Build-Tools 35 introduced.
    """
    nums = re.findall(r"\d+", os.path.basename(bt_dir))
    return tuple(int(n) for n in nums) if nums else (0,)


def zipalign_candidates() -> list[str]:
    """Every zipalign we could use, most capable first.

    Order: an explicit $ZIPALIGN, then build-tools directories across every
    SDK root sorted by descending numeric version, then PATH. Duplicates
    (the same binary reachable by two paths) are collapsed.
    """
    found: list[str] = []

    explicit = os.environ.get("ZIPALIGN")
    if explicit and os.path.isfile(explicit):
        found.append(explicit)

    roots: list[str] = []
    for var in ("ANDROID_SDK_ROOT", "ANDROID_HOME", "ANDROIDSDK"):
        if os.environ.get(var):
            roots.append(os.environ[var])
    roots.append(os.path.expanduser("~/.buildozer/android/platform/android-sdk"))
    roots.append("/usr/local/lib/android/sdk")

    ranked: list[tuple[tuple[int, ...], str]] = []
    for root in roots:
        for bt in glob.glob(os.path.join(root, "build-tools", "*")):
            exe = os.path.join(bt, "zipalign")
            for name in (exe, exe + (".exe" if os.name == "nt" else "")):
                if os.path.isfile(name):
                    ranked.append((_build_tools_rank(bt), name))
                    break
    for _, exe in sorted(ranked, key=lambda t: t[0], reverse=True):
        found.append(exe)

    which = shutil.which("zipalign")
    if which:
        found.append(which)

    seen: set[str] = set()
    ordered: list[str] = []
    for exe in found:
        real = os.path.realpath(exe)
        if real not in seen:
            seen.add(real)
            ordered.append(exe)
    return ordered


def find_zipalign() -> str | None:
    """The highest-versioned zipalign candidate, or None if none exists."""
    cands = zipalign_candidates()
    return cands[0] if cands else None


def run_zipalign(apk: str) -> tuple[bool, str, str]:
    """Run ``zipalign -c -P 16 -v 4`` against each candidate in turn.

    ``-P`` was added in Build-Tools 35, so an older zipalign aborts with
    "invalid option -- 'P'" instead of reporting on the APK at all. That is
    not evidence the APK is misaligned, so such binaries are skipped and
    only a genuine verdict from a capable binary -- or the exhaustion of
    every candidate -- decides the result.

    Returns ``(ok, output, status)`` where status is one of:
      "ok"           a capable zipalign ran and passed
      "misaligned"   a capable zipalign ran and rejected the APK
      "missing"      no zipalign is installed at all
      "incompatible" zipalign exists but none supports -P 16
    """
    cands = zipalign_candidates()
    if not cands:
        return False, ("zipalign not found (install Android Build-Tools 35+ "
                       "or set $ZIPALIGN)"), "missing"

    rejected: list[str] = []
    last_output = ""
    for exe in cands:
        try:
            proc = subprocess.run(
                [exe, "-c", "-P", "16", "-v", "4", apk],
                capture_output=True, text=True, timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            rejected.append(f"{exe}: {exc}")
            continue

        out = (proc.stdout or "") + (proc.stderr or "")
        last_output = out.strip()

        if "invalid option" in out or "unknown flag" in out:
            rejected.append(f"{exe}: too old for -P (Build-Tools 35+ required)")
            continue

        ok = proc.returncode == 0 and "Verification successful" in out
        # Either way this is a real verdict from a capable binary.
        return ok, out.strip(), ("ok" if ok else "misaligned")

    detail = "; ".join(rejected) if rejected else "no usable zipalign"
    msg = (f"no zipalign supporting '-P 16' could be used ({detail}). "
           "Install Android Build-Tools 35+.")
    if last_output:
        msg += f"\nLast output:\n{last_output}"
    return False, msg, "incompatible"


# --------------------------------------------------------------------------
# APK payload hygiene
# --------------------------------------------------------------------------
# Research code, the test suite, scratch material, credentials and developer
# machine paths must never ship. These are matched against APK *entry names*,
# which is the authoritative list of what is packaged -- it cannot be fooled by
# content that merely looks innocent at runtime.
FORBIDDEN_PAYLOAD = {
    "research modules": r"(^|/)research(/|$)|(^|/)experiments?(/|$)",
    "test suite": r"(^|/)tests?(/|$)|(^|/)conftest\.py$|(^|/)test_[^/]*\.py$|_test\.py$",
    "scratch / dev caches": r"(^|/)scratch(/|$)|(^|/)\.pytest_cache(/|$)|(^|/)__pycache__(/|$)",
    "environment files": r"(^|/)\.env($|\.)|(^|/)\.auth_secrets$|(^|/)\.db_salt$",
    "secret / signing keys": r"secret\.key(\.enc)?$|signing\.key(\.enc)?$|\.(keystore|jks|p12|pem|key)$",
    "developer credentials": r"(^|/)(id_rsa|id_ed25519|\.netrc|\.git-credentials)$",
    "database files": r"\.db$|\.sqlite3?$",
    "developer machine paths": r"/mnt/c/Users/|[A-Za-z]:[/\\]Users[/\\]|/home/runner/|/home/[a-z]+/|/root/",
    "crash / device logs": r"(^|/)(tombstone[^/]*|crash[^/]*|logcat[^/]*|[^/]*\.log)$",
    "VCS metadata": r"(^|/)\.git(/|$)",
}


def audit_payload(entries: list[str]) -> tuple[bool, list[tuple[str, list[str]]]]:
    """Return (ok, [(category, offending entry names)])."""
    problems: list[tuple[str, list[str]]] = []
    for label, pattern in FORBIDDEN_PAYLOAD.items():
        rx = re.compile(pattern, re.IGNORECASE)
        hits = [n for n in entries if rx.search(n)]
        if hits:
            problems.append((label, hits))
    return not problems, problems


# --------------------------------------------------------------------------
# Python C-API runtime linkage
# --------------------------------------------------------------------------
# Page alignment does not imply loadability. On Android every dlopen() resolves
# against a linker namespace, so a Python extension that references Py* symbols
# must itself declare the interpreter in DT_NEEDED: the fact that libpython is
# already mapped by the process is not sufficient. An extension that omits the
# edge aborts at import time with
#
#     ImportError: dlopen failed: cannot locate symbol "PyExc_TypeError"
#
# which is a *runtime* failure invisible to a page-size audit and to every
# desktop test. This group therefore checks, for every ELF object in the APK
# (packaged directly or nested inside libpybundle.so):
#
#   1. a libpython shared object is packaged under the same ABI directory;
#   2. each object referencing Py* names a packaged libpython in DT_NEEDED;
#   3. every undefined Py* symbol is exported by that provider, with default
#      visibility.
#
# Nothing here is keyed on a library name: any extension that uses the Python
# C-API is subject to the same three rules.

PY_API_PREFIX = "Py"
LIBPYTHON_NEEDED = re.compile(r"^libpython\d")


def linkage_guard_problem(link_checked: int, interpreters: list[str],
                          sample_count: int) -> str | None:
    """Reason to fail when the linkage audit examined nothing.

    An APK that ships an interpreter and Python extensions must produce at
    least one consumer. Reaching zero means the symbol reader stopped
    understanding the objects, which would otherwise downgrade this group to a
    silent "N/A" pass -- exactly the failure mode a gate exists to prevent.

    Returns the failure message, or ``None`` when no guard is warranted.
    """
    if link_checked != 0 or not interpreters:
        return None
    return (
        f"no ELF in the APK reported any Python C-API reference, yet "
        f"{', '.join(interpreters)} is packaged. The linkage audit found "
        f"{sample_count} ELF object(s) but zero consumers, which means the "
        f"dynamic symbol table could not be read -- refusing to pass."
    )


def audit_python_api_linkage(
        samples: list[tuple[str, bytes, str]],
        packaged: dict[str, dict[str, bytes]]
) -> tuple[bool, int, list[str]]:
    """Return ``(ok, consumers_checked, [failure descriptions])``.

    ``samples`` is a list of ``(label, elf_bytes, abi_directory)`` for every
    ELF object in the APK, packaged directly or nested in a container.
    ``packaged`` maps an ABI directory to ``{basename: bytes}`` of the ELF
    libraries shipped under it.

    The provider is taken from the consumer's own DT_NEEDED rather than guessed,
    so the check asks exactly the question that matters at dlopen() time: does the
    interpreter this module names exist in the APK, and does it really export the
    symbols the module left undefined?
    """
    if not samples:
        return True, 0, []

    problems: list[str] = []
    checked = 0
    for name, blob, abi in samples:
        undef = sorted(sym for sym, (defined, _v) in elf_dynsyms(blob).items()
                       if not defined and sym.startswith(PY_API_PREFIX))
        if not undef:
            continue
        checked += 1

        needed = elf_dt_needed(blob)
        declared = [n for n in needed if LIBPYTHON_NEEDED.match(n)]
        if not declared:
            problems.append(
                f"{name}: references {len(undef)} Python C-API symbols "
                f"(e.g. {', '.join(undef[:3])}) but declares no Python "
                f"interpreter in DT_NEEDED (found: {needed}). Android resolves "
                f"dlopen()ed symbols per linker namespace, so the interpreter "
                f"must be an explicit dependency or the import fails with "
                f"'dlopen failed: cannot locate symbol'."
            )
            continue

        libs = packaged.get(abi, {})
        absent = [p for p in declared if p not in libs]
        resolved: set[str] = set()
        for provider in declared:
            if provider not in libs:
                continue
            table = elf_dynsyms(libs[provider])
            for sym in undef:
                defined, vis = table.get(sym, (False, STV_DEFAULT))
                if defined and vis == STV_DEFAULT:
                    resolved.add(sym)

        if absent:
            problems.append(
                f"{name}: DT_NEEDED names interpreter(s) that are not packaged "
                f"under lib/{abi}/: {', '.join(absent)}"
            )
        missing = [s for s in undef if s not in resolved]
        if missing:
            problems.append(
                f"{name}: {len(missing)} of {len(undef)} Python C-API symbols are "
                f"not exported with default visibility by "
                f"{', '.join(declared)} (e.g. {', '.join(missing[:3])})"
            )

    return not problems, checked, problems


def audit_apk(apk: str, strict_relro: bool, allow_missing_zipalign: bool) -> bool:
    print("=" * 78)
    print(f"APK : {apk}")
    print(f"SIZE: {os.path.getsize(apk):,} bytes")
    print("=" * 78)

    failures: list[tuple[str, str]] = []
    relro_missing: list[str] = []
    rows: list[dict] = []
    samples: list[tuple[str, bytes, str]] = []

    with zipfile.ZipFile(apk) as zf:
        entries = zf.namelist()
        abis = sorted({n.split("/")[1] for n in entries if n.startswith("lib/")})
        native = sorted(n for n in entries
                        if n.startswith("lib/") and n.endswith(".so"))

        if not native:
            print("[!] FAIL: no native libraries packaged under lib/.")
            return False

        arm64 = [n for n in native if n.split("/")[1] == "arm64-v8a"]
        other = [n for n in native if n.split("/")[1] != "arm64-v8a"]

        print(f"ABIs packaged : {', '.join(abis)}")
        print(f"arm64-v8a .so : {len(arm64)}")
        if other:
            print(f"other-ABI .so : {len(other)} (not subject to the arm64 gate)")
        print()

        print(f"{'library':<30} {'kind':<9} {'arch':<9} {'min LOAD align':<16} "
              f"{'RELRO':<6} {'result'}")
        print("-" * 92)

        for path in native:
            abi = path.split("/")[1]
            expected = ABI_MACHINE.get(abi)
            res = _audit_blob(os.path.basename(path), zf.read(path),
                              failures, relro_missing, expected,
                              samples=samples, abi=abi)
            rows.append(res)

            # Record every failing ELF by name so the failure report is exact.
            if res["kind"] == "ELF" and not res["ok"]:
                problems = []
                if not res.get("arch_ok", True):
                    wanted = ("an architecture this gate does not recognise"
                              if expected is None
                              else _machine_label(expected))
                    problems.append(
                        f"built for {_machine_label(res['machine'])}, but "
                        f"packaged under lib/{abi}/ which requires {wanted}"
                    )
                if res["min_align"] < PAGE_SIZE_16KB:
                    problems.append(
                        f"min LOAD alignment {_align_label(res['min_align'])} "
                        f"< 2**14 (16384)"
                    )
                if not res.get("congruent", True):
                    problems.append("p_vaddr/p_offset not congruent with p_align")
                failures.append((res["name"], "; ".join(problems)))

            align = _align_label(res["min_align"]) \
                if res["kind"] in ("ELF", "ARCHIVE") else "-"
            arch = _machine_label(res["machine"]) if res["kind"] == "ELF" else "-"
            relro = "-" if res["kind"] != "ELF" else ("yes" if res.get("relro") else "NO")
            status = "ALIGNED" if res["ok"] else "UNALIGNED"
            if res["kind"] == "ARCHIVE":
                status = (f"ALIGNED ({res['members']} modules)"
                          if res["ok"] else
                          f"UNALIGNED ({res['bad_members']}/{res['members']})")
            elif res["kind"] == "INVALID":
                status = "INVALID"
            elif res["ok"]:
                status = "ALIGNED"
            elif not res.get("arch_ok", True):
                # Distinguish "correct CPU, wrong page size" from "wrong CPU".
                # Only the former is a page-size fault.
                status = "MISMATCH"
            print(f"{res['name']:<30} {res['kind']:<9} {arch:<9} {align:<16} "
                  f"{relro:<6} {status}")

        print("-" * 92)

    # --- ELF gate -----------------------------------------------------------
    print()
    elf_rows = [r for r in rows if r["kind"] == "ELF"]
    if elf_rows:
        worst = min(elf_rows, key=lambda r: r["min_align"])
        print(f"ELF libraries audited : {len(elf_rows)}")
        print(f"Lowest alignment seen : {_align_label(worst['min_align'])} "
              f"({worst['name']})")
        if not relro_missing:
            print(f"GNU_RELRO            : present on all {len(elf_rows)} ELF libraries")
        else:
            print(f"GNU_RELRO            : MISSING on {len(relro_missing)} "
                  f"-> {', '.join(relro_missing)}")

    if failures:
        print()
        print("[!] ELF PAGE-SIZE FAILURES:")
        for name, detail in failures:
            print(f"    FAIL  {name}")
            print(f"          {detail}")

    # --- Packaging gate -----------------------------------------------------
    print()
    print("APK packaging alignment (zipalign -c -P 16 -v 4):")
    zip_ok, zip_out, zip_status = run_zipalign(apk)
    if zip_ok:
        print("    PASS - Verification successful")
    elif zip_status in ("missing", "incompatible") and allow_missing_zipalign:
        print(f"    SKIP - {zip_out}; ELF audit still enforced")
    else:
        print(f"    FAIL - {zip_out}")
        tail = zip_out.splitlines()[-6:]
        for line in tail:
            print(f"      | {line}")

    # --- Payload hygiene ----------------------------------------------------
    print()
    print("APK payload hygiene:")
    payload_ok, payload_problems = audit_payload(entries)
    if payload_ok:
        print(f"    PASS - {len(entries)} entries, no research / tests / scratch /")
        print("           credentials / developer paths detected")
    else:
        for label, hits in payload_problems:
            print(f"    FAIL  {label}: {len(hits)} entry(ies)")
            for h in hits[:8]:
                print(f"            {h}")
            if len(hits) > 8:
                print(f"            ... and {len(hits) - 8} more")

    # --- Python C-API linkage gate -------------------------------------------
    print()
    print("Python C-API runtime linkage (dlopen loadability):")
    packaged: dict[str, dict[str, bytes]] = {}
    for name, blob, abi in samples:
        packaged.setdefault(abi, {})[name.rsplit("/", 1)[-1]] = blob
    link_ok, link_checked, link_problems = audit_python_api_linkage(samples, packaged)

    # An APK that ships an interpreter and Python extensions must produce at
    # least one consumer; zero means the reader stopped understanding the
    # objects and this group would silently degrade to "N/A".
    interpreters = sorted({
        base for libs in packaged.values() for base in libs
        if LIBPYTHON_NEEDED.match(base)
    })
    guard = linkage_guard_problem(link_checked, interpreters, len(samples))
    if guard is not None:
        link_ok = False
        link_problems = [guard]

    if link_ok:
        if link_checked == 0:
            print("    N/A - no packaged ELF references the Python C-API")
        else:
            print(f"    PASS - {link_checked} ELF object(s) reference the Python C-API;")
            print("           each declares a packaged interpreter in DT_NEEDED and")
            print("           every undefined Py* symbol is exported with default")
            print("           visibility")
    else:
        for problem in link_problems:
            print(f"    FAIL  {problem}")

    # --- Verdict ------------------------------------------------------------
    print()
    # A packaging check only counts as satisfied if a capable zipalign
    # actually passed it, or the operator explicitly opted out of having one.
    packaging_ok = zip_ok or (zip_status in ("missing", "incompatible")
                              and allow_missing_zipalign)
    print("=" * 78)
    ok = (not failures and packaging_ok and payload_ok and link_ok
          and (not strict_relro or not relro_missing))
    if ok:
        print("RESULT: PASS - every packaged ARM64 native library is 16 KB aligned")
        if zip_ok:
            print("        and APK packaging alignment verified (zipalign -P 16).")
        else:
            # Never claim the ZIP half was verified when it was opted out of.
            reason = ("zipalign not installed" if zip_status == "missing"
                      else "no installed zipalign supports -P 16")
            print(f"        (APK packaging alignment NOT verified: {reason}")
            print("         and --allow-missing-zipalign was given.)")
    else:
        print("RESULT: FAIL")
        if failures:
            print(f"        {len(failures)} library(ies) failed the ELF 16 KB test.")
        if not zip_ok:
            if zip_status == "missing":
                print("        APK ZIP alignment could not be verified: zipalign not found.")
            elif zip_status == "incompatible":
                print("        APK ZIP alignment could not be verified: no installed "
                      "zipalign supports -P 16 (Build-Tools 35+ required).")
            else:
                print("        APK ZIP alignment verification failed.")
        if not payload_ok:
            print(f"        {len(payload_problems)} forbidden payload categor(ies) present.")
        if not link_ok:
            print(f"        {len(link_problems)} Python C-API linkage failure(s): "
                  "an extension the app imports at startup cannot be dlopen()ed.")
        if strict_relro and relro_missing:
            print(f"        {len(relro_missing)} library(ies) lack GNU_RELRO.")
    print("=" * 78)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Gost-Net Android 16 KB page-size gate")
    ap.add_argument("apks", nargs="*", help="APK file(s) to audit")
    ap.add_argument("--strict-relro", action="store_true",
                    help="also fail the gate when an ELF library lacks GNU_RELRO")
    ap.add_argument("--allow-missing-zipalign", action="store_true",
                    help="do not fail solely because zipalign is unavailable")
    args = ap.parse_args()

    if not args.apks:
        print(__doc__)
        return 2

    all_ok = True
    for apk in args.apks:
        if not os.path.isfile(apk):
            print(f"[!] FAIL: APK not found: {apk}")
            all_ok = False
            continue
        if not audit_apk(apk, args.strict_relro, args.allow_missing_zipalign):
            all_ok = False
        if len(args.apks) > 1:
            print()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())