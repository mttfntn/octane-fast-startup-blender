"""Build the release zip: dist/octane-fast-start-<version>.zip

Usage:  python tools/build.py [--expect-version X.Y.Z]
The version is read from __version__ in startup/octane_fast_start.py.
--expect-version makes the build fail if it differs (used by the release
workflow to check the git tag against the code).

The zip contains one folder, octane-fast-start/, holding the startup script,
check.py, README.md and LICENSE. That folder can be added to Blender's
Preferences > File Paths > Script Directories as it is. Handover/agent notes,
tests and CI files are left out on purpose.
"""
import ast
import os
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["startup/octane_fast_start.py", "check.py", "README.md", "LICENSE"]
TOP = "octane-fast-start"


def read_version():
    path = os.path.join(REPO, "startup", "octane_fast_start.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "__version__" for t in node.targets):
            return node.value.value
    raise SystemExit("__version__ not found in " + path)


def main():
    version = read_version()
    if "--expect-version" in sys.argv:
        expected = sys.argv[sys.argv.index("--expect-version") + 1].lstrip("v")
        if expected != version:
            raise SystemExit(f"tag v{expected} does not match __version__ {version}")
    out_dir = os.path.join(REPO, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"octane-fast-start-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in FILES:
            z.write(os.path.join(REPO, rel), f"{TOP}/{rel}")
    print(out)


if __name__ == "__main__":
    main()
