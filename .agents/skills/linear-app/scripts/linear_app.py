#!/usr/bin/env python3
"""Give an agent its own Linear identity, as an OAuth app user, with tokens that never need renewing by hand.

The long-lived credential is the OAuth application's client secret. Tokens are
minted from it on demand, cached per identity, and replaced before they expire.
A relay identity, the one the inquisitor's answer service posts a person's
answers through, never has its token printed (linear-app spec). Standard
library only.
"""

import argparse
import getpass
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from typing import Any, NamedTuple, cast

try:
    import fcntl
except ImportError:  # not on Windows, which this skill does not support
    fcntl = None

TOKEN_URL = "https://api.linear.app/oauth/token"
GRAPHQL_URL = "https://api.linear.app/graphql"
MCP_URL = "https://mcp.linear.app/mcp"
KEYCHAIN_SERVICE = "linear-app"
DEFAULT_SCOPES = "read,write,app:assignable,app:mentionable"
IDENTITY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
VIEWER_QUERY = "{ viewer { id name } organization { name urlKey } }"
TEAMS_QUERY = ("query($after: String) { teams(first: 100, after: $after) "
               "{ nodes { key } pageInfo { hasNextPage endCursor } } }")
TEAM_PAGES = 50  # 5,000 teams; a workspace with more is not plausible
NO_KEYCHAIN_TOOL = "no keychain tool found (neither macOS 'security' nor Linux 'secret-tool')"

Config = dict[str, Any]
Env = Mapping[str, str]
Opener = Callable[..., Any]
Runner = Callable[..., Any]
Which = Callable[[str], Any]
Reader = Callable[[str, str], "str | None"]


class Failure(Exception):
    """An error to report to the caller.

    `status` is Linear's HTTP status, when there was one; `errors` is the
    `errors` list Linear returned, kept unchanged so a caller reads the cause
    as Linear reports it.
    """

    def __init__(self, message: str, status: int | None = None, errors: object = None):
        super().__init__(message)
        self.status = status
        self.errors = errors


def as_dict(value: Any) -> dict[str, Any]:
    """value when it is a JSON object, else an empty one."""
    return dict(cast(dict[str, Any], value)) if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """value when it is a JSON array, else an empty one."""
    return list(cast(list[Any], value)) if isinstance(value, list) else []


def strings(value: Any) -> list[str] | None:
    """value when it is a JSON array of strings, else None."""
    if not isinstance(value, list):
        return None
    items = as_list(value)
    return [str(s) for s in items] if all(isinstance(s, str) for s in items) else None


# --- identity, config and credentials -------------------------------------------


def resolve_identity(arg: str | None, env: Env | None = None) -> str:
    env = os.environ if env is None else env
    identity = arg or env.get("LINEAR_APP_IDENTITY") or "default"
    if not IDENTITY_RE.match(identity):
        raise Failure(f"identity {identity!r} may use only letters, digits, '_', '.' and '-'")
    return identity


def xdg_dir(kind: str, env: Env | None = None) -> str:
    env = os.environ if env is None else env
    var, default = {"config": ("XDG_CONFIG_HOME", ".config"), "state": ("XDG_STATE_HOME", ".local/state")}[kind]
    base = env.get(var) or os.path.join(os.path.expanduser("~"), default)
    return os.path.join(base, "linear-app")


