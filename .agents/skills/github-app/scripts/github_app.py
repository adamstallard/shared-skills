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
import contextlib
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
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
WIRED_KEY = "GITHUB_APP_WIRED"  # wire's record, in the env it wrote
# What an App needs to push branches and open pull requests.
NEEDED = {"contents": "write", "pull_requests": "write"}


class Failure(Exception):
    """An error to report to the caller. `status` is GitHub's HTTP status, when there was one."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


# --- identity, config and credentials -------------------------------------------


def resolve_identity(arg, env=None):
    """--identity, else GITHUB_APP_ACT_AS (set by run, wire and env), else GITHUB_APP_IDENTITY, else default."""
    env = os.environ if env is None else env
    identity = arg or env.get("GITHUB_APP_ACT_AS") or env.get("GITHUB_APP_IDENTITY") or "default"
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
    """The one identity that the GITHUB_APP_* credentials in the environment belong to.

    Only GITHUB_APP_IDENTITY says this, never GITHUB_APP_ACT_AS: a child that
    run or wire points at another identity must not borrow these credentials.
    """
    return env.get("GITHUB_APP_IDENTITY") or "default"


def env_for(identity, env):
    """The environment's GITHUB_APP_* settings if they belong to `identity`, else none of them."""
    return env if identity == env_identity(env) else {}


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
            f"belongs to identity {env_identity(env)!r} (GITHUB_APP_IDENTITY) and is never lent to another; "
            f"run 'github_app.py --identity {identity} store-credentials', or give {identity!r} its own "
            "environment with its own GITHUB_APP_IDENTITY, GITHUB_APP_ID and key")
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


def current_token(identity, config, env=None, now=None, opener=urllib.request.urlopen, signer=sign, refused=None,
                  fresh=False):
    """An installation token in the first half of its life, minting a new one only when needed.

    Every process acting as this identity shares one cached token, under a lock,
    so they never mint over each other. `refused` is a token GitHub rejected: it
    is replaced, unless another process has already replaced it. `fresh` always
    mints: a token keeps the permissions it was minted with, so one granted
    since then shows only on a new token.
    """
    env = os.environ if env is None else env
    now = time.time() if now is None else now
    app_id, key = app_credentials(identity, config, env)
    target_env = env_for(identity, env)  # GITHUB_APP_OWNER and _INSTALLATION_ID belong to one identity too
    credential = fingerprint(app_id, key, config, target_env)
    path = cache_path(identity, env)
    cached = read_cache(path)
    if refused is None and not fresh and usable(cached, credential, now):
        return cached["token"], cached
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path + ".lock", "w") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        cached = read_cache(path)  # another process may have minted while we waited
        if not fresh and usable(cached, credential, now) and cached.get("token") != refused:
            return cached["token"], cached
        jwt = app_jwt(app_id, key, now, signer)
        remembered = cached.get("installationId") if cached.get("credential") == credential else None
        installation = remembered or find_installation(jwt, config, target_env, opener)
        try:
            body = api("POST", f"/app/installations/{installation}/access_tokens", jwt, body={}, opener=opener)
        except Failure as e:
            if e.status != 404 or not remembered:
                raise
            # A reinstalled App has a new installation ID; look it up again once.
            installation = find_installation(jwt, config, target_env, opener)
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


def describe(identity, config, opener=urllib.request.urlopen, signer=sign, env=None, fresh=False):
    """The App's slug, bot name and email, and a valid token, for the commands that need all of them."""
    env = os.environ if env is None else env
    token, cached = current_token(identity, config, env, opener=opener, signer=signer, fresh=fresh)
    app_id, key = app_credentials(identity, config, env)
    app = api("GET", "/app", app_jwt(app_id, key, time.time(), signer), opener=opener)
    name, email = bot_identity(app["slug"], token, opener)
    return app, name, email, token, cached


# --- commands ----------------------------------------------------------------------


def cmd_token(args, config):
    token, _ = current_token(args.identity, config)
    return token


