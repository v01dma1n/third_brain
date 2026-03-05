import re
import os

VERSION_FILE = "src/telegram_listener.py" # Update this to your primary script path

def increment_version():
    if not os.path.exists(VERSION_FILE):
        return

    with open(VERSION_FILE, "r") as f:
        content = f.read()

    # Look for __version__ = "x.y.z"
    pattern = r'__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"'
    match = re.search(pattern, content)

    if match:
        major, minor, patch = match.groups()
        new_patch = int(patch) + 1
        new_version = f'{major}.{minor}.{new_patch}'
        
        new_content = re.sub(pattern, f'__version__ = "{new_version}"', content)
        
        with open(VERSION_FILE, "w") as f:
            f.write(new_content)
        
        # Add the modified file back to the git index
        os.system(f"git add {VERSION_FILE}")
        print(f"Version bumped to {new_version}")

if __name__ == "__main__":
    increment_version()