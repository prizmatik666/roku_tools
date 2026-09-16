#!/usr/bin/env python3

import ipaddress
import socket
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


# ============================================================
# CONFIGURATION
# ============================================================

PORT = 8060

HOME_SETTLE = 2.5
SEARCH_SETTLE = 1.5

# Delay between individual ECP keypresses.
KEY_DELAY = 0.12

# Individual HTTP request timeout.
HTTP_TIMEOUT = 3.0

# State-query retries are safe because GET requests do not move
# the Roku cursor.
QUERY_RETRIES = 2
QUERY_RETRY_DELAY = 0.50


# ============================================================
# ROKU SEARCH KEYBOARD
# ============================================================

# Keyboard mapped from the Roku search screen:
#
#       COL
#       0 1 2 3 4 5
#     +------------
# R 0 | a b c d e f
# O 1 | g h i j k l
# W 2 | m n o p q r
#   3 | s t u v w x
#   4 | y z 1 2 3 4
#   5 | 5 6 7 8 9 0
#
# Bottom special row:
#
#       [ DELETE ] [ SPACE ] [ BACKSPACE ]
#
# The special row is intentionally not mapped yet because its
# controls span multiple columns and need one navigation test.

KEYBOARD_ROWS = (
    "abcdef",
    "ghijkl",
    "mnopqr",
    "stuvwx",
    "yz1234",
    "567890",
)

KEYBOARD = {
    char: (row, col)
    for row, chars in enumerate(KEYBOARD_ROWS)
    for col, char in enumerate(chars)
}


# ============================================================
# ECP KEY NAMES
# ============================================================

ECP = {
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "OK": "Select",
    "HOME": "Home",
}


# ============================================================
# EXCEPTIONS
# ============================================================

class RokuError(Exception):
    """Base error for controlled Roku failures."""
    pass


class RokuTransportError(RokuError):
    """Network/ECP transport failure."""
    pass


class RokuDesyncError(RokuError):
    """
    Raised when a keypress fails ambiguously.

    The Roku may or may not have processed the failed command,
    so our internal cursor state can no longer be trusted.
    """
    pass


# ============================================================
# UI
# ============================================================

def banner():
    print(r"""
╭──────────────────────────────────────────╮
│          ROKU TEXT ROUTER                │
│     ECP keyboard path automation         │
╰──────────────────────────────────────────╯
""")


# ============================================================
# INPUT
# ============================================================

def normalize_ip(value):
    value = value.strip()

    try:
        return str(ipaddress.ip_address(value))

    except ValueError as exc:
        raise RokuError(
            f"Invalid Roku IP address: {value}"
        ) from exc


# ============================================================
# HTTP / ECP TRANSPORT
# ============================================================

def request(
    ip,
    method,
    path,
    *,
    retries=0,
    retry_delay=QUERY_RETRY_DELAY,
):
    """
    Send an HTTP request to the Roku ECP interface.

    IMPORTANT:

    retries should normally ONLY be used for safe observational
    requests such as GET /query/active-app.

    Keypress POST requests intentionally use retries=0 because a
    timeout is ambiguous:

        POST /keypress/Right
              |
              +-- Roku may NOT have processed it
              |
              +-- Roku MAY have processed it but the HTTP response
                  was lost/delayed

    Repeating that request could therefore move the cursor twice.
    """

    url = f"http://{ip}:{PORT}{path}"

    attempts = retries + 1
    last_error = None

    for attempt in range(1, attempts + 1):

        req = urllib.request.Request(
            url,
            method=method,
            headers={
                "User-Agent": "roku-text-router/1.1",
                "Connection": "close",
            },
        )

        try:
            with urllib.request.urlopen(
                req,
                timeout=HTTP_TIMEOUT,
            ) as response:

                status = response.getcode()

                if status < 200 or status >= 300:
                    raise RokuTransportError(
                        f"{method} {path} returned HTTP {status}"
                    )

                return response.read()

        except urllib.error.HTTPError as exc:
            last_error = exc

            # HTTP errors are deterministic responses from the Roku.
            # Retrying generally isn't useful.
            raise RokuTransportError(
                f"{method} {path} returned "
                f"HTTP {exc.code}: {exc.reason}"
            ) from exc

        except (
            urllib.error.URLError,
            socket.timeout,
            TimeoutError,
            ConnectionError,
            OSError,
        ) as exc:

            last_error = exc

            if attempt < attempts:
                print()
                print(
                    f"[!] ECP request failed "
                    f"({attempt}/{attempts})"
                )
                print(
                    f"    {method} {path}"
                )
                print(
                    f"    Cause: {exc}"
                )
                print(
                    f"[>] Retrying in "
                    f"{retry_delay:.2f}s..."
                )

                time.sleep(retry_delay)
                continue

            raise RokuTransportError(
                f"{method} {path} failed after "
                f"{attempts} attempt"
                f"{'s' if attempts != 1 else ''}: "
                f"{exc}"
            ) from exc

    # Defensive fallback. Normally unreachable.
    raise RokuTransportError(
        f"{method} {path} failed: {last_error}"
    )


