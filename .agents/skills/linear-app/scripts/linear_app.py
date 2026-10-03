#!/usr/bin/env python3
"""Give an agent its own Linear identity, as an OAuth app user, with tokens that never need renewing by hand.

The long-lived credential is the OAuth application's client secret. Tokens are
minted from it on demand, cached per identity, and replaced before they expire.
Standard library only.

Why it is built this way, and what was tried and rejected: ../DECISIONS.md.
"""

import argparse
import getpass
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import fcntl
except ImportError:  # not on Windows, which this skill does not support
    fcntl = None

TOKEN_URL = "https://api.linear.app/oauth/token"
GRAPHQL_URL = "https://api.linear.app/graphql"
MCP_URL = "https://mcp.linear.app/mcp"
KEYCHAIN_SERVICE = "linear-app"
DEFAULT_SCOPES = "read,write,app:assignable,app:mentionable"
# Replace a token once less than this much of its life is left, or less than
# half of it for a token issued with a shorter life.
RENEW_MARGIN = 5 * 24 * 3600
IDENTITY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
VIEWER_QUERY = "{ viewer { id name } organization { name urlKey } }"


class Failure(Exception):
    """An error to report to the caller. `status` is Linear's HTTP status, when there was one."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


# --- identity, config and credentials -------------------------------------------


def resolve_identity(arg, env=None):
    env = os.environ if env is None else env
    identity = arg or env.get("LINEAR_APP_IDENTITY") or "default"
    if not IDENTITY_RE.match(identity):
        raise Failure(f"identity {identity!r} may use only letters, digits, '_', '.' and '-'")
    return identity


def xdg_dir(kind, env=None):
    env = os.environ if env is None else env
    var, default = {"config": ("XDG_CONFIG_HOME", ".config"), "state": ("XDG_STATE_HOME", ".local/state")}[kind]
    base = env.get(var) or os.path.join(os.path.expanduser("~"), default)
    return os.path.join(base, "linear-app")


def load_config(identity, env=None):
    path = os.path.join(xdg_dir("config", env), identity + ".json")
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


def scopes_for(config):
    """The scopes this identity's tokens are minted with, in the order given.

    Order is kept, not sorted: minting with a different scope string revokes every
    token the application has issued.
    """
    scopes = config.get("scopes", DEFAULT_SCOPES)
    if isinstance(scopes, list) and all(isinstance(s, str) for s in scopes):
        scopes = ",".join(scopes)
    if isinstance(scopes, str):
        scopes = ",".join(s.strip() for s in scopes.split(",") if s.strip())
        if scopes:
            return scopes
    raise Failure(f"config field 'scopes' must be a non-empty string or list of strings, not {scopes!r}")


def keychain_entries(identity, config):
    """Where the client ID and secret are stored: (service, id account, secret account)."""
    entry = config.get("keychain") or {}
    return (
        entry.get("service", KEYCHAIN_SERVICE),
        entry.get("clientIdAccount", identity + ":client-id"),
        entry.get("clientSecretAccount", identity + ":client-secret"),
    )


def keychain_tool(which=shutil.which):
    if which("security"):
        return "security"
    if which("secret-tool"):
        return "secret-tool"
    return None


def read_keychain(service, account, run=subprocess.run, which=shutil.which):
    """The stored value, or None when no keychain tool exists or nothing is stored."""
    tool = keychain_tool(which)
    if tool == "security":
        cmd = ["security", "find-generic-password", "-s", service, "-a", account, "-w"]
    elif tool == "secret-tool":
        cmd = ["secret-tool", "lookup", "service", service, "account", account]
    else:
        return None
    result = run(cmd, capture_output=True, text=True)
    value = result.stdout.strip() if result.returncode == 0 else ""
    return value or None


def write_keychain(service, account, value, label, run=subprocess.run, which=shutil.which):
    tool = keychain_tool(which)
    if tool == "security":
        # `security` takes the secret only as an argument, so it is briefly
        # visible to other processes of this user; see DECISIONS.md.
        result = run(["security", "add-generic-password", "-U", "-s", service, "-a", account, "-w", value],
                     capture_output=True, text=True)
    elif tool == "secret-tool":
        result = run(["secret-tool", "store", "--label", label, "service", service, "account", account],
                     input=value, capture_output=True, text=True)
    else:
        raise Failure("no keychain tool found (macOS 'security' or Linux 'secret-tool'); "
                      "set LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET instead")
    if result.returncode != 0:
        raise Failure(f"storing {account} failed: {result.stderr.strip()}")


def delete_keychain(service, account, run=subprocess.run, which=shutil.which):
    tool = keychain_tool(which)
    if tool == "security":
        run(["security", "delete-generic-password", "-s", service, "-a", account], capture_output=True)
    elif tool == "secret-tool":
        run(["secret-tool", "clear", "service", service, "account", account], capture_output=True)


def env_identity(env):
    """The one identity that LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET belong to."""
    return env.get("LINEAR_APP_IDENTITY") or "default"


def env_overrides_keychain(identity, env=None):
    """True when the environment, not the keychain, supplies this identity's credentials."""
    env = os.environ if env is None else env
    return identity == env_identity(env) and bool(
        env.get("LINEAR_CLIENT_ID", "").strip() or env.get("LINEAR_CLIENT_SECRET", "").strip())


