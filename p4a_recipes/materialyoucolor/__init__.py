from pythonforandroid.recipe import PyProjectRecipe


class MaterialyoucolorRecipe(PyProjectRecipe):
    stl_lib_name = "c++_shared"
    version = "3.0.4"
    url = "https://github.com/T-Dynamos/materialyoucolor-python/releases/download/v{version}/materialyoucolor-{version}.tar.gz"

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["LDCXXSHARED"] = env["CXX"] + " -shared"
        env["MYCP_PURE_PYTHON"] = "1"
        return env


recipe = MaterialyoucolorRecipe()
