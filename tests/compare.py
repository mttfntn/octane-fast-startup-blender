"""Compare the behaviour of two versions of octane_fast_start.py.

Usage:
    python tests/compare.py OLD.py NEW.py [--runs N]
    python tests/compare.py --git REV           (REV's script vs the working copy)
Runs every scenario in scenarios.py N times (default 2) against each file and
prints, per scenario, whether the traces match. Traces of the same file are
also compared with each other, to tell real differences from noise.
Exit code 0 only if every scenario matches or is listed in EXPECTED.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from scenarios import SCENARIOS  # noqa: E402

# Differences that are intended, with the reason.
EXPECTED = {
    "custom_port_online": "bug fix: the old version ignored the port set in Octane's preferences",
}


def trace(path, name):
    p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "scenarios.py"), path, name],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        return {"crash": p.stderr.strip().splitlines()[-1:]}
    return json.loads(p.stdout.strip().splitlines()[-1])


def main():
    args = sys.argv[1:]
    runs = 2
    if "--runs" in args:
        i = args.index("--runs")
        runs = int(args[i + 1])
        del args[i:i + 2]
    if args[0] == "--git":
        repo = os.path.dirname(HERE)
        rel = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", args[1]],
                             capture_output=True, text=True, check=True).stdout.split()
        rel = next(f for f in rel if f.endswith("octane_fast_start.py"))
        old_src = subprocess.run(["git", "-C", repo, "show", f"{args[1]}:{rel}"],
                                 capture_output=True, text=True, check=True).stdout
        tmp = tempfile.NamedTemporaryFile("w", suffix="_old.py", delete=False, encoding="utf-8")
        tmp.write(old_src)
        tmp.close()
        old, new = tmp.name, os.path.join(repo, "startup", "octane_fast_start.py")
    else:
        old, new = args[0], args[1]

    failed = False
    for name in SCENARIOS:
        olds = [trace(old, name) for _ in range(runs)]
        news = [trace(new, name) for _ in range(runs)]
        noise = any(t != olds[0] for t in olds) or any(t != news[0] for t in news)
        if "skip" in olds[0]:
            status = "SKIPPED (" + olds[0]["skip"] + ")"
        elif olds[0] == news[0] and not noise:
            status = "same"
        elif name in EXPECTED:
            status = "DIFFERENT - expected: " + EXPECTED[name]
        else:
            status = "DIFFERENT" + (" (runs of the same file differ: noise?)" if noise else "")
            failed = True
        print(f"{name:22} {status}")
        if olds[0] != news[0]:
            for key in sorted(set(olds[0]) | set(news[0])):
                if olds[0].get(key) != news[0].get(key):
                    print(f"    {key}:\n      old {olds[0].get(key)}\n      new {news[0].get(key)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
