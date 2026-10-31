import sys
import types

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
    sys.modules["tomllib"] = tomllib

if "toml" not in sys.modules:
    toml_mod = types.ModuleType("toml")
    def _load(f, *a, **kw):
        if hasattr(f, "read"):
            content = f.read()
            if isinstance(content, bytes):
                return tomllib.loads(content.decode("utf-8"))
            return tomllib.loads(content)
        with open(f, "rb") as fp:
            return tomllib.load(fp)
    toml_mod.load = _load
    toml_mod.loads = tomllib.loads
    sys.modules["toml"] = toml_mod


class _StubItem:
    def __new__(cls, *args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return super().__new__(cls)

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return self

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return self

    @classmethod
    def __class_getitem__(cls, item):
        return cls


class _StubModule(types.ModuleType):
    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _StubItem


for mod_name in [
    "langchain_core",
    "langchain_core.prompts",
    "langchain_core.messages",
    "langchain_core.language_models",
    "langchain_core.language_models.chat_models",
    "langchain_core.tools",
    "langchain_core.runnables",
    "langchain_core.outputs",
    "langchain_core.callbacks",
    "langchain_openai",
    "langchain_openai.chat_models",
    "langchain_openai.chat_models.base",
    "langchain_anthropic",
    "langchain_google_genai",
    "langgraph",
    "langgraph.graph",
    "langgraph.prebuilt",
    "chromadb",
    "chromadb.config",
    "openai",
    "anthropic",
    "google.generativeai",
    "dashscope",
]:
    if mod_name not in sys.modules:
        try:
            __import__(mod_name)
        except ImportError:
            sys.modules[mod_name] = _StubModule(mod_name)