# ============================================================
# ECP KEYPRESSES
# ============================================================

def keypress(ip, key, delay=True):
    """
    Send exactly ONE ECP keypress.

    Keypresses are deliberately NOT retried.

    If a POST times out, we cannot know whether Roku processed
    the command. Retrying could cause a double movement.
    """

    if key not in ECP:
        raise RokuError(
            f"Unknown internal key command: {key}"
        )

    ecp_key = ECP[key]

    request(
        ip,
        "POST",
        f"/keypress/{ecp_key}",
        retries=0,
    )

    if delay:
        time.sleep(KEY_DELAY)


# ============================================================
# ACTIVE APP / STATE
# ============================================================

def active_app(ip):
    """
    Query current Roku application/state.

    Safe to retry because this is observational and cannot move
    the keyboard cursor.
    """

    data = request(
        ip,
        "GET",
        "/query/active-app",
        retries=QUERY_RETRIES,
    )

    try:
        return ET.fromstring(data)

    except ET.ParseError as exc:
        raise RokuError(
            "Roku returned invalid XML for "
            "/query/active-app"
        ) from exc


def describe_active_app(root):
    app = root.find("app")

    if app is None:
        return "(unknown)"

    text = (app.text or "").strip()

    attrs = " ".join(
        f'{key}="{value}"'
        for key, value in app.attrib.items()
    )

    return f"{attrs} {text}".strip()


def is_home(root):
    app = root.find("app")

    if app is None:
        return False

    attrs = {
        str(key).lower(): str(value).lower()
        for key, value in app.attrib.items()
    }

    text = (app.text or "").strip().lower()

    # Roku firmware/platform variants expose Home somewhat
    # differently.

    if attrs.get("type") == "home":
        return True

    if attrs.get("ui-location") == "home":
        return True

    if "roku dynamic menu" in text:
        return True

    if text == "home":
        return True

    return False


# ============================================================
# HOME RESET
# ============================================================

def reset_to_home(ip):
    """
    Establish a deterministic starting state.

    Home itself is a state-reset command. If it succeeds, wait
    for the UI and verify /query/active-app before proceeding.
    """

    print("[>] Sending Home...")

    try:
        keypress(
            ip,
            "HOME",
            delay=False,
        )

    except RokuTransportError as exc:
        # Home has the same ambiguous POST-response problem as
        # other keys, but unlike keyboard movement we can safely
        # inspect state before deciding what to do.
        print(
            f"[!] Home ECP response failed: {exc}"
        )
        print(
            "[>] Checking whether Roku reached Home anyway..."
        )

    time.sleep(HOME_SETTLE)

    root = active_app(ip)
    description = describe_active_app(root)

    if is_home(root):
        print(
            f"[✓] Home confirmed: {description}"
        )
        return

    print(
        f"[!] Active state after Home: {description}"
    )
    print("[>] Sending Home again...")

    try:
        keypress(
            ip,
            "HOME",
            delay=False,
        )

    except RokuTransportError as exc:
        print(
            f"[!] Second Home response failed: {exc}"
        )
        print(
            "[>] Verifying actual Roku state..."
        )

    time.sleep(HOME_SETTLE)

    root = active_app(ip)
    description = describe_active_app(root)

    if not is_home(root):
        raise RokuError(
            "Could not establish deterministic Home state.\n"
            f"Current Roku state: {description}"
        )

    print(
        f"[✓] Home confirmed: {description}"
    )


# ============================================================
# OPEN SEARCH
# ============================================================

