import glob
from importlib import import_module
from os.path import dirname, basename, isfile, join

target_dirs = ["kor", "us", "ch"]

endpoints = {}
for dir in target_dirs:
    dir_path = dirname(__file__) + "/" + dir
    modules = glob.glob(join(dir_path, "*.py"))
    __all__ = [basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py')]
    for module_name in __all__:
        path = "." + dir + "." + module_name

        result = import_module(path, __package__)
        class_name = result.__name__.split(".")[-1]
        endpoint_class = getattr(result, class_name)
        endpoints[endpoint_class.__name__] = endpoint_class