ENV_OVERRIDE_WARNING = ("LINEAR_CLIENT_ID/LINEAR_CLIENT_SECRET in the environment override the keychain "
                        "for this identity; unset them for the keychain entries to take effect")


def client_credentials(identity, config, env=None, read=None):
    """The OAuth client ID and secret: environment first, then the keychain.

    The environment belongs to one identity only: $LINEAR_APP_IDENTITY, else
    'default'. Any other identity reads the keychain, so it never borrows
    another application's credentials.
    """
    env = os.environ if env is None else env
    read = read or read_keychain  # looked up now, so a stub of read_keychain applies
    if env_overrides_keychain(identity, env):
        client_id = env.get("LINEAR_CLIENT_ID", "").strip()
        secret = env.get("LINEAR_CLIENT_SECRET", "").strip()
        if client_id and secret:
            return client_id, secret
        if client_id or secret:
            raise Failure("set both LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET, or neither")
    service, id_account, secret_account = keychain_entries(identity, config)
    client_id = read(service, id_account)
    secret = read(service, secret_account)
    if client_id and secret:
        return client_id, secret
    owner = env_identity(env)
    if identity != owner and (env.get("LINEAR_CLIENT_ID", "").strip() or env.get("LINEAR_CLIENT_SECRET", "").strip()):
        raise Failure(
            f"no client credentials for identity {identity!r}: LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET are set, "
            f"but they belong to identity {owner!r} (LINEAR_APP_IDENTITY); set LINEAR_APP_IDENTITY={identity} "
            f"to use them for {identity!r}, or run 'linear_app.py --identity {identity} store-credentials'"
        )
    raise Failure(
        f"no client credentials for identity {identity!r}: set LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET, "
        f"or run 'linear_app.py --identity {identity} store-credentials'"
    )


# --- HTTP ------------------------------------------------------------------------


def post(url, data, headers, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with opener(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except (ValueError, OSError):
            body = {}
        message = body.get("error_description") or body.get("error") or e.reason
        if isinstance(body.get("errors"), list) and body["errors"]:
            message = body["errors"][0].get("message", message)
        raise Failure(f"Linear answered {e.code}: {message}", status=e.code)
    except (urllib.error.URLError, OSError) as e:
        raise Failure(f"cannot reach Linear: {getattr(e, 'reason', e)}")
    except ValueError:
        raise Failure("Linear sent a response that is not JSON")


def mint(client_id, secret, scopes, opener=urllib.request.urlopen):
    """A new token: (access token, seconds until it expires)."""
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
        "scope": scopes,
    }).encode()
    body = post(TOKEN_URL, data, {"Content-Type": "application/x-www-form-urlencoded"}, opener)
    token = body.get("access_token")
    if not token:
        raise Failure("Linear returned no access token; check that client credentials are enabled on the application")
    return token, int(body.get("expires_in") or 30 * 24 * 3600)


def graphql(token, query, opener=urllib.request.urlopen):
    data = json.dumps({"query": query}).encode()
    body = post(GRAPHQL_URL, data, {"Content-Type": "application/json", "Authorization": "Bearer " + token}, opener)
    if body.get("errors"):
        raise Failure(f"Linear rejected the query: {body['errors'][0].get('message', body['errors'])}")
    return body.get("data") or {}


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


def fingerprint(client_id, secret, scopes):
    """Identifies what a token was minted from, without holding the secret.

    Any change (a new app, a rotated secret, new scopes) makes the cached token
    unusable, since each of them can leave it revoked or wrong.
    """
    return hashlib.sha256(json.dumps([client_id, secret, scopes]).encode()).hexdigest()


