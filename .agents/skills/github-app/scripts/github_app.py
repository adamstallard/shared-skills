#!/usr/bin/env python3
"""Let an agent act on GitHub as its own GitHub App, with tokens that never need renewing by hand.

The long-lived credential is the App's private key. Installation tokens, which
last an hour, are minted from it on demand, cached per identity, and replaced
halfway through their life. Standard library only, plus the `openssl` command
for the RS256 signature.

Why it is built this way, and what was tried and rejected: ../DECISIONS.md.
"""

import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import fcntl
except ImportError:  # not on Windows, which this skill does not support
    fcntl = None

API = "https://api.github.com"
API_VERSION = "2022-11-28"
IDENTITY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
HELPER_KEY = "credential.https://github.com.helper"
# The repository settings wire replaces, and gives back on unwire.
SAVED = ("user.name", "user.email", "commit.gpgsign", "tag.gpgsign")
WIRED_MARK = "github-app.wired"


def saved_key(key):
    return "github-app.saved-" + key.replace(".", "-")
# What an App needs to push branches and open pull requests.
NEEDED = {"contents": "write", "pull_requests": "write"}


class Failure(Exception):
    """An error to report to the caller. `status` is GitHub's HTTP status, when there was one."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


# --- identity, config and credentials -------------------------------------------


def resolve_identity(arg, env=None):
    env = os.environ if env is None else env
    identity = arg or env.get("GITHUB_APP_IDENTITY") or "default"
    if not IDENTITY_RE.match(identity):
        raise Failure(f"identity {identity!r} may use only letters, digits, '_', '.' and '-'")
    return identity


def xdg_dir(kind, env=None):
    env = os.environ if env is None else env
    var, default = {"config": ("XDG_CONFIG_HOME", ".config"), "state": ("XDG_STATE_HOME", ".local/state")}[kind]
    base = env.get(var) or os.path.join(os.path.expanduser("~"), default)
    return os.path.join(base, "github-app")


def config_path(identity, env=None):
    return os.path.join(xdg_dir("config", env), identity + ".json")


def load_config(identity, env=None):
    path = config_path(identity, env)
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise Failure(f"cannot read {path}: {e}")
    if not isinstance(config, dict):
        raise Failure(f"{path} must hold a JSON object")
    return config


def default_key_path(identity, env=None):
    return os.path.join(xdg_dir("config", env), identity + ".pem")


def key_path(identity, config, env=None):
    """Where this identity's private key file is: the config's `keyFile`, else the default path."""
    configured = config.get("keyFile")
    if configured:
        return os.path.expanduser(str(configured))
    return default_key_path(identity, env)


def env_identity(env):
    """The one identity that the GITHUB_APP_* credentials in the environment belong to."""
    return env.get("GITHUB_APP_IDENTITY") or "default"


def env_credentials_set(env):
    return [k for k in ("GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_PRIVATE_KEY_FILE")
            if env.get(k, "").strip()]


def app_credentials(identity, config, env=None):
    """(app ID, private key bytes): the environment first, for its own identity only, then the config and key file."""
    env = os.environ if env is None else env
    present = env_credentials_set(env)
    if present and identity == env_identity(env):
        app_id = env.get("GITHUB_APP_ID", "").strip()
        key = env.get("GITHUB_APP_PRIVATE_KEY", "")
        key_file = env.get("GITHUB_APP_PRIVATE_KEY_FILE", "").strip()
        if not app_id or not (key.strip() or key_file):
            raise Failure("set GITHUB_APP_ID and one of GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_FILE, "
                          "or none of them")
        if key.strip() and key_file:
            raise Failure("set GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_FILE, not both")
        if "\n" not in key.strip():
            # An environment file can't hold a line break, so a key there is
            # usually written with "\n" escapes; turn them back into newlines.
            key = key.replace("\\n", "\n")
        return app_id, key.encode() if key.strip() else read_key(key_file)
    app_id = str(config.get("appId") or "").strip()
    path = key_path(identity, config, env)
    if app_id and os.path.exists(path):
        return app_id, read_key(path)
    if present:
        raise Failure(
            f"no App credentials for identity {identity!r}: GITHUB_APP_* is set in the environment, but it "
            f"belongs to identity {env_identity(env)!r} (GITHUB_APP_IDENTITY); set GITHUB_APP_IDENTITY={identity} "
            f"to use it for {identity!r}, or run 'github_app.py --identity {identity} store-credentials'")
    missing = "an appId in " + config_path(identity, env) if not app_id else "the key file " + path
    raise Failure(f"no App credentials for identity {identity!r}: {missing} is missing; "
                  f"run 'github_app.py --identity {identity} store-credentials', or set GITHUB_APP_ID and "
                  "GITHUB_APP_PRIVATE_KEY_FILE")


def read_key(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise Failure(f"cannot read the private key {path}: {e.strerror}")


# --- signing and HTTP ------------------------------------------------------------


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign(key, data, run=subprocess.run, which=shutil.which):
    """An RS256 signature of `data`, made by `openssl` from the key's bytes.

    The key goes to openssl as a file in a private temporary folder, never as an
    argument, and the folder is removed straight after.
    """
    if not which("openssl"):
        raise Failure("'openssl' is not on PATH; it signs the App's tokens")
    folder = tempfile.mkdtemp(prefix="github-app-")
    try:
        path = os.path.join(folder, "key.pem")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        result = run(["openssl", "dgst", "-sha256", "-sign", path], input=data, capture_output=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.decode(errors="replace").strip().splitlines()
        raise Failure("openssl could not sign with the App's private key"
                      + (f": {detail[-1]}" if detail else "") + "; is it the .pem file GitHub generated?")
    return result.stdout


def app_jwt(app_id, key, now, signer=sign):
    """A JSON Web Token proving to GitHub that we hold the App's key. GitHub allows 10 minutes; this asks for 9."""
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    # Issued a minute early, so a slightly fast clock here isn't refused as "issued in the future".
    claims = b64url(json.dumps({"iat": int(now) - 60, "exp": int(now) + 540, "iss": str(app_id)},
                               separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    return f"{header}.{claims}.{b64url(signer(key, signing_input))}"


def api(method, path, token, body=None, opener=urllib.request.urlopen):
    url = path if path.startswith("https://") else API + path
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
               "Authorization": "Bearer " + token, "User-Agent": "github-app-skill"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read() or b"{}").get("message") or e.reason
        except (ValueError, OSError):
            message = e.reason
        raise Failure(f"GitHub answered {e.code} to {method} {path}: {message}", status=e.code)
    except (urllib.error.URLError, OSError) as e:
        raise Failure(f"cannot reach GitHub: {getattr(e, 'reason', e)}")
    except ValueError:
        raise Failure("GitHub sent a response that is not JSON")


def parse_time(stamp):
    """Seconds since the epoch for GitHub's `2024-01-01T00:00:00Z` timestamps."""
    try:
        moment = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        raise Failure(f"GitHub sent an expiry time this script cannot read: {stamp!r}")
    return moment.replace(tzinfo=datetime.timezone.utc).timestamp()


def find_installation(jwt, config, env, opener=urllib.request.urlopen):
    """The installation to mint for: the configured ID, else the one on the configured owner, else the only one."""
    configured = str(config.get("installationId") or env.get("GITHUB_APP_INSTALLATION_ID", "")).strip()
    if configured:
        return configured
    owner = str(config.get("owner") or env.get("GITHUB_APP_OWNER", "")).strip()
    installations, page = [], 1
    while True:
        batch = api("GET", f"/app/installations?per_page=100&page={page}", jwt, opener=opener)
        if not isinstance(batch, list):
            raise Failure("GitHub's list of the App's installations was not a list")
        installations += batch
        if len(batch) < 100:
            break
        page += 1
    logins = [str((i.get("account") or {}).get("login", "")) for i in installations]
    if owner:
        for inst, login in zip(installations, logins):
            if login.lower() == owner.lower():
                return str(inst["id"])
        raise Failure(f"the App is not installed on {owner!r}; it is installed on: {', '.join(logins) or 'nothing'}. "
                      "Install it on that account, or fix 'owner' in the config")
    if len(installations) == 1:
        return str(installations[0]["id"])
    if not installations:
        raise Failure("the App is not installed anywhere yet; install it on the account that owns the repositories")
    raise Failure(f"the App is installed on several accounts ({', '.join(logins)}); "
                  "set 'owner' in the config to the one to act on")


# --- the token cache ---------------------------------------------------------------


def cache_path(identity, env=None):
    return os.path.join(xdg_dir("state", env), identity + ".json")


def read_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        return cached if isinstance(cached, dict) else {}
    except (OSError, ValueError):
        return {}


def write_cache(path, cached):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    os.replace(tmp, path)


def fingerprint(app_id, key, config, env):
    """Identifies what a token was minted from, without holding the key.

    A different App, key or installation makes the cached token unusable.
    """
    target = [str(config.get("installationId") or env.get("GITHUB_APP_INSTALLATION_ID", "")),
              str(config.get("owner") or env.get("GITHUB_APP_OWNER", "")).lower()]
    return hashlib.sha256(json.dumps([str(app_id), hashlib.sha256(key).hexdigest(), target]).encode()).hexdigest()


def usable(cached, credential, now):
    return cached.get("token") and cached.get("credential") == credential and now < cached.get("renewAt", 0)


def current_token(identity, config, env=None, now=None, opener=urllib.request.urlopen, signer=sign, refused=None):
    """An installation token in the first half of its life, minting a new one only when needed.

    Every process acting as this identity shares one cached token, under a lock,
    so they never mint over each other. `refused` is a token GitHub rejected: it
    is replaced, unless another process has already replaced it.
    """
    env = os.environ if env is None else env
    now = time.time() if now is None else now
    app_id, key = app_credentials(identity, config, env)
    credential = fingerprint(app_id, key, config, env)
    path = cache_path(identity, env)
    cached = read_cache(path)
    if refused is None and usable(cached, credential, now):
        return cached["token"], cached
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path + ".lock", "w") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        cached = read_cache(path)  # another process may have minted while we waited
        if usable(cached, credential, now) and cached.get("token") != refused:
            return cached["token"], cached
        jwt = app_jwt(app_id, key, now, signer)
        remembered = cached.get("installationId") if cached.get("credential") == credential else None
        installation = remembered or find_installation(jwt, config, env, opener)
        try:
            body = api("POST", f"/app/installations/{installation}/access_tokens", jwt, body={}, opener=opener)
        except Failure as e:
            if e.status != 404 or not remembered:
                raise
            # A reinstalled App has a new installation ID; look it up again once.
            installation = find_installation(jwt, config, env, opener)
            body = api("POST", f"/app/installations/{installation}/access_tokens", jwt, body={}, opener=opener)
        token = body.get("token")
        if not token:
            raise Failure("GitHub returned no installation token")
        expires_at = parse_time(body.get("expires_at"))
        # Renewed halfway through its life, so a process that keeps the token it
        # was handed still has at least half an hour left.
        cached = {"token": token, "credential": credential, "appId": str(app_id), "installationId": str(installation),
                  "permissions": body.get("permissions") or {},
                  "renewAt": int(now + (expires_at - now) / 2), "expiresAt": int(expires_at)}
        write_cache(path, cached)
    return token, cached


