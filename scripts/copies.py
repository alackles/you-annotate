"""Make and update instructor copies: one Fly app per instructor, running this same code.

    .venv/bin/python scripts/copies.py create smith --name "Dr. Smith" --passcode equiano
    .venv/bin/python scripts/copies.py deploy smith [--tag release-2026-11-05]
    .venv/bin/python scripts/copies.py footnotes [smith ...]     # default: every copy
    .venv/bin/python scripts/copies.py secrets smith [...]       # after editing copies/smith.env

`footnotes` adds footnotes that are new on the live site to the copies; ones a copy already
has are skipped. It only adds: a footnote edited on the live site arrives as a second note
beside the old one, and one deleted there stays in the copies.

`create` makes the app you-annotate-<copy> with its own volume and secrets, deploys a release
tag to it, uploads texts/equiano.md, and copies the footnotes (only the footnotes) from the
live site's export. Each step is skipped if already done, so a failed run can be re-run.
It ends by printing a card to send the instructor.

The instructor code is that app's ADMIN_PASSWORD. Codes live in copies/<copy>.env (gitignored)
and are never regenerated, which would lock the instructor out. The live values are Fly
secrets, which `deploy` doesn't touch: after editing ADMIN_NAME or ADMIN_PASSWORD in the
file, run `copies.py secrets <copy>` to send them to Fly.

Copies deploy from a release tag (`git tag release-YYYY-MM-DD`; the newest is the default) via
a temporary git worktree, so uncommitted local changes never reach a colleague's copy.
"""

import argparse
import json
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parent.parent
COPIES = REPO / "copies"
ORG, REGION = "personal", "ord"
SOURCE = "https://you-annotate.fly.dev"
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no i, l, o, 0, 1


def footnotes_only(export: dict) -> dict:
    """The export with every annotation but footnotes removed, and no links. Other layers are
    the class's own work and must not reach another instructor's copy."""
    return {**export, "annotations": [a for a in export["annotations"] if a["layer"] == "footnote"],
            "links": []}


def instructor_code() -> str:
    return "-".join("".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(3))


def fly(*args, input=None, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["fly", *args], input=input, text=True, capture_output=True, check=check)


def sh(*args, cwd=REPO) -> str:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


def say(msg: str) -> None:
    print(f"• {msg}", flush=True)


# --- copies/<copy>.env ------------------------------------------------------------------

def env_path(copy: str) -> Path:
    return COPIES / f"{copy}.env"


def read_env(copy: str) -> dict:
    return dict(dotenv_values(env_path(copy))) if env_path(copy).exists() else {}


def write_env(copy: str, env: dict) -> None:
    COPIES.mkdir(exist_ok=True)
    lines = [f'{k}="{v}"' for k, v in env.items()]
    env_path(copy).write_text("\n".join(lines) + "\n")


# --- steps ------------------------------------------------------------------------------

def newest_release() -> str:
    tags = sh("git", "tag", "--list", "release-*", "--sort=-creatordate").split()
    if not tags:
        sys.exit("No release tag yet. Make one from main: git tag release-$(date +%F)")
    return tags[0]


def ensure_app(app: str) -> None:
    if fly("status", "--app", app, check=False).returncode == 0:
        say(f"app {app} exists")
        return
    r = fly("apps", "create", app, "--org", ORG, check=False)
    if r.returncode != 0:
        sys.exit(f"Couldn't create {app} (is the name taken?):\n{r.stderr.strip()}")
    say(f"created app {app}")


def ensure_volume(app: str) -> None:
    if any(v["name"] == "data" for v in json.loads(fly("volumes", "list", "--app", app, "--json").stdout)):
        say("volume exists")
        return
    fly("volumes", "create", "data", "--app", app, "--region", REGION, "--size", "1", "--yes")
    say("created volume")