def usable(cached, credential, now):
    expires_at = cached.get("expiresAt", 0)
    lifetime = expires_at - cached.get("mintedAt", expires_at - 2 * RENEW_MARGIN)
    return (
        cached.get("token")
        and cached.get("credential") == credential
        and expires_at - now > min(RENEW_MARGIN, lifetime / 2)
    )


def current_token(identity, config, env=None, now=None, opener=urllib.request.urlopen, read=None,
                  refused=None):
    """A token with at least RENEW_MARGIN left, minting a new one only when needed.

    Every process acting as this identity shares one cached token, under a lock,
    so they never mint over each other. `refused` is a token Linear rejected: it
    is replaced, unless another process has already replaced it.
    """
    now = time.time() if now is None else now
    scopes = scopes_for(config)
    client_id, secret = client_credentials(identity, config, env, read)
    credential = fingerprint(client_id, secret, scopes)
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
        token, expires_in = mint(client_id, secret, scopes, opener)
        cached = {"token": token, "scopes": scopes, "credential": credential,
                  "mintedAt": int(now), "expiresAt": int(now + expires_in)}
        write_cache(path, cached)
    return token, cached


# --- commands ----------------------------------------------------------------------


def cmd_token(args, config):
    token, _ = current_token(args.identity, config)
    return token


def cmd_headers(args, config):
    token, _ = current_token(args.identity, config)
    return json.dumps({"Authorization": "Bearer " + token})