# --- who the App is ----------------------------------------------------------------


def bot_identity(slug, token, opener=urllib.request.urlopen):
    """The commit name and email GitHub shows as the App's bot user, with its avatar."""
    login = f"{slug}[bot]"
    user = api("GET", "/users/" + urllib.parse.quote(login), token, opener=opener)
    return login, f"{user['id']}+{login}@users.noreply.github.com"


def describe(identity, config, opener=urllib.request.urlopen, signer=sign, env=None):
    """The App's slug, bot name and email, and a valid token, for the commands that need all of them."""
    env = os.environ if env is None else env
    token, cached = current_token(identity, config, env, opener=opener, signer=signer)
    app_id, key = app_credentials(identity, config, env)
    app = api("GET", "/app", app_jwt(app_id, key, time.time(), signer), opener=opener)
    name, email = bot_identity(app["slug"], token, opener)
    return app, name, email, token, cached


# --- commands ----------------------------------------------------------------------


def cmd_token(args, config):
    token, _ = current_token(args.identity, config)
    return token


def cmd_check(args, config, opener=urllib.request.urlopen, signer=sign):
    app, name, email, token, cached = describe(args.identity, config, opener, signer)
    permissions = cached.get("permissions") or {}
    repos = api("GET", "/installation/repositories?per_page=100", token, opener=opener)
    names = sorted(r["full_name"] for r in repos.get("repositories", []))
    result = {
        "identity": args.identity,
        "app": app.get("slug"),
        "commitsAs": f"{name} <{email}>",
        "installationId": cached["installationId"],
        "permissions": permissions,
        "canPushAndOpenPullRequests": all(permissions.get(k) in ("write", "admin") for k in NEEDED),
        "repositories": repos.get("total_count", len(names)),
        "tokenMinutesLeft": max(0, int((cached["expiresAt"] - time.time()) // 60)),
    }
    if len(names) == repos.get("total_count", len(names)):
        result["repositoryNames"] = names
    wanted = config.get("repos") or []
    if wanted:
        missing = [r for r in wanted if r.lower() not in {n.lower() for n in names}]
        if missing and len(names) < repos.get("total_count", 0):
            # More than one page: ask about each missing one directly.
            missing = [r for r in missing if not repo_visible(r, token, opener)]
        if missing:
            result["warnings"] = [f"the App cannot reach {', '.join(missing)}; add them to its installation"]
    if not result["canPushAndOpenPullRequests"]:
        lacking = [f"{k}: write" for k in NEEDED if permissions.get(k) not in ("write", "admin")]
        result.setdefault("warnings", []).append(
            "the App's installation lacks " + ", ".join(lacking) + "; grant it in the App's settings, "
            "then accept the new permissions on the installation")
    return result


def repo_visible(full_name, token, opener):
    try:
        api("GET", "/repos/" + full_name, token, opener=opener)
        return True
    except Failure as e:
        if e.status in (403, 404):
            return False
        raise


def cmd_store_credentials(args, config, signer=sign):
    if not str(args.app_id).isdigit():
        raise Failure(f"--app-id must be the App's numeric ID, not {args.app_id!r}")
    source = os.path.expanduser(args.key_file)
    key = read_key(source)
    signer(key, b"check")  # refuse a file that is not a usable private key, before storing anything
    target = key_path(args.identity, config)
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    if os.path.abspath(source) != os.path.abspath(target):
        tmp = target + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        os.replace(tmp, target)
    os.chmod(target, 0o600)
    updated = dict(config, appId=str(args.app_id))
    if args.owner:
        updated["owner"] = args.owner
    path = config_path(args.identity)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    stored = {"identity": args.identity, "stored": True, "keyFile": target, "config": path}
    warnings = []
    if os.path.abspath(source) != os.path.abspath(target):
        warnings.append(f"the key is now copied to {target}; delete {source}")
    if env_credentials_set(os.environ) and args.identity == env_identity(os.environ):
        warnings.append("GITHUB_APP_* in the environment overrides the stored key for this identity; "
                        "unset it for the stored key to take effect")
    if warnings:
        stored["warnings"] = warnings
    return stored


def script_command(identity, *rest, python=None, script=None):
    python = python or sys.executable
    script = script or os.path.abspath(__file__)
    return " ".join(shlex.quote(p) for p in (python, script, "--identity", identity, *rest))


def git(repo, *args, run=subprocess.run):
    return run(["git", "-C", repo, *args], capture_output=True, text=True)


def repo_root(path, run=subprocess.run):
    result = git(path, "rev-parse", "--show-toplevel", run=run)
    if result.returncode != 0:
        raise Failure(f"{path!r} is not inside a git repository")
    return result.stdout.strip()


def cmd_wire(args, config, run=subprocess.run, opener=urllib.request.urlopen, signer=sign):
    repo = repo_root(os.path.abspath(args.repo or "."), run)
    app, name, email, _, _ = describe(args.identity, config, opener, signer)

    def setting(*a):
        result = git(repo, "config", "--local", *a, run=run)
        if result.returncode != 0:
            raise Failure(f"git config failed in {repo}: {result.stderr.strip()}")

    # The first wire keeps the repository's own values, such as a work email,
    # so unwire can put them back; a rewire must not save the bot's as theirs.
    if git(repo, "config", "--local", "--get", WIRED_MARK, run=run).returncode != 0:
        for key in SAVED:
            own = git(repo, "config", "--local", "--get", key, run=run)
            if own.returncode == 0:
                setting(saved_key(key), own.stdout.rstrip("\n"))
        setting(WIRED_MARK, args.identity)
    git(repo, "config", "--local", "--unset-all", HELPER_KEY, run=run)
    # The empty value first clears helpers from the global config, such as the
    # macOS keychain, for github.com in this repository only.
    setting("--add", HELPER_KEY, "")
    setting("--add", HELPER_KEY, "!" + script_command(args.identity, "credential"))
    setting("user.name", name)
    setting("user.email", email)
    # A person who signs every commit would otherwise sign the App's with their own key.
    setting("commit.gpgsign", "false")
    setting("tag.gpgsign", "false")
    wired ={"identity": args.identity, "repo": repo, "app": app.get("slug"), "commitsAs": f"{name} <{email}>"}
    remote = git(repo, "remote", "get-url", "origin", run=run)
    url = remote.stdout.strip() if remote.returncode == 0 else ""
    if url and not url.startswith("https://"):
        wired["warnings"] = [f"origin is {url}, which pushes with your SSH key, not the App; run "
                             "'git remote set-url origin https://github.com/<owner>/<repo>.git' in " + repo]
    return wired


def cmd_unwire(args, config, run=subprocess.run):
    repo = repo_root(os.path.abspath(args.repo or "."), run)
    git(repo, "config", "--local", "--unset-all", HELPER_KEY, run=run)
    for key in SAVED:
        git(repo, "config", "--local", "--unset-all", key, run=run)
        own = git(repo, "config", "--local", "--get", saved_key(key), run=run)
        if own.returncode == 0:
            git(repo, "config", "--local", key, own.stdout.rstrip("\n"), run=run)
            git(repo, "config", "--local", "--unset-all", saved_key(key), run=run)
    git(repo, "config", "--local", "--unset-all", WIRED_MARK, run=run)
    return {"identity": args.identity, "repo": repo, "unwired": True}


def cmd_env(args, config, opener=urllib.request.urlopen, signer=sign):
    """Environment lines for a server role's environment file: git identity and helper, no secrets."""
    app, name, email, _, _ = describe(args.identity, config, opener, signer)
    lines = [
        f"GITHUB_APP_IDENTITY={args.identity}",
        f"GIT_AUTHOR_NAME={name}", f"GIT_AUTHOR_EMAIL={email}",
        f"GIT_COMMITTER_NAME={name}", f"GIT_COMMITTER_EMAIL={email}",
        # Config passed this way outranks every config file, for this process only.
        "GIT_CONFIG_COUNT=4",
        f"GIT_CONFIG_KEY_0={HELPER_KEY}", "GIT_CONFIG_VALUE_0=",
        f"GIT_CONFIG_KEY_1={HELPER_KEY}", "GIT_CONFIG_VALUE_1=!" + script_command(args.identity, "credential"),
        # Never the account's own signing key on the App's commits.
        "GIT_CONFIG_KEY_2=commit.gpgsign", "GIT_CONFIG_VALUE_2=false",
        "GIT_CONFIG_KEY_3=tag.gpgsign", "GIT_CONFIG_VALUE_3=false",
    ]
    return "\n".join(lines)


def cmd_credential(args, config, stdin=None):
    """git's credential-helper protocol: answer `get` for https://github.com, ignore the rest."""
    if args.operation == "erase":
        # git says the token it was given was refused; mint a fresh one next time.
        try:
            os.remove(cache_path(args.identity))
        except FileNotFoundError:
            pass
        return ""
    if args.operation != "get":
        return ""
    fields = {}
    for line in (stdin or sys.stdin).read().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            fields[k] = v
    if fields.get("protocol") != "https" or fields.get("host") != "github.com":
        return ""
    token, _ = current_token(args.identity, config)
    return f"username=x-access-token\npassword={token}"


def cmd_gh(args, config, execvpe=None, which=None):
    """Run `gh` as the App: GH_TOKEN set for that one process, never exported."""
    execvpe = execvpe or os.execvpe  # looked up now, so a stub of os.execvpe applies
    which = which or shutil.which
    if not which("gh"):
        raise Failure("'gh' is not on PATH")
    token, _ = current_token(args.identity, config)
    env = dict(os.environ, GH_TOKEN=token)
    env.pop("GITHUB_TOKEN", None)  # gh prefers GH_TOKEN, but a stray one should not confuse anyone reading env
    gh_args = args.gh_args[1:] if args.gh_args[:1] == ["--"] else args.gh_args
    execvpe("gh", ["gh", *gh_args], env)
    return ""


def cmd_forget(args, config):
    forgotten = {"identity": args.identity, "forgotten": True}
    warnings = []
    if config.get("keyFile"):  # a file the user placed and pointed at, which forget leaves alone
        forgotten["keptKeyFile"] = os.path.expanduser(str(config["keyFile"]))
    else:
        path = default_key_path(args.identity)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            warnings.append(f"could not delete the key file {path}: {e.strerror}")
    state = cache_path(args.identity)
    for p in (state, state + ".lock"):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    env = os.environ
    present = env_credentials_set(env)
    if present and args.identity == env_identity(env):
        warnings.append("GITHUB_APP_* is still set in the environment, so this identity keeps working from it; "
                        "unset " + ", ".join(present))
    if "keptKeyFile" in forgotten and os.path.exists(forgotten["keptKeyFile"]) and config.get("appId"):
        warnings.append(f"this identity still works from {forgotten['keptKeyFile']}, which forget keeps")
    warnings.append("repositories wired with 'wire' still point at this identity; run 'unwire' in each")
    forgotten["warnings"] = warnings
    return forgotten


# --- command line ------------------------------------------------------------------


def parser():
    p = argparse.ArgumentParser(prog="github_app.py", description="Act on GitHub as a GitHub App.")
    p.add_argument("--identity", help="which App to act as (default: $GITHUB_APP_IDENTITY, else 'default')")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("token", help="print a valid installation token, minting one if needed")
    sub.add_parser("check", help="show which App and installation this is, and what it may do")
    s = sub.add_parser("store-credentials", help="store the App's ID and a copy of its private key")
    s.add_argument("--app-id", required=True, help="the App's numeric ID, from its settings page")
    s.add_argument("--key-file", required=True, help="the .pem file GitHub generated")
    s.add_argument("--owner", help="the account the App is installed on, if it is installed on several")
    w = sub.add_parser("wire", help="make git in one repository push and commit as the App")
    w.add_argument("--repo", help="the repository to wire (default: the one this folder is in)")
    u = sub.add_parser("unwire", help="undo 'wire' in one repository")
    u.add_argument("--repo", help="the repository to unwire (default: the one this folder is in)")
    sub.add_parser("env", help="print environment lines that wire git for a server process")
    c = sub.add_parser("credential", help="git credential helper; git runs this itself")
    c.add_argument("operation", choices=["get", "store", "erase"])
    sub.add_parser("gh", help="run gh as the App, e.g. 'gh pr create ...'; everything after 'gh' goes to gh")
    sub.add_parser("forget", help="delete this identity's stored key and cached token")
    return p


COMMANDS = {
    "token": cmd_token,
    "check": cmd_check,
    "store-credentials": cmd_store_credentials,
    "wire": cmd_wire,
    "unwire": cmd_unwire,
    "env": cmd_env,
    "credential": cmd_credential,
    "gh": cmd_gh,
    "forget": cmd_forget,
}
RAW_OUTPUT = {"token", "env", "credential", "gh"}  # printed bare, for $(...), env files, git and gh


def split_gh(argv):
    """The command line up to and including `gh`, and gh's own arguments after it.

    argparse can't pass on arguments that begin with an option, such as
    `gh -R owner/repo pr list`, so everything after `gh` skips it.
    """
    i = 0
    while i < len(argv):
        if argv[i] == "--identity":
            i += 2
        elif argv[i].startswith("--identity="):
            i += 1
        elif argv[i] == "gh":
            return argv[:i + 1], argv[i + 1:]
        else:
            break
    return argv, []


def main(argv=None):
    head, gh_args = split_gh(sys.argv[1:] if argv is None else list(argv))
    args = parser().parse_args(head)
    args.gh_args = gh_args
    try:
        args.identity = resolve_identity(args.identity)
        result = COMMANDS[args.command](args, load_config(args.identity))
    except Failure as e:
        if args.command in RAW_OUTPUT:
            print(f"github_app: {e}", file=sys.stderr)
        else:
            print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    except Exception as e:  # callers parse stdout, so even a bug answers predictably
        import traceback
        traceback.print_exc()
        if args.command not in RAW_OUTPUT:
            print(json.dumps({"ok": False, "error": f"unexpected error: {e!r}"}))
        return 1
    if args.command in RAW_OUTPUT:
        if result:
            print(result)
    else:
        print(json.dumps({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