def cmd_check(args, config, opener=urllib.request.urlopen, signer=sign):
    # A fresh token, so permissions granted since the last mint show, and `run` and `gh` get them too.
    app, name, email, token, cached = describe(args.identity, config, opener, signer, fresh=True)
    remember_bot(args.identity, cached["appId"], name, email)  # check refreshes what `run` and `env` use
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
        # Optional: claiming an issue adds a label and a comment.
        "canClaimIssues": permissions.get("issues") in ("write", "admin"),
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


# --- the agent's environment -------------------------------------------------------
#
# The agent's identity lives only in the environment of the processes that act
# as it. Nothing here writes a git config file: see ../DECISIONS.md.


def bot_cache_path(identity, env=None):
    return os.path.join(xdg_dir("state", env), identity + ".bot.json")


def remember_bot(identity, app_id, name, email, env=None):
    write_cache(bot_cache_path(identity, env), {"appId": str(app_id), "name": name, "email": email})


def commit_identity(identity, config, opener=urllib.request.urlopen, signer=sign, env=None):
    """The bot's commit name and email, remembered per App, so `run` asks GitHub only once."""
    env = os.environ if env is None else env
    app_id, _ = app_credentials(identity, config, env)
    known = read_cache(bot_cache_path(identity, env))
    if known.get("appId") == str(app_id) and known.get("name") and known.get("email"):
        return known["name"], known["email"]
    _, name, email, _, _ = describe(identity, config, opener, signer, env)
    remember_bot(identity, app_id, name, email, env)
    return name, email


def agent_env(identity, name, email, offset=0):
    """Every variable that makes git and gh act as the App: the one source for `env`, `run` and `wire`.

    GIT_CONFIG_* outranks every git config file, and GIT_AUTHOR_*/GIT_COMMITTER_*
    outrank user.*, author.*, committer.* and anything included. No token: the
    helper mints one when git asks. `offset` numbers the GIT_CONFIG_* entries
    after ones the environment already has.
    """
    settings = [
        # The empty value first clears every helper from config files, such as
        # the macOS keychain, for github.com.
        (HELPER_KEY, ""),
        (HELPER_KEY, "!" + script_command(identity, "credential")),
        # Never the person's own signing key on the App's commits.
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
    ]
    variables = {
        # Not GITHUB_APP_IDENTITY: that names whose GITHUB_APP_* credentials the
        # environment holds, and a child may inherit another identity's.
        "GITHUB_APP_ACT_AS": identity,
        "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
        "GIT_CONFIG_COUNT": str(offset + len(settings)),
    }
    for i, (key, value) in enumerate(settings, offset):
        variables[f"GIT_CONFIG_KEY_{i}"] = key
        variables[f"GIT_CONFIG_VALUE_{i}"] = value
    return variables


def config_count(env):
    """GIT_CONFIG_COUNT already in an environment, or 0."""
    raw = env.get("GIT_CONFIG_COUNT", "").strip()
    if not raw:
        return 0
    if not raw.isdigit():
        raise Failure(f"GIT_CONFIG_COUNT is {raw!r}, which git refuses; fix or unset it")
    return int(raw)


def env_file_line(key, value):
    """KEY="value", read identically by systemd's EnvironmentFile= and by `set -a; . file` in sh.

    Inside double quotes both treat a backslash before \\ " $ ` as an escape and
    keep every other character as it is.
    """
    return key + '="' + re.sub(r'([\\"$`])', r"\\\1", value) + '"'


def cmd_env(args, config, opener=urllib.request.urlopen, signer=sign):
    """Lines for a server role's environment file: git identity and helper, no secrets."""
    offset = args.offset
    if offset is None:
        present = config_count(os.environ)
        if present:
            raise Failure(f"GIT_CONFIG_COUNT={present} is already set here, and these lines would replace "
                          f"those settings; pass --offset N, where N is the GIT_CONFIG_COUNT of the "
                          f"environment the lines go into")
        offset = 0
    if offset < 0:
        raise Failure("--offset must be 0 or more")
    name, email = commit_identity(args.identity, config, opener, signer)
    return "\n".join(env_file_line(k, v) for k, v in agent_env(args.identity, name, email, offset).items())


