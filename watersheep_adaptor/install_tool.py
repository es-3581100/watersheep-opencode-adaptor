"""Install the packaged custom tool into a chosen project without overwriting."""
import argparse
from importlib import resources
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".", help="existing project directory")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    if not project.is_dir():
        parser.error("project must be an existing directory")
    target = project / ".opencode" / "tools" / "watersheep_decide.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as output:
            output.write(resources.files("watersheep_adaptor").joinpath("watersheep_decide.ts").read_text(encoding="utf-8"))
    except FileExistsError:
        parser.error("tool already exists: %s" % target)
    print(target)
    return 0
