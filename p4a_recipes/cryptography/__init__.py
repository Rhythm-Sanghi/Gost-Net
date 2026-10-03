import glob
import os
import struct
from os.path import join

from pythonforandroid.logger import info
from pythonforandroid.recipe import RustCompiledComponentsRecipe


def read_dt_needed(path):
    """Return the ``DT_NEEDED`` list of an ELF64 little-endian object.

    Implemented here with the standard library only: this runs on the build
    host during ``build_arch``, where depending on an external toolchain binary
    would make a mandatory linkage assertion fail for the wrong reason.
    """
    with open(path, "rb") as handle:
        data = handle.read()

    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise ValueError(f"{path}: not an ELF file")
    if data[4] != 2 or data[5] != 1:
        raise ValueError(f"{path}: not ELF64 little-endian")

    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]

    loads = []
    dynamic = None
    for index in range(e_phnum):
        offset = e_phoff + index * e_phentsize
        p_type = struct.unpack_from("<I", data, offset)[0]
        p_offset = struct.unpack_from("<Q", data, offset + 8)[0]
        p_vaddr = struct.unpack_from("<Q", data, offset + 16)[0]
        p_filesz = struct.unpack_from("<Q", data, offset + 32)[0]
        if p_type == 1:                      # PT_LOAD
            loads.append((p_vaddr, p_offset, p_filesz))
        elif p_type == 2:                    # PT_DYNAMIC
            dynamic = (p_offset, p_filesz)

    if dynamic is None:
        raise ValueError(f"{path}: no PT_DYNAMIC segment")

    entries = []
    position = dynamic[0]
    while position + 16 <= dynamic[0] + dynamic[1]:
        tag, value = struct.unpack_from("<qQ", data, position)
        position += 16
        if tag == 0:                          # DT_NULL
            break
        entries.append((tag, value))

    strtab = next((v for t, v in entries if t == 5), None)   # DT_STRTAB
    if strtab is None:
        raise ValueError(f"{path}: no DT_STRTAB")

    for vaddr, offset, size in loads:
        if vaddr <= strtab < vaddr + size:
            strtab_off = offset + (strtab - vaddr)
            break
    else:
        raise ValueError(f"{path}: DT_STRTAB outside every PT_LOAD")

    needed = []
    for tag, value in entries:
        if tag != 1:                          # DT_NEEDED
            continue
        start = strtab_off + value
        needed.append(data[start:data.index(b"\0", start)].decode("utf-8", "replace"))
    return needed


class CryptographyRecipe(RustCompiledComponentsRecipe):
    """Rust-built ``cryptography`` extension for Android.

    No linker flags are added here. NDK r28+ is the single enforcement point for
    16 KB page sizes: its clang driver injects ``-z max-page-size=16384`` into
    every link line (verified with ``clang -###``), and LLD 19 already defaults
    to 16 KB, so an explicit flag would be redundant. Adding one "for safety"
    would obscure the real provenance of the alignment.

    The one thing this override genuinely needs is the ``libpython`` link edge.

    Why it is needed
    ----------------
    ``RustCompiledComponentsRecipe`` inherits ``PyProjectRecipe``, whose
    ``build_arch`` installs the finished wheel through ``install_wheel()`` (or
    ``install_prebuilt_wheel()``).  It never calls
    ``PythonRecipe.install_python_package()``, so an override of that method is
    never reached from this recipe class.

    That mattered because on Android every ``dlopen()`` resolves symbols inside
    a linker namespace.  ``libpython3.11.so`` being loaded by the process is not
    enough: an extension that omits it from ``DT_NEEDED`` is aborted by Bionic
    with ``ImportError: dlopen failed: cannot locate symbol "PyExc_TypeError"``.

    python-for-android handles this for C and Cython extensions in
    ``PythonRecipe.get_recipe_env``, which appends ``-L<link_root>
    -lpython<link_version>`` to ``LDFLAGS``.  ``RUSTFLAGS`` is the equivalent
    hook for a Rust ``cdylib``, and this recipe supplies the same two flags so
    the linker records the dependency itself.  No ELF is rewritten afterwards.
    """

    name = "cryptography"
    version = "46.0.3"
    url = "https://github.com/pyca/cryptography/archive/refs/tags/{version}.tar.gz"
    depends = ["openssl", "cffi"]

    @property
    def target_libpython(self):
        """File name of the target interpreter, e.g. ``libpython3.11.so``."""
        return f"libpython{self.ctx.python_recipe.link_version}.so"

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        openssl_build_dir = self.get_recipe("openssl", self.ctx).get_build_dir(arch.arch)
        build_target = self.RUST_ARCH_CODES[arch.arch].upper().replace("-", "_")
        openssl_include = "{}_OPENSSL_INCLUDE_DIR".format(build_target)
        openssl_libs = "{}_OPENSSL_LIB_DIR".format(build_target)
        env[openssl_include] = join(openssl_build_dir, "include")
        env[openssl_libs] = join(openssl_build_dir)

        # Link the Rust extension against the TARGET interpreter, not the host
        # one.  link_root() is the python3 recipe's own android-build output
        # directory, which is also already on p4a's RUSTFLAGS search path; it is
        # named explicitly so the flag set is self-describing.
        link_root = self.ctx.python_recipe.link_root(arch.arch)
        link_version = self.ctx.python_recipe.link_version
        target = join(link_root, self.target_libpython)
        if not os.path.isfile(target):
            raise RuntimeError(
                f"cryptography: target interpreter {target} does not exist, "
                f"refusing to link -lpython{link_version} against anything "
                "else (in particular not a host Python)."
            )
        env["RUSTFLAGS"] = (
            f"{env.get('RUSTFLAGS', '')} "
            f"-Clink-args=-L{link_root} -Clink-args=-lpython{link_version}"
        ).strip()
        info(f"cryptography: linking against target interpreter {target}")
        return env

    def build_arch(self, arch):
        # Covers both install routes of PyProjectRecipe.build_arch: the
        # prebuilt-wheel path and the build-from-source wheel path both return
        # into this frame, so the assertion below always runs.
        super().build_arch(arch)
        self._assert_libpython_linked(arch)

    def _assert_libpython_linked(self, arch):
        """Fail the build unless the extension declares libpython in DT_NEEDED.

        This is a runtime-loadability requirement, not a cosmetic one, so it
        terminates the build instead of logging and continuing.
        """
        install_dir = self.ctx.get_python_install_dir(arch.arch)
        matches = sorted(glob.glob(join(install_dir, "**", "_rust.abi3.so"),
                                   recursive=True))
        if not matches:
            raise RuntimeError(
                f"cryptography: no _rust.abi3.so under {install_dir} after the "
                "build; the Rust extension was never installed, so its Android "
                "native linkage cannot be verified."
            )

        libpython = self.target_libpython
        for path in matches:
            needed = read_dt_needed(path)
            if libpython not in needed:
                raise RuntimeError(
                    f"cryptography: {path} does not declare {libpython} in "
                    f"DT_NEEDED (found: {needed}). On Android this makes the "
                    "module unloadable: Bionic resolves dlopen()ed symbols "
                    "inside a linker namespace, so the undefined Python C-API "
                    "references (for example PyExc_TypeError) go unresolved "
                    "and importing cryptography fails with 'dlopen failed: "
                    "cannot locate symbol'. This indicates the Rust link line "
                    "lost its -lpython argument."
                )
            info(f"cryptography: DT_NEEDED verified -> {needed}")


recipe = CryptographyRecipe()