def cmd_run(args, config, execvpe=None, which=None, opener=urllib.request.urlopen, signer=sign):
    """Run one command as the App: git's identity and helper, and GH_TOKEN, for that process only."""
    execvpe = execvpe or os.execvpe  # looked up now, so a stub of os.execvpe applies
    which = which or shutil.which
    command = args.rest[1:] if args.rest[:1] == ["--"] else list(args.rest)
    if not command:
        raise Failure("give a command to run, e.g. 'run -- git push'")
    if not which(command[0]):
        raise Failure(f"{command[0]!r} is not on PATH")
    name, email = commit_identity(args.identity, config, opener, signer)
    token, _ = current_token(args.identity, config)
    # Numbered after any GIT_CONFIG_* the caller already has, which keep working.
    env = dict(os.environ, **agent_env(args.identity, name, email, config_count(os.environ)), GH_TOKEN=token)
    # gh prefers GH_TOKEN, but other tools called from 'run' might use GITHUB_TOKEN and act as the person.
    env.pop("GITHUB_TOKEN", None)
    execvpe(command[0], command, env)
    return ""


def cmd_gh(args, config, execvpe=None, which=None, opener=urllib.request.urlopen, signer=sign):
    """`run -- gh …`."""
    rest = args.rest[1:] if args.rest[:1] == ["--"] else args.rest
    return cmd_run(argparse.Namespace(identity=args.identity, rest=["gh", *rest]), config, execvpe, which,
                   opener, signer)


# --- Claude Code projects ----------------------------------------------------------


def settings_path(project):
    return os.path.join(project, ".claude", "settings.local.json")


def value_digest(value):
    """Enough of a value's SHA-256 to tell whether it still matches what wire wrote.

    None for anything but a string, which wire never writes, so such a value
    never matches and is the person's.
    """
    if not isinstance(value, str):
        return None
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def read_marker(env, path):
    """What wire recorded in this env object, or None if it holds no marker."""
    raw = env.get(WIRED_KEY)
    if raw is None:
        return None
    try:
        marker = json.loads(raw)
    except (TypeError, ValueError):
        marker = None
    if (not isinstance(marker, dict) or not isinstance(marker.get("sha256"), dict)
            or not all(isinstance(v, str) for v in marker["sha256"].values())):
        raise Failure(f"{path} has a {WIRED_KEY} that this script can't read; fix or remove it by hand; "
                      "nothing was changed")
    return marker


def read_settings(path):
    try:
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise Failure(f"cannot read {path}: {e}; fix it first, nothing was changed")
    if not isinstance(settings, dict) or not isinstance(settings.get("env", {}), dict):
        raise Failure(f"{path} must hold a JSON object whose 'env' is an object; nothing was changed")
    return settings


def current_umask():
    """The process umask. Python can only read it by setting it, so put it straight back."""
    umask = os.umask(0o022)
    os.umask(umask)
    return umask


def write_json(path, data):
    """Replace a JSON file atomically: through a symlink to its target, keeping an existing file's mode.

    A new file gets what open() would give it, 0666 less the umask.
    """
    path = os.path.realpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        mode = 0o666 & ~current_umask()
    # A temp file of its own, so two writers never write into one file.
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        os.fchmod(fd, mode)  # mkstemp makes it 0600
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass
        raise


