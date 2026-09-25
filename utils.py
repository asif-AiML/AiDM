import subprocess
import re


def run_command(command: list[str]) -> int:
    print("\nRunning:")
    print(" ".join(command))
    print()

    try:
        return subprocess.run(command).returncode

    except FileNotFoundError:
        print(f"Error: '{command[0]}' is not installed or not in PATH.")
        return 127

    except KeyboardInterrupt:
        print("\nDownload cancelled.")
        return 130




def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" ._")

    return name or "AIDM_Stream"