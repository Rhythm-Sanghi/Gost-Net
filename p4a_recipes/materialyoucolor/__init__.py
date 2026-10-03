from pythonforandroid.recipe import PyProjectRecipe


class MaterialyoucolorRecipe(PyProjectRecipe):
    """``materialyoucolor`` -- a pure-Python, mypyc-optional colour library.

    ``MYCP_PURE_PYTHON=1`` keeps mypyc from compiling ahead-of-time, so this
    recipe produces no native objects of its own and needs no linker flags.
    ``LDCXXSHARED`` still has to be defined because setuptools references it
    unconditionally when probing shared-library flags.

    16 KB page-size compliance comes from NDK r28+ itself; see the note in
    ``p4a_recipes/cryptography/__init__.py``.
    """

    stl_lib_name = "c++_shared"
    version = "3.0.4"
    url = "https://github.com/T-Dynamos/materialyoucolor-python/releases/download/v{version}/materialyoucolor-{version}.tar.gz"

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["LDCXXSHARED"] = env["CXX"] + " -shared"
        env["MYCP_PURE_PYTHON"] = "1"
        return env


recipe = MaterialyoucolorRecipe()