@contextlib.contextmanager
def settings_lock(real):
    """Hold an exclusive lock on one settings file's read, work-out and write.

    Without it, two wires (or a wire and an unwire) both read the old file and
    the later write drops the earlier one's change, marker included. The lock
    file lives in this script's state folder, so nothing is left in the person's
    project.

    It is named by the device and inode of the file's folder and the file's name
    in one canonical form (case-folded, canonically normalised), not by its path: on macOS ~/Proj
    and ~/proj, or links to S.json and s.json, are one file under several real
    paths, and two lock names would not exclude each other. Folding can give two
    genuinely different files one lock, which only makes them take turns. Only
    when the folder doesn't exist yet is the whole path used. Names go to bytes
    with os.fsencode, since a path need not be UTF-8.
    """
    if not fcntl:
        yield
        return
    folder = os.path.join(xdg_dir("state"), "locks")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    real = os.path.realpath(real)

    def canonical(name):
        # Unicode's canonical caseless match: casefold can produce decomposed
        # forms (Greek ΐ), so normalise on both sides of it.
        return os.fsencode(unicodedata.normalize("NFD", unicodedata.normalize("NFD", name).casefold()))

    try:
        st = os.stat(os.path.dirname(real))
        key = f"{st.st_dev}:{st.st_ino}/".encode() + canonical(os.path.basename(real))
    except FileNotFoundError:
        key = canonical(real)
    name = hashlib.sha256(key).hexdigest()[:24] + ".lock"
    with open(os.path.join(folder, name), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def project_dir(path):
    project = os.path.realpath(os.path.expanduser(path))
    if not os.path.isdir(project):
        raise Failure(f"{path!r} is not a folder")
    return project


def cmd_wire(args, config, opener=urllib.request.urlopen, signer=sign):
    """Make Claude Code sessions in one project act as the App, through its settings.local.json env."""
    project = project_dir(args.project)
    path = settings_path(project)
    # The file actually written: through a symlink, its target, so the person's link stays.
    real = os.path.realpath(path)
    os.makedirs(os.path.dirname(real), exist_ok=True)  # wire writes here anyway; the lock needs it now
    with settings_lock(real):
        return wire_locked(args, config, opener, signer, project, path, real)


def wire_locked(args, config, opener, signer, project, path, real):
    settings = read_settings(real)
    existed = settings is not None
    settings = settings or {}
    env = dict(settings.get("env") or {})
    # The marker in the file is the only record of what wire wrote there.
    marker = read_marker(env, real)
    ours = marker["sha256"] if marker else {}
    mine = lambda k: k in ours and value_digest(env[k]) == ours[k]
    name, email = commit_identity(args.identity, config, opener, signer)
    wanted = agent_env(args.identity, name, email)
    # Anything this script didn't put there, or that no longer matches what it wrote, is the person's:
    # never overwrite it, and never mix GIT_CONFIG_* numbering with theirs.
    theirs = sorted(k for k in env if (k in wanted or k.startswith("GIT_CONFIG_")) and not mine(k))
    if theirs:
        raise Failure(f"{path} already sets {', '.join(theirs)} in 'env'; remove them first, or use 'run' "
                      "instead; nothing was changed")
    # Whether the first wire created the file or its env, so unwire removes only that.
    if marker:
        created_file, created_env = bool(marker.get("createdFile")), bool(marker.get("createdEnv"))
    else:
        created_file, created_env = not existed, "env" not in settings
    warnings = []
    if config_count(os.environ) and os.environ.get("GIT_CONFIG_VALUE_1") != wanted["GIT_CONFIG_VALUE_1"]:
        warnings.append("GIT_CONFIG_* is set in this shell; in Claude Code sessions in this project the "
                        "App's GIT_CONFIG_* replace it")
    for k in list(ours):
        if k not in wanted and k in env and mine(k):
            del env[k]
    env.update(wanted)
    env[WIRED_KEY] = json.dumps({"identity": args.identity, "createdFile": created_file, "createdEnv": created_env,
                                 "sha256": {k: value_digest(v) for k, v in wanted.items()}},
                                separators=(",", ":"), sort_keys=True)
    settings["env"] = env
    # Everything is worked out above; this one atomic write is the only change.
    write_json(real, settings)
    wired = {"identity": args.identity, "project": project, "settings": path, "commitsAs": f"{name} <{email}>"}
    if warnings:
        wired["warnings"] = warnings
    return wired


def cmd_unwire(args, config):
    """Remove exactly the env keys wire added to a project's settings.local.json, and nothing else."""
    project = project_dir(args.project)
    real = os.path.realpath(settings_path(project))
    with settings_lock(real):
        return unwire_locked(project, real)


def unwire_locked(project, real):
    settings = read_settings(real)
    env = (settings or {}).get("env") or {}
    marker = read_marker(env, real)
    if not marker:
        raise Failure(f"{real} has no record of being wired by this script (no {WIRED_KEY} in its 'env'); "
                      "nothing was changed")
    ours = marker["sha256"]
    changed = sorted(k for k in ours if k in env and value_digest(env[k]) != ours[k])
    for k in ours:
        if k in env and value_digest(env[k]) == ours[k]:
            del env[k]
    del env[WIRED_KEY]
    if env or not marker.get("createdEnv"):
        settings["env"] = env
    else:
        settings.pop("env", None)
    if not settings and marker.get("createdFile"):
        os.remove(real)
    else:
        write_json(real, settings)
    unwired = {"identity": marker.get("identity"), "project": project, "settings": real, "unwired": True}
    if changed:
        unwired["warnings"] = [f"left {', '.join(changed)} in {real}: changed since wire, so they are yours"]
    return unwired


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
    host = fields.get("host", "").lower()
    if host.endswith(":443"):  # the default port, which git's URL matching ignores too
        host = host[:-len(":443")]
    if fields.get("protocol") != "https" or host != "github.com":
        return ""
    token, _ = current_token(args.identity, config)
    return f"username=x-access-token\npassword={token}"


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
    for p in (state, state + ".lock", bot_cache_path(args.identity)):
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
    if warnings:
        forgotten["warnings"] = warnings
    return forgotten


# --- command line ------------------------------------------------------------------


def parser():
    p = argparse.ArgumentParser(prog="github_app.py", description="Act on GitHub as a GitHub App.")
    p.add_argument("--identity", help="which App to act as (default: $GITHUB_APP_ACT_AS, else "
                                         "$GITHUB_APP_IDENTITY, else 'default')")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("token", help="print a valid installation token, minting one if needed")
    sub.add_parser("check", help="show which App and installation this is, and what it may do")
    s = sub.add_parser("store-credentials", help="store the App's ID and a copy of its private key")
    s.add_argument("--app-id", required=True, help="the App's numeric ID, from its settings page")
    s.add_argument("--key-file", required=True, help="the .pem file GitHub generated")
    s.add_argument("--owner", help="the account the App is installed on, if it is installed on several")
    sub.add_parser("run", help="run one command as the App, e.g. 'run -- git push'; everything after 'run' is the command")
    sub.add_parser("gh", help="run gh as the App, e.g. 'gh pr create ...'; everything after 'gh' goes to gh")
    w = sub.add_parser("wire", help="make Claude Code sessions in one project act as the App, through its "
                                    ".claude/settings.local.json")
    w.add_argument("--project", required=True, help="the project folder Claude Code is started in")
    u = sub.add_parser("unwire", help="undo 'wire' in one project")
    u.add_argument("--project", required=True, help="the project folder that was wired")
    e = sub.add_parser("env", help="print environment-file lines that make a server process act as the App")
    e.add_argument("--offset", type=int, help="number the GIT_CONFIG_* lines after the N the target "
                                              "environment already has")
    c = sub.add_parser("credential", help="git credential helper; git runs this itself")
    c.add_argument("operation", choices=["get", "store", "erase"])
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
    "run": cmd_run,
    "gh": cmd_gh,
    "forget": cmd_forget,
}
RAW_OUTPUT = {"token", "env", "credential", "run", "gh"}  # printed bare, for $(...), env files, git and gh
PASS_THROUGH = {"run", "gh"}  # commands whose remaining arguments belong to another program


def split_rest(argv):
    """The command line up to and including `run` or `gh`, and the other program's arguments after it.

    argparse can't pass on arguments that begin with an option, such as
    `gh -R owner/repo pr list`, so everything after `run` or `gh` skips it.
    """
    i = 0
    while i < len(argv):
        if argv[i] == "--identity":
            i += 2
        elif argv[i].startswith("--identity="):
            i += 1
        elif argv[i] in PASS_THROUGH:
            return argv[:i + 1], argv[i + 1:]
        else:
            break
    return argv, []


def main(argv=None):
    head, rest = split_rest(sys.argv[1:] if argv is None else list(argv))
    args = parser().parse_args(head)
    args.rest = rest
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
