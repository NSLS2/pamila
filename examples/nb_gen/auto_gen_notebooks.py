import glob
from pathlib import Path
import shlex
from subprocess import PIPE, Popen

for filename in glob.glob("*.py"):
    fp = Path(filename)
    if filename[0].isdigit():
        cmd = f"jupytext --to notebook {filename} --update -o ../{fp.stem}.ipynb"
        # print(cmd)
        p = Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE, encoding="utf-8")
        out, err = p.communicate()
        print(out)
        if err:
            print(f"\n## ERROR ##: {err}\n")


print("Finished converting all notebooks")
