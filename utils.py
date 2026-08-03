import subprocess


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