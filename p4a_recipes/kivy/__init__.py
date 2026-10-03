"""Local python-for-android override for the `kivy` recipe.

Why this exists
---------------
Moving the Android build from NDK r25 to NDK r28 is mandatory for 16 KB page
size support (NDK r28's LLD 19 links every object with 2**14 LOAD alignment by
default). The newer Clang (19) promotes ``-Wincompatible-function-pointer-types``
from a warning to a hard error in C mode, which breaks Kivy's CGL GLES2 backend:

    kivy/graphics/cgl_backend/cgl_gl.c:4382:52: error: incompatible function
    pointer types assigning to 'void (*)(GLuint, GLsizei, const GLchar **, const
    GLint *)' from 'void (GLuint, GLsizei, const GLchar *const *, const GLint *)'

This is a pre-existing Kivy typing mismatch between the GLES2 `glShaderSource`
prototype (`const GLchar *const *`) and Kivy's desktop-GL typedef
(`const GLchar **`). It is *not* a page-size problem and it is not caused by our
code; older Clang merely tolerated it.

We therefore downgrade exactly that one diagnostic to a warning for the Kivy
recipe only. No other warning class is suppressed, and no application source,
cryptography or networking behaviour is changed.

If Kivy is ever upgraded to a release that fixes cgl_gl.c (or to >= 3.0, which
drops the legacy CGL backend), this override can be deleted.

Dropping ``chardet`` from python_depends
----------------------------------------
python-for-android installs requirements that have no recipe by delegating to
pip with no platform constraint (``pythonforandroid/build.py``::

    venv/bin/pip install -v --target <dir> --no-deps -r requirements.txt
    # "Installing pure Python modules with pip"

On an x86_64 build host that resolves ``chardet`` to
``chardet-7.6.0-cp311-cp311-manylinux2014_x86_64...whl``, whose mypyc-compiled
objects are unpacked straight into the arm64-v8a bundle. The 15 ``.so`` files
that land inside ``libpybundle.so`` are therefore both

  * compiled for the wrong CPU (x86-64), so they can never load on ARM64, and
  * linked at 4 KB page alignment, which fails the 16 KB compatibility gate.

``chardet`` publishes no Android wheel, and Kivy never imports it (verified: no
reference to ``chardet`` anywhere in the built Kivy tree). ``requests`` -- which
Kivy's ``kivy.network.urlrequest`` does import -- hard-depends on
``charset_normalizer`` and treats ``chardet`` as an optional extra, so removing
it is behaviour-preserving; ``requests`` falls back to the charset declared in
the ``Content-Type`` header when no detector library is present.

We therefore remove it from the dependency list instead of shipping binaries for
the wrong architecture. ``scripts/check_android_16kb.py`` now also validates the
ELF architecture of every packaged object, so a regression like this fails the
build rather than silently producing an unloadable APK.

Vendored patch files
--------------------
A local recipe *shadows the entire upstream recipe directory*, not just its
Python module: ``pythonforandroid.recipe.Recipe.recipe_dirs`` puts
``local_recipes`` ahead of the bundled ``recipes/``, and ``apply_patch()``
resolves paths against the winning recipe's own directory. The upstream
``kivy`` recipe ships three patch files alongside its ``__init__.py``:

    use_cython.patch                     (applied when kivy < 3.0)
    sdl-gl-swapwindow-nogil.patch        (applied when affected by a deadlock)
    no-ast-str.patch                     (always applied)

Because this override replaces that directory, those files are vendored here
byte-for-byte. Without them a *cached* build still succeeds -- ``prebuild_arch``
never runs when the recipe is already built -- and only a clean build fails,
with the misleading error:

    /usr/bin/patch: **** Can't open patch file .../p4a_recipes/kivy/use_cython.patch

Keep this directory self-contained. If upstream changes a patch, re-vendor it.
"""

from pythonforandroid.recipes.kivy import KivyRecipe as _P4AKivyRecipe


class KivyRecipe(_P4AKivyRecipe):
    # Upstream p4a lists: certifi, chardet, idna, requests, urllib3, filetype.
    # See module docstring for why chardet is dropped.
    python_depends = ["certifi", "idna", "requests", "urllib3", "filetype"]

    # Clang >= 16 errors on the legacy CGL GLES2 glShaderSource typedef mismatch.
    # See module docstring.
    _COMPAT_CFLAGS = " -Wno-incompatible-function-pointer-types"

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)

        for var in ("CFLAGS", "CPPFLAGS"):
            env[var] = env.get(var, "") + self._COMPAT_CFLAGS

        return env


recipe = KivyRecipe()