def open_search(ip):
    """
    User-confirmed Roku navigation:

        Home
          ↓
        Left
          ↓
        Down × 5
          ↓
        OK

    Search keyboard then opens with focus on:

        a = (0,0)
    """

    sequence = [
        "LEFT",
        "DOWN",
        "DOWN",
        "DOWN",
        "DOWN",
        "DOWN",
        "OK",
    ]

    print("[>] Opening Search...")

    total = len(sequence)

    for number, key in enumerate(
        sequence,
        start=1,
    ):
        try:
            keypress(ip, key)

        except RokuTransportError as exc:
            raise RokuDesyncError(
                "Search navigation was interrupted.\n"
                f"Failed command: {number}/{total} {key}\n"
                "The Roku's current menu position is unknown.\n"
                "Restart the script to reset from Home.\n"
                f"Cause: {exc}"
            ) from exc

    time.sleep(SEARCH_SETTLE)

    print("[✓] Search navigation sent")
    print("[✓] Keyboard origin: a (0,0)")


# ============================================================
# ROUTING
# ============================================================

def route_between(current, target):
    """
    Generate movement between two character coordinates.

    Routing policy:

        1. vertical movement
        2. horizontal movement

    Keyboard wrapping is deliberately NOT assumed.
    """

    current_row, current_col = current
    target_row, target_col = target

    commands = []

    row_delta = target_row - current_row
    col_delta = target_col - current_col

    if row_delta < 0:
        commands.extend(
            ["UP"] * abs(row_delta)
        )

    elif row_delta > 0:
        commands.extend(
            ["DOWN"] * row_delta
        )

    if col_delta < 0:
        commands.extend(
            ["LEFT"] * abs(col_delta)
        )

    elif col_delta > 0:
        commands.extend(
            ["RIGHT"] * col_delta
        )

    return commands


# ============================================================
# PAYLOAD COMPILATION
# ============================================================

def build_route(message):
    """
    Compile the COMPLETE message into a movement route before
    touching the Roku.

    This guarantees that an unsupported character cannot cause
    half of a message to be transmitted.

    Initial keyboard position:

        a = (0,0)
    """

    message = message.lower()

    if not message:
        raise RokuError(
            "Message cannot be empty."
        )

    unsupported = sorted({
        char
        for char in message
        if char not in KEYBOARD
        and char != " "
    })

    if unsupported:
        pretty = ", ".join(
            repr(char)
            for char in unsupported
        )

        raise RokuError(
            "Unsupported character(s): "
            f"{pretty}\n"
            "Current mapped payload alphabet: "
            "a-z, 0-9.\n"
            "Space requires the special bottom-row key."
        )

    current = KEYBOARD["a"]
    route = []

    for char in message:

        # Space remains disabled until the bottom-row geometry
        # is verified on the Roku.
        if char == " ":
            raise RokuError(
                "Space detected.\n"
                "Letters and numbers are fully mapped, but "
                "the wide Space key requires one navigation "
                "test before enabling spaces."
            )

        target = KEYBOARD[char]

        movement = route_between(
            current,
            target,
        )

        commands = movement + ["OK"]

        route.append({
            "char": char,
            "from": current,
            "to": target,
            "movement": movement,
            "commands": commands,
        })

        current = target

    return route


# ============================================================
# ROUTE PREVIEW
# ============================================================

def print_route(route):
    print()
    print("Payload route")
    print("─" * 70)

    total_inputs = 0
    movement_inputs = 0
    select_inputs = 0

    for number, step in enumerate(
        route,
        start=1,
    ):

        movement = step["movement"]

        if movement:
            path = " ".join(
                movement + ["OK"]
            )
        else:
            # Repeated character.
            path = "OK"

        print(
            f"{number:>3}. "
            f"{step['char']!r:<4} "
            f"{step['from']} → {step['to']}   "
            f"{path}"
        )

        total_inputs += len(
            step["commands"]
        )

        movement_inputs += len(
            movement
        )

        select_inputs += 1

    print("─" * 70)
    print(
        f"Characters      : {len(route)}"
    )
    print(
        f"Movement inputs : {movement_inputs}"
    )
    print(
        f"Select inputs   : {select_inputs}"
    )
    print(
        f"Total ECP inputs: {total_inputs}"
    )

    estimated = (
        total_inputs * KEY_DELAY
    )

    print(
        f"Minimum send time: ~{estimated:.1f}s "
        f"(plus HTTP latency)"
    )

    print()