def load_config(identity: str, env: Env | None = None) -> Config:
    path = os.path.join(xdg_dir("config", env), identity + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            config: object = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise Failure(f"cannot read {path}: {e}")
    if not isinstance(config, dict):
        raise Failure(f"{path} must hold a JSON object")
    return as_dict(config)


def scopes_for(config: Config) -> str:
    """The scopes this identity's tokens are minted with, in the order given.

    Order is kept, not sorted: minting with a different scope string revokes every
    token the application has issued.
    """
    scopes: object = config.get("scopes", DEFAULT_SCOPES)
    listed = strings(scopes)
    if listed is not None:
        scopes = ",".join(listed)
    if isinstance(scopes, str):
        scopes = ",".join(s.strip() for s in scopes.split(",") if s.strip())
        if scopes:
            return scopes
    raise Failure(f"config field 'scopes' must be a non-empty string or list of strings, not {scopes!r}")


def keychain_entries(identity: str, config: Config) -> tuple[str, str, str]:
    """Where the client ID and secret are stored: (service, id account, secret account)."""
    entry: Config = config.get("keychain") or {}
    return (
        entry.get("service", KEYCHAIN_SERVICE),
        entry.get("clientIdAccount", identity + ":client-id"),
        entry.get("clientSecretAccount", identity + ":client-secret"),
    )


def token_account(identity: str) -> str:
    """The keychain account, under the service linear-app, that caches a relay identity's token."""
    return identity + ":token"


def keychain_tool(which: Which = shutil.which) -> str | None:
    if which("security"):
        return "security"
    if which("secret-tool"):
        return "secret-tool"
    return None


def read_keychain(service: str, account: str, run: Runner = subprocess.run, which: Which = shutil.which) -> str | None:
    """The stored value, or None when no keychain tool exists or nothing is stored."""
    tool = keychain_tool(which)
    if tool == "security":
        cmd = ["security", "find-generic-password", "-s", service, "-a", account, "-w"]
    elif tool == "secret-tool":
        cmd = ["secret-tool", "lookup", "service", service, "account", account]
    else:
        return None
    result = run(cmd, capture_output=True, text=True)
    value: str = result.stdout.strip() if result.returncode == 0 else ""
    return value or None


SECURITY_PROMPTS = re.compile(r"(?:password data|retype password) for new item: ")
SECURITY_PROMPT_LIMIT = 128


def store_in_macos_keychain(service: str, account: str, value: str, run: Runner = subprocess.run) -> None:
    """Store `value` with `security`, never on its command line, and check that it reads back.

    Given `-w` last with no value, `security` asks for the password twice.
    It reads the answers from standard input only when it has no terminal,
    so this starts it in a new session, which leaves it none.
    Given one copy instead of two, it stores an empty password and still
    exits 0, so the entry is read back to check it.

    The prompt keeps only a password's first 128 characters (measured
    2026-11-27), too few for a relay identity's cached token. A longer value
    goes to `security -i`, which reads its commands from standard input, as
    hex after `-X`, so it is never on a command line and needs no quoting.
    """
    where = f"(service {service!r}, account {account!r})"
    if len(value) > SECURITY_PROMPT_LIMIT:
        command = f"add-generic-password -U -s {service} -a {account} -X {value.encode().hex()}\n"
        result = run(["security", "-i"], input=command, capture_output=True, text=True)
    else:
        cmd = ["security", "add-generic-password", "-U", "-s", service, "-a", account, "-w"]
        result = run(cmd, input=f"{value}\n{value}\n", capture_output=True, text=True, start_new_session=True)
    if result.returncode != 0:
        raise Failure(f"storing {account} failed: {SECURITY_PROMPTS.sub('', result.stderr).strip()}")
    cmd = ["security", "find-generic-password", "-s", service, "-a", account, "-w"]
    result = run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Failure(f"could not read back the keychain entry {where} to check it: {result.stderr.strip()}")
    # The read-back is stripped as read_keychain strips what it reads, so this
    # passes only when later commands would get this value; store-credentials
    # strips both values before storing them. A wrong entry is left in place:
    # find-generic-password searches every keychain in the search list, so the
    # entry it found may be another keychain's.
    if result.stdout.strip() != value:
        raise Failure(f"the keychain entry {where} does not hold the value entered; "
                      "run store-credentials again, or add the entry with Keychain Access")


def write_keychain(service: str, account: str, value: str, label: str,
                   run: Runner = subprocess.run, which: Which = shutil.which) -> None:
    tool = keychain_tool(which)
    if tool == "security":
        store_in_macos_keychain(service, account, value, run)
        return
    if tool == "secret-tool":
        result = run(["secret-tool", "store", "--label", label, "service", service, "account", account],
                     input=value, capture_output=True, text=True)
    else:
        raise Failure(NO_KEYCHAIN_TOOL + "; set LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET instead")
    if result.returncode != 0:
        raise Failure(f"storing {account} failed: {result.stderr.strip()}")


def delete_keychain(service: str, account: str, run: Runner = subprocess.run, which: Which = shutil.which,
                    lookup: Callable[..., "str | None"] = read_keychain) -> bool:
    """True when the entry is gone afterwards, False when the delete failed (a locked keychain, say).

    `lookup` is bound to the real read_keychain when this is defined, so it runs
    through the same `run` and `which` even where read_keychain is replaced.
    """
    tool = keychain_tool(which)
    if tool == "security":
        result = run(["security", "delete-generic-password", "-s", service, "-a", account], capture_output=True)
        return result.returncode in (0, 44)  # 44: no such entry
    if tool == "secret-tool":
        result = run(["secret-tool", "clear", "service", service, "account", account], capture_output=True)
        if result.returncode == 0:
            return True
        # Any other exit can't tell "nothing matched" from "no secret service"
        # or a locked collection, so the entry counts as gone when a lookup
        # can't find it either. An entry a locked collection still holds would
        # then wrongly count as gone.
        return lookup(service, account, run, which) is None
    return True  # no keychain tool, so nothing can be stored


def env_identity(env: Env) -> str:
    """The one identity that LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET belong to."""
    return env.get("LINEAR_APP_IDENTITY") or "default"


def env_overrides_keychain(identity: str, env: Env | None = None) -> bool:
    """True when the environment, not the keychain, supplies this identity's credentials."""
    env = os.environ if env is None else env
    return identity == env_identity(env) and bool(
        env.get("LINEAR_CLIENT_ID", "").strip() or env.get("LINEAR_CLIENT_SECRET", "").strip())


ENV_OVERRIDE_WARNING = ("LINEAR_CLIENT_ID/LINEAR_CLIENT_SECRET in the environment override the keychain "
                        "for this identity; unset them for the keychain entries to take effect")


def client_credentials(identity: str, config: Config, env: Env | None = None, read: Reader | None = None,
                       relay: bool = False) -> tuple[str, str]:
    """The OAuth client ID and secret: environment first, then the keychain.

    The environment belongs to one identity only: $LINEAR_APP_IDENTITY, else
    'default'. Any other identity reads the keychain, so it never borrows
    another application's credentials. A relay identity reads the keychain
    only: any agent's environment can hold the variables, so any agent
    could mint the relay's token from them.
    """
    env = os.environ if env is None else env
    read = read or read_keychain  # looked up now, so a stub of read_keychain applies
    if not relay and env_overrides_keychain(identity, env):
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
    if relay:
        raise Failure(
            f"no client credentials for identity {identity!r} in the keychain: a relay identity reads them only "
            f"from there, never from LINEAR_CLIENT_ID or LINEAR_CLIENT_SECRET; "
            f"run 'linear_app.py --identity {identity} store-credentials'"
        )
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


# --- relay identities ------------------------------------------------------------


class Relay(NamedTuple):
    """Whether an identity is a relay identity, and why, for refusals to name.

    `warning` is a fault in inquisitor.json the person must fix; every
    command adds it to its output. While it is set and `relay` is not, token,
    headers and wire refuse, since linear-app cannot tell which identity was
    meant as the relay.
    """

    relay: bool
    why: str = ""
    warning: str = ""


NOT_RELAY = Relay(False)


def inquisitor_config_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "shared-skills", "inquisitor.json")


