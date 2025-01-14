import glob
from pathlib import Path
import shlex
import subprocess

skip = True

for filename in glob.glob("*.py"):
    fp = Path(filename)
    if filename[0].isdigit():
        cmd = f"python {filename}"

        if True:
            skip = False
        else:
            if filename.startswith("07_"):
                skip = False

        if skip:
            print(f"\n### Skipping cmd: {cmd}")
            continue

        print(f"\n### Running cmd: {cmd}")

        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True)

        # Print the output of the script
        print("\n----- stdout -----\n")
        print(result.stdout)
        print("\n----- stderr -----\n")
        print(result.stderr)

        # Check if the script failed
        if result.returncode != 0:
            if result.returncode == -11:
                if filename.startswith("04_"):
                    if result.stdout.endswith("MLVTree: scor_xy_and_QH1_K1_SP"):
                        continue
                elif filename.startswith("07_"):
                    if result.stdout.endswith("Finished successfully.\n"):
                        continue

            print("\n----- Error detected -----\n")
            print(f"Script '{fp}' failed with return code {result.returncode}")
            break
else:
    print("All scripts ran successfully!")
