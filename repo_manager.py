#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path


# --------------------------------------------------------
# Detect SCRIPT_DIR and ROOT_DIR
# --------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent        # /project-root/repo-manager
ROOT_DIR = SCRIPT_DIR.parent                        # /project-root

SEARCH_DIRS = [
    ROOT_DIR / "Extensions",
    ROOT_DIR / "Modules"
]

# -----------------------------------
# Colors
# -----------------------------------
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"


# -----------------------------------
# .env Loader (from SCRIPT_DIR)
# -----------------------------------
def load_env():
    env_path = SCRIPT_DIR / ".env"

    values = {}

    if not env_path.exists():
        return values

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, val = line.split("=", 1)
            values[key.strip()] = os.path.expanduser(val.strip())

    return values


ENV = load_env()
SSH_KEY = ENV.get("SSH_KEY")


# -----------------------------------
# Helpers
# -----------------------------------
def run(cmd, cwd=None):
    r = subprocess.run(
        cmd, cwd=cwd, shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True, executable="/bin/bash"
    )
    return r.stdout


def get_repos():
    repos = []
    for base in SEARCH_DIRS:
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            if ".git" in dirs:
                repos.append(Path(root))
    return repos


def is_clean(repo):
    """
    Only real modifications count as dirty.
    Untracked files (??) are ignored.
    """
    status_lines = run("git status --porcelain", cwd=repo).strip().splitlines()

    for line in status_lines:
        if line.startswith("??"):
            continue
        return False  # real change exists

    return True


def load_ssh():
    if not SSH_KEY:
        print(f"{C.RED}[ERROR]{C.RESET}   No SSH_KEY found in repo-manager/.env")
        return

    print(f"{C.YELLOW}[KEY]{C.RESET}    Using SSH key: {SSH_KEY}")
    subprocess.run("eval $(ssh-agent -s)", shell=True)
    subprocess.run(f"ssh-add '{SSH_KEY}'", shell=True)


def fetch(repo):
    out = run("git fetch --all --prune", cwd=repo)
    if "Permission denied" in out:
        load_ssh()
        run("git fetch --all --prune", cwd=repo)


def git_stash(repo):
    run("git stash push -u -m 'auto-stash via repo_manager --force'", cwd=repo)


def default_branch(repo):
    out = run("git remote show origin", cwd=repo)
    for line in out.splitlines():
        if "HEAD branch" in line:
            return line.split(":")[1].strip()
    return None


def checkout(repo, branch):
    return run(f"git checkout {branch}", cwd=repo)


def pull(repo):
    return run("git pull --ff-only", cwd=repo)


# -----------------------------------
# Main logic
# -----------------------------------
def process(latest=False, force=False):
    repos = get_repos()
    total = len(repos)

    print(f"{C.BOLD}{C.CYAN}Processing {total} repositories…{C.RESET}")

    for i, repo in enumerate(repos, start=1):
        rel = str(repo.relative_to(ROOT_DIR))
        counter = f"[{i}/{total}]"

        clean = is_clean(repo)

        # --------------------------------------------------
        # FORCE MODE
        # --------------------------------------------------
        if force and not clean:
            git_stash(repo)
            fetch(repo)
            pull(repo)
            print(f"{counter:<8}{C.MAGENTA}[FORCE]{C.RESET}  {rel:<50} (stash + pull)")
            continue

        # --------------------------------------------------
        # Not clean -> skip
        # --------------------------------------------------
        if not clean:
            print(f"{counter:<8}{C.RED}[SKIP]{C.RESET}   {rel:<50} (uncommitted)")
            continue

        # --------------------------------------------------
        # LATEST MODE
        # --------------------------------------------------
        if latest:
            fetch(repo)

            br = default_branch(repo)
            if not br:
                print(f"{counter:<8}{C.RED}[SKIP]{C.RESET}   {rel:<50} (no default branch)")
                continue

            co = checkout(repo, br)
            if "error" in co.lower() or "fatal" in co.lower():
                print(f"{counter:<8}{C.RED}[SKIP]{C.RESET}   {rel:<50} (checkout failed)")
                continue

            pl = pull(repo)
            if "error" in pl.lower() or "fatal" in pl.lower():
                print(f"{counter:<8}{C.RED}[SKIP]{C.RESET}   {rel:<50} (pull failed)")
                continue

            print(f"{counter:<8}{C.GREEN}[OK]{C.RESET}     {rel:<50} (latest: {br})")
            continue

        # --------------------------------------------------
        # Normal clean pull
        # --------------------------------------------------
        fetch(repo)
        pull(repo)
        print(f"{counter:<8}{C.GREEN}[OK]{C.RESET}     {rel:<50} (pull)")


# -----------------------------------
# Help
# -----------------------------------
def help():
    print(f"""
{C.BOLD}{C.CYAN}Repo Manager CLI{C.RESET}
---------------------------------------

{C.BOLD}{C.YELLOW}IMPORTANT:{C.RESET}
  This program must be executed inside the folder:
      {C.CYAN}repo-manager/{C.RESET}

  Directory structure must be:

      project-root/
        ├── Extensions/
        ├── Modules/
        ├── repo-manager/
        │     ├── repo_manager.py
        │     └── .env   <── SSH key is configured here

  Your .env file must contain:
      SSH_KEY=/path/to/private/key


{C.BOLD}{C.YELLOW}Commands:{C.RESET}

  {C.GREEN}--pull{C.RESET}
        Fetch + pull all clean repositories.

  {C.GREEN}--pull --force{C.RESET}
        Stash real changes (NOT untracked files), then fetch + pull.

  {C.GREEN}--latest{C.RESET}
        Fetch → detect default branch → checkout → pull.

  {C.GREEN}--help{C.RESET}
        Show this help page.
""")


# -----------------------------------
# Entry point
# -----------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        help()
        exit(0)

    args = sys.argv[1:]

    latest = "--latest" in args
    force = "--force" in args

    if "--pull" in args:
        process(latest=False, force=force)
    elif "--latest" in args:
        process(latest=True, force=False)
    else:
        help()