def json_type(value: object) -> str:
    """The JSON name of a parsed value's type, for messages."""
    for kind, name in ((bool, "a boolean"), (int, "a number"), (float, "a number"), (str, "a string"),
                       (list, "an array"), (dict, "an object")):
        if isinstance(value, kind):
            return name
    return "null"


def configured_relay(path: str | None = None) -> tuple[str | None, str | None]:
    """(the Linear relay name inquisitor.json holds, valid or not, or None;
    what is wrong with the file, how to fix it, and that every identity
    counts as a relay identity until the file is fixed, or None)."""
    path = path or inquisitor_config_path()
    until = "; until it is fixed, every identity counts as a relay identity"
    try:
        with open(path, encoding="utf-8") as f:
            data: object = json.load(f)
    except (FileNotFoundError, NotADirectoryError):
        return None, None
    except (OSError, ValueError) as e:
        return None, f"{path} cannot be read as a JSON object ({e}); fix the file or remove it{until}"
    node, key = data, ""
    for name in ("answer_service", "linear"):
        if not isinstance(node, dict):
            return None, (f"{key or 'the top level'} in {path} must be a JSON object, not {json_type(node)}; "
                          f"make it an object, or remove it{until}")
        fields = as_dict(node)
        if name not in fields:
            return None, None
        node, key = fields[name], f"{key}.{name}" if key else name
    if not isinstance(node, dict):
        return None, f"{key} in {path} must be a JSON object, not {json_type(node)}; make it an object, or remove it{until}"
    linear = as_dict(node)
    if "relay" not in linear:
        return None, None
    relay: object = linear["relay"]
    if not isinstance(relay, str):
        return None, (f"answer_service.linear.relay in {path} must be a string naming the relay identity, not "
                      f"{json_type(relay)}; set it to that name, or remove it{until}")
    return relay, None


def relay_status(identity: str, config: Config, env: Env | None = None, read: Reader | None = None,
                 which: Which = shutil.which) -> Relay:
    """Whether `identity` is a relay identity: the Linear relay inquisitor.json
    names, or an identity holding that relay's client ID (linear-app spec)."""
    env = os.environ if env is None else env
    read = read or read_keychain
    relay, everyone = configured_relay()
    if everyone:
        return Relay(True, everyone, everyone)
    if relay is None:
        return NOT_RELAY
    if not IDENTITY_RE.fullmatch(relay):
        return Relay(False, warning=(
            f"answer_service.linear.relay in {inquisitor_config_path()} is {relay!r}, which is no identity name: "
            "a name uses only letters, digits, '_', '.' and '-'. Set it to the name of an identity given to "
            f"store-credentials (`ls {xdg_dir('config', env)}` lists those with a config), or remove it; until "
            "then token, headers and wire refuse for every identity, since linear-app cannot tell which identity was meant"))
    if identity == relay:
        return Relay(True, f"identity {identity!r} is the Linear relay that {inquisitor_config_path()} names")
    unreadable = f"so every identity counts as a relay identity while {inquisitor_config_path()} names a Linear relay"
    try:
        relay_config = load_config(relay, env)
    except Failure as e:
        return Relay(True, f"the Linear relay's config cannot be read ({e}), {unreadable}")
    service, id_account, _ = keychain_entries(relay, relay_config)
    relay_id = read(service, id_account)
    if not relay_id:
        if keychain_tool(which) is None:
            return Relay(True, f"{NO_KEYCHAIN_TOOL}, so the Linear relay {relay!r}'s client ID cannot be read, "
                               f"{unreadable}")
        return Relay(True, f"the keychain gives no client ID for the Linear relay {relay!r} (service "
                           f"{service!r}, account {id_account!r}), {unreadable}")
    own = env.get("LINEAR_CLIENT_ID", "").strip() if identity == env_identity(env) else ""
    if not own:
        service, id_account, _ = keychain_entries(identity, config)
        own = (read(service, id_account) or "").strip()
    if own and own == relay_id.strip():
        return Relay(True, f"identity {identity!r} holds the client ID of the Linear relay {relay!r}")
    return NOT_RELAY


def relay_of(args: argparse.Namespace) -> Relay:
    relay: object = getattr(args, "relay", NOT_RELAY)
    return relay if isinstance(relay, Relay) else NOT_RELAY


def posts_only_through_commands(identity: str, relay: Relay) -> str:
    return (f"identity {identity!r} is a relay identity ({relay.why}); a relay identity posts only through "
            "post, edit and delete, and no command prints its token or hands it to the Linear MCP server")


# --- HTTP ------------------------------------------------------------------------