def ensure_secrets(copy: str, app: str, name: str, passcode: str) -> dict:
    env = read_env(copy)
    if env.get("ADMIN_PASSWORD"):
        say(f"secrets already recorded in {env_path(copy).relative_to(REPO)}")
        return env
    env = {"APP": app, "URL": f"https://{app}.fly.dev", "ADMIN_NAME": name,
           "ADMIN_PASSWORD": instructor_code(), "PASSCODE": passcode, "TAG": ""}
    write_env(copy, env)  # before setting them on Fly, so a code that's live is never lost
    stdin = "".join(f"{k}={v}\n" for k, v in [("ADMIN_PASSWORD", env["ADMIN_PASSWORD"]),
                                               ("ADMIN_NAME", name),
                                               ("SECRET_KEY", secrets.token_hex(32))])
    fly("secrets", "import", "--stage", "--app", app, input=stdin)
    say(f"set secrets; recorded in {env_path(copy).relative_to(REPO)}")
    return env


def deploy(copy: str, app: str, tag: str) -> None:
    say(f"deploying {tag} to {app} (a few minutes)")
    tree = Path(tempfile.mkdtemp(prefix="you-annotate-deploy-")) / "tree"
    sh("git", "worktree", "add", "--detach", str(tree), tag)
    try:
        r = subprocess.run(["fly", "deploy", "--app", app, "--ha=false"], cwd=tree, text=True)
        if r.returncode != 0:
            sys.exit("fly deploy failed (output above)")
    finally:
        sh("git", "worktree", "remove", "--force", str(tree))
        shutil.rmtree(tree.parent, ignore_errors=True)
    write_env(copy, {**read_env(copy), "TAG": tag})


def wait_until_up(c: httpx.Client) -> None:
    for _ in range(60):
        try:
            if c.get("/api/texts").status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(2)
    sys.exit(f"{c.base_url} didn't come up")


def ensure_text(c: httpx.Client, slug: str, title: str, passcode: str, file: Path) -> None:
    r = c.post("/api/admin/texts", files={"file": (file.name, file.read_bytes())},
               data={"title": title, "slug": slug, "passcode": passcode})
    if r.status_code == 409:
        say(f"text '{slug}' already uploaded")
        return
    r.raise_for_status()
    say(f"uploaded '{title}' ({r.json()['chapters']} chapters)")


def copy_footnotes(c: httpx.Client, slug: str, export: dict) -> int:
    data = footnotes_only(export)
    preview = c.post(f"/api/admin/texts/{slug}/restore", json=data).raise_for_status().json()
    if preview["annotations"]["unplaced"]:
        print("\n".join(preview["problems"]))
        sys.exit("Some footnotes don't fit the uploaded text (listed above); nothing was restored. "
                 "Is texts/equiano.md the same file the live site was made from?")
    c.post(f"/api/admin/texts/{slug}/restore?apply=true", json=data).raise_for_status()
    n = preview["annotations"]
    say(f"footnotes: {n['exact'] + n['moved']} added, {n['duplicate']} already there")
    return len(data["annotations"])


def card(env: dict, slug: str, title: str) -> str:
    url = env["URL"]
    return f"""
Your copy of {title}

  Reading page:      {url}/t/{slug}
  Admin page:        {url}/admin
  Instructor code:   {env['ADMIN_PASSWORD']}
  Student passcode:  {env['PASSCODE']}

Students open the reading page and join with their name and the student passcode.
Anyone with the link can read (but not annotate) without it. Log in on the admin page
with the instructor code to change the student passcode, upload other texts, and edit or
delete any annotation; logged in, your annotations show as {env['ADMIN_NAME']!r}.
"""


# --- commands ---------------------------------------------------------------------------

def create(args) -> None:
    app = f"you-annotate-{args.copy}"
    tag = args.tag or newest_release()
    ensure_app(app)
    ensure_volume(app)
    env = ensure_secrets(args.copy, app, args.name, args.passcode)
    if env.get("TAG") == tag and not args.redeploy:
        say(f"already running {tag}")
    else:
        deploy(args.copy, app, tag)

    with httpx.Client(base_url=args.source, timeout=60) as src:
        title = src.get(f"/api/texts/{args.slug}").raise_for_status().json()["title"]
        export = src.get(f"/api/texts/{args.slug}/export").raise_for_status().json()
    with httpx.Client(base_url=env["URL"], timeout=60) as c:
        wait_until_up(c)
        c.post("/api/admin/login", json={"password": env["ADMIN_PASSWORD"]}).raise_for_status()
        ensure_text(c, args.slug, title, env["PASSCODE"], args.file)
        copy_footnotes(c, args.slug, export)
        c.post("/api/admin/logout")
    print(card(read_env(args.copy), args.slug, title))