def cmd_check(args, config):
    token, cached = current_token(args.identity, config)
    try:
        data = graphql(token, VIEWER_QUERY)
    except Failure as e:
        if e.status != 401:
            raise
        # Revoked without our knowing (a mint elsewhere with other scopes, say):
        # replace it once, and report a second refusal as it is.
        token, cached = current_token(args.identity, config, refused=token)
        data = graphql(token, VIEWER_QUERY)
    viewer, org = data.get("viewer") or {}, data.get("organization") or {}
    result = {
        "identity": args.identity,
        "user": viewer.get("name"),
        "workspace": {"name": org.get("name"), "urlKey": org.get("urlKey")},
        "scopes": cached["scopes"],
        "canBeDelegate": "app:assignable" in cached["scopes"].split(","),
        "tokenDaysLeft": max(0, int((cached["expiresAt"] - time.time()) // 86400)),
    }
    expected = config.get("workspace")
    if expected and expected not in (org.get("urlKey"), org.get("name")):
        raise Failure(f"identity {args.identity!r} belongs to workspace {org.get('urlKey')!r}, "
                      f"but its config expects {expected!r}")
    for key in ("teams", "people", "notes"):
        if config.get(key):
            result[key] = config[key]
    return result


def cmd_store_credentials(args, config):
    service, id_account, secret_account = keychain_entries(args.identity, config)
    print("Find both values in Linear: Settings -> API -> your OAuth application.", file=sys.stderr)
    print("Client ID: ", end="", file=sys.stderr, flush=True)  # stdout holds only the JSON
    try:
        client_id = input().strip()
        secret = getpass.getpass("Client secret (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        raise Failure("store-credentials needs a person at a terminal to type the client ID and secret; "
                      "an agent should ask the user to run it. Nothing was stored")
    if not client_id or not secret:
        raise Failure("both the client ID and the client secret are needed; nothing was stored")
    write_keychain(service, id_account, client_id, f"Linear client ID ({args.identity})")
    write_keychain(service, secret_account, secret, f"Linear client secret ({args.identity})")
    stored = {"identity": args.identity, "stored": True, "service": service}
    if env_overrides_keychain(args.identity):
        stored["warnings"] = [ENV_OVERRIDE_WARNING]
    return stored


def helper_command(identity, script=None, python=None):
    script = script or os.path.abspath(__file__)
    python = python or sys.executable
    return " ".join(shlex.quote(p) for p in (python, script, "--identity", identity, "headers"))


def cmd_wire(args, config, run=subprocess.run, which=shutil.which):
    if not which("claude"):
        raise Failure("'claude' is not on PATH; wiring is for Claude Code. Other MCP clients: see the README")
    current_token(args.identity, config)  # fail now, not at the next session start
    scope = "local" if args.project else "user"
    cwd = os.path.abspath(args.project) if args.project else None
    if cwd and not os.path.isdir(cwd):
        raise Failure(f"--project {args.project!r} is not a folder")
    server = json.dumps({"type": "http", "url": MCP_URL, "headersHelper": helper_command(args.identity)})

    def claude(*cmd):
        result = run(["claude", "mcp", *cmd], cwd=cwd, capture_output=True, text=True)
        return result.returncode == 0 or result

    def add(name):
        result = claude("add-json", "--scope", scope, name, server)
        if result is not True:
            raise Failure(f"claude mcp add-json failed: {result.stderr.strip() or result.stdout.strip()}")

    # Prove the new server can be added under a spare name before removing the
    # old one, so a failure never leaves the user with no Linear server at all.
    trial = args.name + "-linear-app-new"
    claude("remove", "--scope", scope, trial)
    add(trial)
    claude("remove", "--scope", scope, trial)
    claude("remove", "--scope", scope, args.name)
    add(args.name)
    wired = {"identity": args.identity, "server": args.name, "scope": scope, "restartNeeded": True}
    if cwd:
        wired["project"] = cwd
    return wired


def cmd_forget(args, config):
    service, id_account, secret_account = keychain_entries(args.identity, config)
    forgotten = {"identity": args.identity, "forgotten": True}
    if service == KEYCHAIN_SERVICE:
        for account in (id_account, secret_account):
            delete_keychain(service, account)
    else:  # entries another tool made, which it may still use
        forgotten["keptKeychain"] = {"service": service, "accounts": [id_account, secret_account]}
    path = cache_path(args.identity)
    for p in (path, path + ".lock"):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    # Report what is actually left, not what should be: check each source directly.
    sources, warnings = [], []
    if env_overrides_keychain(args.identity):
        if os.environ.get("LINEAR_CLIENT_ID", "").strip() and os.environ.get("LINEAR_CLIENT_SECRET", "").strip():
            sources.append("the environment (LINEAR_CLIENT_ID/LINEAR_CLIENT_SECRET)")
        else:
            warnings.append("only one of LINEAR_CLIENT_ID/LINEAR_CLIENT_SECRET is set in the environment; unset it")
    if read_keychain(service, id_account) and read_keychain(service, secret_account):
        sources.append(f"the keychain entries in service {service!r}, "
                       + ("which the delete did not remove (a locked keychain or a denied prompt?)"
                          if service == KEYCHAIN_SERVICE else "which forget keeps"))
    if sources and warnings:  # the half pair blocks the keychain until it is unset
        warnings.append("once it is unset, this identity works again from " + " and ".join(sources))
    elif sources:
        warnings.append("this identity still has credentials and keeps working, from " + " and ".join(sources))
    if warnings:
        forgotten["warnings"] = warnings
    return forgotten


# --- command line ------------------------------------------------------------------


def parser():
    p = argparse.ArgumentParser(prog="linear_app.py", description="Act on Linear as an OAuth app user.")
    p.add_argument("--identity", help="which app user to act as (default: $LINEAR_APP_IDENTITY, else 'default')")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("token", help="print a valid access token, minting one if needed")
    sub.add_parser("headers", help="print the Authorization header as JSON, for an MCP headersHelper")
    sub.add_parser("check", help="show who the token acts as, and what it may do")
    sub.add_parser("store-credentials", help="save this identity's client ID and secret in the keychain")
    w = sub.add_parser("wire", help="point Claude Code's Linear MCP server at this identity")
    w.add_argument("--project", help="only for sessions started in this folder (default: every session)")
    w.add_argument("--name", default="linear", help="the MCP server's name (default: linear)")
    sub.add_parser("forget", help="delete this identity's stored credentials and cached token")
    return p


COMMANDS = {
    "token": cmd_token,
    "headers": cmd_headers,
    "check": cmd_check,
    "store-credentials": cmd_store_credentials,
    "wire": cmd_wire,
    "forget": cmd_forget,
}
RAW_OUTPUT = {"token", "headers"}  # printed bare, for $(...) and headersHelper


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        args.identity = resolve_identity(args.identity)
        result = COMMANDS[args.command](args, load_config(args.identity))
    except Failure as e:
        if args.command in RAW_OUTPUT:
            print(f"linear_app: {e}", file=sys.stderr)
        else:
            print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    except Exception as e:  # callers parse stdout, so even a bug answers predictably
        import traceback
        traceback.print_exc()
        if args.command not in RAW_OUTPUT:
            print(json.dumps({"ok": False, "error": f"unexpected error: {e!r}"}))
        return 1
    print(result if args.command in RAW_OUTPUT else json.dumps({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