def post(url: str, data: bytes, headers: dict[str, str], opener: Opener = urllib.request.urlopen) -> dict[str, Any]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with opener(req, timeout=30) as resp:
            body: object = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except (ValueError, OSError):
            body = {}
        fields = as_dict(body)
        message: object = fields.get("error_description") or fields.get("error") or e.reason
        errors: object = fields.get("errors")
        first = as_list(errors)[:1]
        if first and isinstance(first[0], dict):
            message = as_dict(first[0]).get("message", message)
        raise Failure(f"Linear answered {e.code}: {message}", status=e.code, errors=errors)
    except (urllib.error.URLError, OSError) as e:
        raise Failure(f"cannot reach Linear: {getattr(e, 'reason', e)}")
    except ValueError:
        raise Failure("Linear sent a response that is not JSON")
    if not isinstance(body, dict):
        raise Failure("Linear sent a response that is not a JSON object")
    return as_dict(body)


def granted_scopes(body: dict[str, Any]) -> list[str] | None:
    """The scopes a token response says Linear granted, or None when it names none."""
    scope: object = body.get("scope")
    if isinstance(scope, str):
        return [s for s in re.split(r"[\s,]+", scope) if s]
    return strings(scope)


def mint(client_id: str, secret: str, scopes: str,
         opener: Opener = urllib.request.urlopen) -> tuple[str, int, list[str] | None]:
    """A new token: (access token, seconds until it expires, the scopes Linear granted)."""
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
        "scope": scopes,
    }).encode()
    body = post(TOKEN_URL, data, {"Content-Type": "application/x-www-form-urlencoded"}, opener)
    token: object = body.get("access_token")
    if not token or not isinstance(token, str):
        raise Failure("Linear returned no access token; check that client credentials are enabled on the application")
    return token, int(body.get("expires_in") or 30 * 24 * 3600), granted_scopes(body)