def deploy_cmd(args) -> None:
    env = read_env(args.copy)
    if not env:
        sys.exit(f"No {env_path(args.copy).relative_to(REPO)}; make the copy with `create` first.")
    deploy(args.copy, env["APP"], args.tag or newest_release())


def footnotes_cmd(args) -> None:
    names = args.copies or sorted(p.stem for p in COPIES.glob("*.env"))
    if not names:
        sys.exit("No copies yet.")
    with httpx.Client(base_url=args.source, timeout=60) as src:
        export = src.get(f"/api/texts/{args.slug}/export").raise_for_status().json()
    for name in names:
        env = read_env(name)
        if not env:
            sys.exit(f"No {env_path(name).relative_to(REPO)}")
        print(f"{name}:")
        with httpx.Client(base_url=env["URL"], timeout=60) as c:
            wait_until_up(c)
            c.post("/api/admin/login", json={"password": env["ADMIN_PASSWORD"]}).raise_for_status()
            copy_footnotes(c, args.slug, export)
            c.post("/api/admin/logout")


def secrets_cmd(args) -> None:
    for name in args.copies:
        env = read_env(name)
        if not env:
            sys.exit(f"No {env_path(name).relative_to(REPO)}")
        stdin = f"ADMIN_NAME={env['ADMIN_NAME']}\nADMIN_PASSWORD={env['ADMIN_PASSWORD']}\n"
        fly("secrets", "import", "--app", env["APP"], input=stdin)  # restarts the machine
        with httpx.Client(base_url=env["URL"], timeout=60) as c:
            wait_until_up(c)
            if c.post("/api/admin/login", json={"password": env["ADMIN_PASSWORD"]}).status_code != 200:
                sys.exit(f"{name}: secrets set, but the password from the file doesn't log in")
            say(f"{name}: logs in with the file's password, shows as {c.get('/api/admin/me').json()['name']!r}")
            c.post("/api/admin/logout")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(required=True)

    c = sub.add_parser("create", help="make a copy (or finish a half-made one)")
    c.add_argument("copy", help="short lowercase name, e.g. smith -> you-annotate-smith")
    c.add_argument("--name", required=True, help="instructor's name as shown on their annotations")
    c.add_argument("--passcode", required=True, help="the students' passcode")
    c.add_argument("--tag", help="release tag to deploy (default: newest release-*)")
    c.add_argument("--redeploy", action="store_true", help="deploy even if already on that tag")
    c.add_argument("--source", default=SOURCE, help="site to copy the text's title and footnotes from")
    c.add_argument("--slug", default="equiano")
    c.add_argument("--file", type=Path, default=REPO / "texts" / "equiano.md")
    c.set_defaults(func=create)

    d = sub.add_parser("deploy", help="deploy a release tag to an existing copy")
    d.add_argument("copy")
    d.add_argument("--tag", help="release tag to deploy (default: newest release-*)")
    d.set_defaults(func=deploy_cmd)

    f = sub.add_parser("footnotes", help="add footnotes that are new on the live site to copies")
    f.add_argument("copies", nargs="*", help="which copies (default: all in copies/)")
    f.add_argument("--source", default=SOURCE)
    f.add_argument("--slug", default="equiano")
    f.set_defaults(func=footnotes_cmd)

    s = sub.add_parser("secrets", help="send ADMIN_NAME and ADMIN_PASSWORD from copies/<copy>.env to Fly")
    s.add_argument("copies", nargs="+", help="which copies (restarts each one)")
    s.set_defaults(func=secrets_cmd)

    args = ap.parse_args()
    for name in args.copies if hasattr(args, "copies") else [args.copy]:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
            sys.exit("Copy name: lowercase letters, digits and dashes")
    args.func(args)


if __name__ == "__main__":
    main()
