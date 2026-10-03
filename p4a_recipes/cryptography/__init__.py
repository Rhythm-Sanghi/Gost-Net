import glob
from os.path import join
import subprocess
from pythonforandroid.logger import info
from pythonforandroid.recipe import RustCompiledComponentsRecipe


class CryptographyRecipe(RustCompiledComponentsRecipe):
    """Rust-built ``cryptography`` extension for Android.

    No linker flags are added here. NDK r28+ is the single enforcement point for
    16 KB page sizes: its clang driver injects ``-z max-page-size=16384`` into
    every link line (verified with ``clang -###``), and LLD 19 already defaults
    to 16 KB, so an explicit flag would be redundant. Adding one "for safety"
    would obscure the real provenance of the alignment.

    The only thing this override genuinely needs is the DT_NEEDED fix below.
    """

    name = "cryptography"
    version = "46.0.3"
    url = "https://github.com/pyca/cryptography/archive/refs/tags/{version}.tar.gz"
    depends = ["openssl", "cffi"]

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        openssl_build_dir = self.get_recipe("openssl", self.ctx).get_build_dir(arch.arch)
        build_target = self.RUST_ARCH_CODES[arch.arch].upper().replace("-", "_")
        openssl_include = "{}_OPENSSL_INCLUDE_DIR".format(build_target)
        openssl_libs = "{}_OPENSSL_LIB_DIR".format(build_target)
        env[openssl_include] = join(openssl_build_dir, "include")
        env[openssl_libs] = join(openssl_build_dir)
        return env

    def install_python_package(self, arch, name=None, env=None):
        super().install_python_package(arch, name=name, env=env)
        # Ensure _rust.abi3.so explicitly links to libpython3.11.so in DT_NEEDED for Bionic linker
        install_dir = self.ctx.get_python_install_dir(arch.arch)
        matches = glob.glob(join(install_dir, "**", "_rust.abi3.so"), recursive=True)
        py_ver = self.python_major_minor_version
        for so in matches:
            info(f"Patching DT_NEEDED for {so} with libpython{py_ver}.so")
            try:
                subprocess.run(["patchelf", "--add-needed", f"libpython{py_ver}.so", so], check=True)
            except Exception as e:
                info(f"Failed to patchelf {so}: {e}")


recipe = CryptographyRecipe()