def graphql(token: str, query: str, opener: Opener = urllib.request.urlopen,
            variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """The `data` of a GraphQL request. Callers pass any text only in
    `variables`, so it reaches Linear as data and can never change the query."""
    payload: dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    body = post(GRAPHQL_URL, json.dumps(payload).encode(),
                {"Content-Type": "application/json", "Authorization": "Bearer " + token}, opener)
    errors: object = body.get("errors")
    if errors:
        first: object = as_list(errors)[0] if as_list(errors) else errors
        message: object = as_dict(first).get("message", first)
        raise Failure(f"Linear rejected the query: {message}", status=200, errors=errors)
    data: object = body.get("data")
    return as_dict(data)


# --- the token cache ---------------------------------------------------------------


def cache_path(identity: str, env: Env | None = None) -> str:
    return os.path.join(xdg_dir("state", env), identity + ".json")


def read_cache(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            cached: object = json.load(f)
        return as_dict(cached)
    except (OSError, ValueError):
        return {}


def write_cache(path: str, cached: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    os.replace(tmp, path)


def drop_file_cache(identity: str, env: Env | None = None) -> None:
    """Delete any token linear-app's state folder holds for the identity."""
    path = cache_path(identity, env)
    for p in (path, path + ".tmp"):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def read_keychain_cache(identity: str) -> dict[str, Any]:
    try:
        cached: object = json.loads(read_keychain(KEYCHAIN_SERVICE, token_account(identity)) or "{}")
    except ValueError:
        return {}
    return as_dict(cached)


def fingerprint(client_id: str, secret: str, scopes: str) -> str:
    """Identifies what a token was minted from, without holding the secret.

    Any change (a new app, a rotated secret, new scopes) makes the cached token
    unusable, since each of them can leave it revoked or wrong.
    """
    return hashlib.sha256(json.dumps([client_id, secret, scopes]).encode()).hexdigest()


def usable(cached: dict[str, Any], credential: str, now: float) -> bool:
    # a cache with no record of the scopes Linear granted is unusable, so current_token mints a new
    # token, whose scopes check can report
    return bool(cached.get("token") and cached.get("credential") == credential and now < cached.get("renewAt", 0)
                and "grantedScopes" in cached)


def current_token(identity: str, config: Config, env: Env | None = None, now: float | None = None,
                  opener: Opener = urllib.request.urlopen, read: Reader | None = None,
                  refused: str | None = None, relay: bool = False) -> tuple[str, dict[str, Any]]:
    """A token in the first half of its life, minting a new one only when needed.

    Every process acting as this identity shares one cached token, under a lock,
    so they never mint over each other. `refused` is a token Linear rejected: it
    is replaced, unless another process has already replaced it. A relay
    identity's token is cached only in the keychain, under the service
    linear-app and the account `<identity>:token`; the lock file holds no token.
    """
    now = time.time() if now is None else now
    scopes = scopes_for(config)
    client_id, secret = client_credentials(identity, config, env, read, relay)
    credential = fingerprint(client_id, secret, scopes)
    path = cache_path(identity, env)

    def load() -> dict[str, Any]:
        return read_keychain_cache(identity) if relay else read_cache(path)

    cached = load()
    if refused is None and usable(cached, credential, now):
        return cached["token"], cached
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path + ".lock", "w") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        cached = load()  # another process may have minted while we waited
        if usable(cached, credential, now) and cached.get("token") != refused:
            return cached["token"], cached
        token, expires_in, granted = mint(client_id, secret, scopes, opener)
        # Renewed halfway through its life, whatever life Linear gives it, so a
        # session that keeps the token it got at start has at least half left.
        cached = {"token": token, "scopes": scopes, "grantedScopes": granted, "credential": credential,
                  "renewAt": int(now + expires_in / 2), "expiresAt": int(now + expires_in)}
        if relay:
            write_keychain(KEYCHAIN_SERVICE, token_account(identity), json.dumps(cached),
                           f"Linear token ({identity})")
        else:
            write_cache(path, cached)
    return token, cached


def with_token(args: argparse.Namespace, config: Config,
               call: Callable[[str], dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """call(token)'s result and the cache entry. When Linear answers 401 to a
    token revoked without our knowing (a mint elsewhere with other scopes,
    say), it is replaced once, and a second refusal is reported as it is."""
    relay = relay_of(args).relay
    token, cached = current_token(args.identity, config, relay=relay)
    try:
        return call(token), cached
    except Failure as e:
        if e.status != 401:
            raise
    token, cached = current_token(args.identity, config, refused=token, relay=relay)
    return call(token), cached


# --- commands ----------------------------------------------------------------------


def cmd_token(args: argparse.Namespace, config: Config) -> str:
    token, _ = current_token(args.identity, config, relay=relay_of(args).relay)
    return token


def cmd_headers(args: argparse.Namespace, config: Config) -> str:
    token, _ = current_token(args.identity, config, relay=relay_of(args).relay)
    return json.dumps({"Authorization": "Bearer " + token})


def visible_teams(token: str) -> list[str]:
    """The keys of the teams the token's app user can see, read from Linear."""
    keys: list[str] = []
    after: str | None = None
    for _ in range(TEAM_PAGES):
        teams: object = graphql(token, TEAMS_QUERY, variables={"after": after}).get("teams")
        if not isinstance(teams, dict):
            raise Failure("Linear's answer held no teams")
        nodes: object = as_dict(teams).get("nodes")
        page = as_dict(as_dict(teams).get("pageInfo"))
        if not isinstance(nodes, list):
            raise Failure("Linear's answer held no list of teams")
        for node in as_list(nodes):
            key: object = as_dict(node).get("key")
            if isinstance(key, str):
                keys.append(key)
        cursor: object = page.get("endCursor")
        if not (page.get("hasNextPage") and isinstance(cursor, str)):
            return keys
        after = cursor
    raise Failure(f"Linear listed more than {TEAM_PAGES} pages of teams")


def cmd_check(args: argparse.Namespace, config: Config) -> dict[str, Any]:
    token_used: list[str] = []

    def viewer(token: str) -> dict[str, Any]:
        token_used.append(token)
        return graphql(token, VIEWER_QUERY)

    data, cached = with_token(args, config, viewer)
    viewer_data: Config = data.get("viewer") or {}
    org: Config = data.get("organization") or {}
    result: dict[str, Any] = {
        "identity": args.identity,
        "user": viewer_data.get("name"),
        "userId": viewer_data.get("id"),
        "workspace": {"name": org.get("name"), "urlKey": org.get("urlKey")},
        "scopes": cached["scopes"],
        "grantedScopes": cached.get("grantedScopes"),
        "canBeDelegate": "app:assignable" in cached["scopes"].split(","),
        "tokenDaysLeft": max(0, int((cached["expiresAt"] - time.time()) // 86400)),
    }
    expected = config.get("workspace")
    if expected and expected not in (org.get("urlKey"), org.get("name")):
        raise Failure(f"identity {args.identity!r} belongs to workspace {org.get('urlKey')!r}, "
                      f"but its config expects {expected!r}")
    try:
        result["visibleTeams"] = visible_teams(token_used[-1])
    except Failure as e:
        result["visibleTeamsError"] = f"could not read the teams the app user can see: {e}"
    for key in ("teams", "people", "notes"):
        if config.get(key):
            result[key] = config[key]
    warnings = stale_helpers(args.identity)
    if relay_of(args).relay:
        warnings += relay_helpers(args.identity)
    if result["grantedScopes"] is None:
        warnings.append("Linear's token response named no scopes, so grantedScopes is null")
    if warnings:
        result["warnings"] = warnings
    return result


def cmd_store_credentials(args: argparse.Namespace, config: Config) -> dict[str, Any]:
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
    stored: dict[str, Any] = {"identity": args.identity, "stored": True, "service": service}
    if not relay_of(args).relay and env_overrides_keychain(args.identity):
        stored["warnings"] = [ENV_OVERRIDE_WARNING]
    return stored


def stable_script(home: str | None = None, current: str | None = None) -> str:
    """This script's path under an installed skill folder, when it leads here, else the file itself.

    Installed skills are links into a clone; manage-skills repairs those links
    when the clone moves, so a command naming the link keeps working.
    """
    current = os.path.abspath(current or __file__)
    home = home or os.path.expanduser("~")
    for target in (".claude", ".agents"):
        candidate = os.path.join(home, target, "skills", "linear-app", "scripts", os.path.basename(current))
        if os.path.exists(candidate) and os.path.realpath(candidate) == os.path.realpath(current):
            return candidate
    return current


def helper_command(identity: str, script: str | None = None, python: str | None = None) -> str:
    script = script or stable_script()
    python = python or sys.executable
    return " ".join(shlex.quote(p) for p in (python, script, "--identity", identity, "headers"))


def wired_servers(identity: str, path: str | None = None) -> Iterator[tuple[str, str | None, list[str]]]:
    """(server name, project folder or None for every session, headersHelper split into words)
    for each Claude Code MCP server whose headersHelper runs this script for this identity."""
    # Claude Code keeps its config in CLAUDE_CONFIG_DIR when that is set.
    path = path or os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~"), ".claude.json")
    try:
        with open(path, encoding="utf-8") as f:
            claude: object = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(claude, dict):
        return
    settings = as_dict(claude)
    tables: list[tuple[object, str | None]] = [(settings.get("mcpServers"), None)]
    # A project whose folder is gone starts no session, so its servers can't fail.
    for folder, project in as_dict(settings.get("projects")).items():
        if isinstance(project, dict) and os.path.isdir(folder):
            tables.append((as_dict(project).get("mcpServers"), folder))
    for servers, folder in tables:
        if not isinstance(servers, dict):
            continue
        for name, server in as_dict(servers).items():
            helper: object = as_dict(server).get("headersHelper")
            try:
                words = shlex.split(helper) if isinstance(helper, str) else []
            except ValueError:
                continue
            if len(words) < 4 or not words[1].endswith("linear_app.py") or words[2:4] != ["--identity", identity]:
                continue
            yield name, folder, words


def stale_helpers(identity: str, path: str | None = None) -> list[str]:
    """Warnings for Claude Code servers wired to this identity whose helper can't run."""
    warnings: list[str] = []
    for name, folder, words in wired_servers(identity, path):
        # As the shell would find them: a bare name on PATH, and ~ expanded.
        interpreter = shutil.which(words[0]) if "/" not in words[0] else os.path.expanduser(words[0])
        missing = [w for w, found in ((words[0], interpreter), (words[1], os.path.expanduser(words[1])))
                   if not found or not os.path.exists(found)]
        if missing:
            rewire = [sys.executable, stable_script(), "--identity", identity, "wire", "--name", name]
            if folder:
                rewire += ["--project", folder]
            warnings.append(f"the {name!r} MCP server runs {missing[0]}, which no longer exists, so Linear "
                            f"fails at session start; run: {shlex.join(rewire)}")
    return warnings


def relay_helpers(identity: str, path: str | None = None) -> list[str]:
    """Warnings for Claude Code servers whose helper runs `headers` for this relay identity."""
    return [f"the {name!r} MCP server{f' for {folder}' if folder else ''} is wired to relay identity "
            f"{identity!r}, whose headers refuses, so Linear fails in its sessions; wire another identity to it"
            for name, folder, words in wired_servers(identity, path) if "headers" in words[4:]]


def cmd_wire(args: argparse.Namespace, config: Config, run: Runner = subprocess.run,
             which: Which = shutil.which) -> dict[str, Any]:
    if relay_of(args).relay:
        raise Failure(posts_only_through_commands(args.identity, relay_of(args)) + "; no MCP server was changed")
    if not which("claude"):
        raise Failure("'claude' is not on PATH; wiring is for Claude Code. Other MCP clients: see the README")
    current_token(args.identity, config)  # fail now, not at the next session start
    scope = "local" if args.project else "user"
    cwd = os.path.abspath(args.project) if args.project else None
    if cwd and not os.path.isdir(cwd):
        raise Failure(f"--project {args.project!r} is not a folder")
    server = json.dumps({"type": "http", "url": MCP_URL, "headersHelper": helper_command(args.identity)})

    def claude(*cmd: str) -> Any:
        result = run(["claude", "mcp", *cmd], cwd=cwd, capture_output=True, text=True)
        return result.returncode == 0 or result

    def add(name: str) -> None:
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
    wired: dict[str, Any] = {"identity": args.identity, "server": args.name, "scope": scope, "restartNeeded": True}
    if cwd:
        wired["project"] = cwd
    return wired


def cmd_forget(args: argparse.Namespace, config: Config) -> dict[str, Any]:
    service, id_account, secret_account = keychain_entries(args.identity, config)
    forgotten: dict[str, Any] = {"identity": args.identity, "forgotten": True}
    left_over: list[str] = []  # own entries that may still be stored
    found: list[str] = []  # of those, the ones the read-back actually found
    if service == KEYCHAIN_SERVICE:
        for account in (id_account, secret_account):
            # A failed delete counts even when the read-back finds nothing: a
            # locked keychain fails the read too.
            deleted = delete_keychain(service, account) is not False
            if read_keychain(service, account):
                found.append(account)
            elif deleted:
                continue
            left_over.append(account)
    else:  # entries another tool made, which it may still use
        forgotten["keptKeychain"] = {"service": service, "accounts": [id_account, secret_account]}
    # A relay identity's token is cached in the keychain; an identity that was
    # one before may have left it there, so it is deleted whatever the identity is now.
    token_left = delete_keychain(KEYCHAIN_SERVICE, token_account(args.identity)) is False
    path = cache_path(args.identity)
    for p in (path, path + ".lock"):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    # Report what is actually left, not what should be: check each source directly.
    sources: list[str] = []
    warnings: list[str] = []
    half_pair, unsure = False, False
    if not relay_of(args).relay and env_overrides_keychain(args.identity):
        if os.environ.get("LINEAR_CLIENT_ID", "").strip() and os.environ.get("LINEAR_CLIENT_SECRET", "").strip():
            sources.append("the environment (LINEAR_CLIENT_ID/LINEAR_CLIENT_SECRET)")
        else:
            half_pair = True
            warnings.append("only one of LINEAR_CLIENT_ID/LINEAR_CLIENT_SECRET is set in the environment; unset it")
    for account in left_over:
        warnings.append(f"could not delete keychain entry {account} in service {service!r} "
                        "(a locked keychain or a denied prompt?)")
    if token_left:
        warnings.append(f"could not delete the cached token, keychain entry {token_account(args.identity)} in "
                        f"service {KEYCHAIN_SERVICE!r} (a locked keychain or a denied prompt?)")
    if len(found) == 2:
        sources.append(f"the keychain entries in service {service!r}, which the delete did not remove")
    elif len(left_over) == 2:  # the keychain could not be read, so they may or may not be there
        unsure = True
        sources.append(f"the keychain entries in service {service!r}, which may still be stored")
    elif service != KEYCHAIN_SERVICE and read_keychain(service, id_account) and read_keychain(service, secret_account):
        sources.append(f"the keychain entries in service {service!r}, which forget keeps")
    keychain_only = unsure and len(sources) == 1
    if sources and half_pair:  # the half pair blocks the keychain until it is unset
        warnings.append(("once it is unset, this identity may work again from " if unsure
                         else "once it is unset, this identity works again from ") + " and ".join(sources))
    elif keychain_only:
        warnings.append("this identity may still have credentials, and works again once the keychain "
                        "is reachable, from " + sources[0])
    elif sources:
        warnings.append("this identity still has credentials and keeps working, from " + " and ".join(sources))
    if warnings:
        forgotten["warnings"] = warnings
    return forgotten


# --- post, edit and delete -----------------------------------------------------------

BODY_FILE_ONLY = ("name the text's file with --body-file <file>, given once and spelled in full: "
                  "linear-app reads a comment's text only from a regular file, never from standard input, "
                  "so the post hooks read exactly the text it sends")
COMMENT_CREATE = ("mutation($input: CommentCreateInput!) "
                  "{ commentCreate(input: $input) { success comment { id url } } }")
COMMENT_UPDATE = ("mutation($id: String!, $input: CommentUpdateInput!) "
                  "{ commentUpdate(id: $id, input: $input) { success comment { id url } } }")
COMMENT_DELETE = "mutation($id: String!) { commentDelete(id: $id) { success } }"


def body_file_refusal(argv: list[str]) -> str | None:
    """Why a post or edit call's options do not name its text's file exactly
    once and in full, or None. argparse would keep the last of two
    `--body-file` options while the inquisitor's post hook reads another, and
    reject `--body` without naming `--body-file`; so both are refused here,
    saying to use `--body-file`."""
    i = 0
    while i < len(argv) and argv[i] not in ("post", "edit"):
        i += 2 if argv[i] == "--identity" else 1
    if i >= len(argv):
        return None
    given = 0
    for arg in argv[i + 1:]:
        if arg == "--":
            break
        name = arg.split("=", 1)[0]
        if name == "--body-file":
            given += 1
        elif name.startswith("--b") and "--body-file".startswith(name):
            return f"{name} is not --body-file spelled in full; {BODY_FILE_ONLY}"
    if given > 1:
        return f"--body-file is given {given} times; {BODY_FILE_ONLY}"
    return None


DEVICE_DIRS = ("/dev/", "/proc/")


def names_a_device(path: str) -> bool:
    """Whether the path, or any link it leads through, is under /dev or /proc.

    /dev/stdin and /dev/fd/0 reach a regular file whenever standard input is
    a redirect or a zsh heredoc, so a regular-file check alone lets standard
    input through, while a hook opening the same path reads the hook's own
    standard input, not the text sent.
    """
    hop = os.path.abspath(path)
    for _ in range(40):  # the kernel's own limit on links followed
        if hop.startswith(DEVICE_DIRS):
            return True
        if not os.path.islink(hop):
            break
        hop = os.path.normpath(os.path.join(os.path.dirname(hop), os.readlink(hop)))
    return os.path.realpath(path).startswith(DEVICE_DIRS)


def read_body(path: str | None) -> str:
    """The text of the regular file `--body-file` names."""
    if not path:
        raise Failure(BODY_FILE_ONLY)
    if names_a_device(path):
        raise Failure(f"--body-file {path} names a device, such as standard input; {BODY_FILE_ONLY}")
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            raise Failure(f"--body-file {path} is not a regular file; {BODY_FILE_ONLY}")
        # O_NONBLOCK: a FIFO swapped in after the check would otherwise block the open.
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except OSError as e:
        raise Failure(f"cannot read --body-file {path}: {e.strerror or e}")
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise Failure(f"--body-file {path} is not a regular file; {BODY_FILE_ONLY}")
        raw = f.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Failure(f"--body-file {path} is not UTF-8 text")


def mutation_result(data: dict[str, Any], field: str) -> dict[str, Any]:
    """The mutation's payload; a Failure when Linear does not report success."""
    payload: object = data.get(field)
    if as_dict(payload).get("success") is not True:
        raise Failure(f"Linear did not report {field} as a success", status=200, errors=[])
    return as_dict(payload)


def comment_fields(payload: dict[str, Any]) -> dict[str, Any]:
    comment: Config = payload.get("comment") or {}
    return {"id": comment.get("id"), "url": comment.get("url")}


def cmd_post(args: argparse.Namespace, config: Config) -> dict[str, Any]:
    comment_input: dict[str, Any] = {"issueId": args.issue, "body": read_body(args.body_file)}
    if args.parent:
        comment_input["parentId"] = args.parent
    data, _ = with_token(args, config, lambda token: graphql(token, COMMENT_CREATE,
                                                              variables={"input": comment_input}))
    return {"identity": args.identity, **comment_fields(mutation_result(data, "commentCreate"))}


def cmd_edit(args: argparse.Namespace, config: Config) -> dict[str, Any]:
    variables = {"id": args.comment, "input": {"body": read_body(args.body_file)}}
    data, _ = with_token(args, config, lambda token: graphql(token, COMMENT_UPDATE, variables=variables))
    return {"identity": args.identity, **comment_fields(mutation_result(data, "commentUpdate"))}


def cmd_delete(args: argparse.Namespace, config: Config) -> dict[str, Any]:
    data, _ = with_token(args, config, lambda token: graphql(token, COMMENT_DELETE, variables={"id": args.comment}))
    mutation_result(data, "commentDelete")
    return {"identity": args.identity, "id": args.comment}


# --- command line ------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="linear_app.py", description="Act on Linear as an OAuth app user.",
                                allow_abbrev=False)
    p.add_argument("--identity", help="which app user to act as (default: $LINEAR_APP_IDENTITY, else 'default')")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("token", help="print a valid access token, minting one if needed; refused for a relay identity",
                   allow_abbrev=False)
    sub.add_parser("headers", help="print the Authorization header as JSON, for an MCP headersHelper; "
                   "refused for a relay identity", allow_abbrev=False)
    sub.add_parser("check", help="show who the token acts as, and what it may do", allow_abbrev=False)
    sub.add_parser("store-credentials", help="save this identity's client ID and secret in the keychain",
                   allow_abbrev=False)
    w = sub.add_parser("wire", help="point Claude Code's Linear MCP server at this identity; "
                       "refused for a relay identity", allow_abbrev=False)
    w.add_argument("--project", help="only for sessions started in this folder (default: every session)")
    w.add_argument("--name", default="linear", help="the MCP server's name (default: linear)")
    sub.add_parser("forget", help="delete this identity's stored credentials and cached token", allow_abbrev=False)
    po = sub.add_parser("post", help="comment on an issue, or reply in a comment's thread", allow_abbrev=False)
    po.add_argument("--issue", required=True, help="the issue's id or identifier, such as ENG-5")
    po.add_argument("--parent", help="the comment whose thread the reply goes in")
    po.add_argument("--body-file", help="the regular file holding the comment's text")
    ed = sub.add_parser("edit", help="replace a comment's text", allow_abbrev=False)
    ed.add_argument("--comment", required=True, help="the comment's id")
    ed.add_argument("--body-file", help="the regular file holding the comment's new text")
    de = sub.add_parser("delete", help="delete a comment", allow_abbrev=False)
    de.add_argument("--comment", required=True, help="the comment's id")
    return p


COMMANDS: dict[str, Callable[[argparse.Namespace, Config], Any]] = {
    "token": cmd_token,
    "headers": cmd_headers,
    "check": cmd_check,
    "store-credentials": cmd_store_credentials,
    "wire": cmd_wire,
    "forget": cmd_forget,
    "post": cmd_post,
    "edit": cmd_edit,
    "delete": cmd_delete,
}
RAW_OUTPUT = {"token", "headers"}  # printed bare, for $(...) and headersHelper
PRINTS_TOKEN = {"token", "headers"}


def guard_relay(args: argparse.Namespace) -> None:
    """Before any command runs for a relay identity: delete its state-folder
    token; refuse token and headers; and, when the host has no keychain
    tool, refuse every command but forget. wire is left to cmd_wire, which
    refuses a relay identity. While inquisitor.json names an invalid relay,
    refuse token, headers and wire for every identity."""
    relay = relay_of(args)
    if not relay.relay:
        if relay.warning and args.command in PRINTS_TOKEN | {"wire"}:
            raise Failure(relay.warning)
        return
    drop_file_cache(args.identity)
    if args.command == "forget":
        return
    if keychain_tool() is None:
        raise Failure(f"identity {args.identity!r} is a relay identity ({relay.why}), and {NO_KEYCHAIN_TOOL}: "
                      "its credentials and token live only in the keychain, so every command but forget is refused")
    if args.command in PRINTS_TOKEN:
        raise Failure(posts_only_through_commands(args.identity, relay))


def with_relay_warning(args: argparse.Namespace, output: dict[str, Any]) -> dict[str, Any]:
    """Add any fault in inquisitor.json the person must fix to output's warnings,
    in place, unless the warnings or the error already hold it; return output."""
    warning = relay_of(args).warning
    warnings = [str(w) for w in as_list(output.get("warnings"))]
    if warning and warning not in warnings and warning not in str(output.get("error", "")):
        output["warnings"] = warnings + [warning]
    return output


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    refusal = body_file_refusal(argv)
    if refusal:
        print(json.dumps({"ok": False, "error": refusal}))
        return 1
    args = parser().parse_args(argv)
    try:
        args.identity = resolve_identity(args.identity)
        config = load_config(args.identity)
        args.relay = relay_status(args.identity, config)
        guard_relay(args)
        result = COMMANDS[args.command](args, config)
    except Failure as e:
        if args.command in RAW_OUTPUT:
            print(f"linear_app: {e}", file=sys.stderr)
        else:
            failed: dict[str, Any] = {"ok": False, "error": str(e)}
            if e.status is not None:
                failed["status"] = e.status
            if e.errors is not None:
                failed["errors"] = e.errors
            print(json.dumps(with_relay_warning(args, failed)))
        return 1
    except Exception as e:  # callers parse stdout, so even a bug answers predictably
        import traceback
        traceback.print_exc()
        if args.command not in RAW_OUTPUT:
            print(json.dumps({"ok": False, "error": f"unexpected error: {e!r}"}))
        return 1
    print(result if args.command in RAW_OUTPUT else json.dumps(with_relay_warning(args, {"ok": True, **result})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
