# Types for handbacks.py, which is untyped; only the names code under the
# strict check of .agents/pyrightconfig.json uses. Kept by whoever builds the
# shared post reader (post_reader.py).

def forget_scripts(texts: list[str], scripts: set[str]) -> None: ...