# ============================================================
# PAYLOAD TRANSMISSION
# ============================================================

def transmit(ip, route):
    """
    Transmit the precompiled route.

    If ANY keypress fails, stop immediately.

    We deliberately do NOT retry because the Roku may have
    processed the command even though its HTTP response failed.
    Continuing would risk desynchronizing our internal cursor
    position from the actual television cursor.
    """

    total_chars = len(route)

    print("[>] Sending payload...")

    completed = 0

    for number, step in enumerate(
        route,
        start=1,
    ):

        commands = step["commands"]
        total_commands = len(commands)

        for command_number, command in enumerate(
            commands,
            start=1,
        ):

            try:
                keypress(
                    ip,
                    command,
                )

            except RokuTransportError as exc:

                print()

                raise RokuDesyncError(
                    "\n"
                    "PAYLOAD TRANSMISSION INTERRUPTED\n"
                    "────────────────────────────────────\n"
                    f"Character     : {number}/{total_chars}\n"
                    f"Target        : {step['char']!r}\n"
                    f"Expected from : {step['from']}\n"
                    f"Expected to   : {step['to']}\n"
                    f"Command       : "
                    f"{command_number}/{total_commands} "
                    f"{command}\n"
                    f"Completed chars: {completed}\n"
                    "\n"
                    "The failed ECP command may or may not "
                    "have been processed by the Roku.\n"
                    "Cursor state is therefore considered "
                    "UNKNOWN.\n"
                    "\n"
                    "Do not continue from the current cursor.\n"
                    "Restart the script so Home -> Search -> "
                    "a establishes a clean state.\n"
                    "\n"
                    f"Transport error: {exc}"
                ) from exc

        completed = number

        print(
            f"\r[>] Character "
            f"{number}/{total_chars}: "
            f"{step['char']!r} "
            f"({step['to'][0]},{step['to'][1]})",
            end="",
            flush=True,
        )

    print()
    print(
        f"[✓] Payload complete "
        f"({total_chars}/{total_chars} characters)"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    banner()

    try:
        roku_ip = normalize_ip(
            input("Roku IP : ")
        )

        message = input(
            "Message : "
        )

        print()
        print("[>] Validating payload...")

        # Compile everything before making any Roku state
        # changes.
        route = build_route(
            message
        )

        print("[✓] Payload valid")

        print_route(
            route
        )

        answer = input(
            "Send to Roku? [Y/n]: "
        ).strip().lower()

        if answer not in (
            "",
            "y",
            "yes",
        ):
            print("[!] Cancelled.")
            return 0

        print()
        print(
            f"[>] Connecting to "
            f"{roku_ip}:{PORT}..."
        )

        # Safe initial connectivity/state query.
        root = active_app(
            roku_ip
        )

        print(
            "[✓] Roku reachable: "
            + describe_active_app(root)
        )

        print(
            f"[i] ECP timeout : {HTTP_TIMEOUT:.1f}s"
        )
        print(
            f"[i] Key delay   : {KEY_DELAY:.2f}s"
        )

        # Establish deterministic state.
        reset_to_home(
            roku_ip
        )

        # Navigate to keyboard origin.
        open_search(
            roku_ip
        )

        # Send compiled payload.
        transmit(
            roku_ip,
            route,
        )

        return 0

    except KeyboardInterrupt:
        print()
        print("[!] Interrupted by user.")
        print(
            "[!] Roku cursor state may be unknown."
        )
        return 130

    except RokuDesyncError as exc:
        print(
            f"\n[✗] {exc}",
            file=sys.stderr,
        )
        return 2

    except RokuTransportError as exc:
        print(
            f"\n[✗] Roku transport error: {exc}",
            file=sys.stderr,
        )
        return 1

    except RokuError as exc:
        print(
            f"\n[✗] {exc}",
            file=sys.stderr,
        )
        return 1

    except Exception as exc:
        # Last-resort clean failure instead of dumping a giant
        # traceback during normal use. The exception class is
        # retained so genuinely unexpected bugs are identifiable.
        print(
            f"\n[✗] Unexpected error "
            f"({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
