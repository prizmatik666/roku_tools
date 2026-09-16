#!/usr/bin/env python3

import curses
import time
import urllib.parse
import urllib.request
import urllib.error


COMMON_KEYS = [
    "Home", "Back", "Up", "Down", "Left", "Right", "Select",
    "Rev", "Fwd", "Play", "InstantReplay", "Info", "Backspace",
    "Search", "Enter", "VolumeDown", "VolumeMute", "VolumeUp",
    "PowerOff", "PowerOn", "ChannelUp", "ChannelDown",
]

ALIASES = {
    "h": "Home",
    "home": "Home",
    "b": "Back",
    "back": "Back",
    "u": "Up",
    "up": "Up",
    "d": "Down",
    "down": "Down",
    "l": "Left",
    "left": "Left",
    "r": "Right",
    "right": "Right",
    "ok": "Select",
    "select": "Select",
    "enter": "Enter",
    "play": "Play",
    "pause": "Play",
    "rewind": "Rev",
    "rev": "Rev",
    "fastforward": "Fwd",
    "ff": "Fwd",
    "fwd": "Fwd",
    "replay": "InstantReplay",
    "instantreplay": "InstantReplay",
    "info": "Info",
    "search": "Search",
    "bs": "Backspace",
    "backspace": "Backspace",
    "volup": "VolumeUp",
    "voldown": "VolumeDown",
    "mute": "VolumeMute",
    "poweroff": "PowerOff",
    "poweron": "PowerOn",
    "chup": "ChannelUp",
    "chdown": "ChannelDown",
}


class RokuECPClient:
    def __init__(self, roku_ip: str, timeout: float = 3.0):
        self.roku_ip = roku_ip.strip()
        self.timeout = timeout

    @property
    def base(self) -> str:
        return f"http://{self.roku_ip}:8060"

    def post(self, path: str) -> tuple[bool, str]:
        url = self.base + path
        req = urllib.request.Request(url, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                code = getattr(resp, "status", 200)
                return True, f"POST {path} -> HTTP {code}"
        except urllib.error.HTTPError as e:
            return False, f"HTTPError {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return False, f"URLError: {e.reason}"
        except Exception as e:
            return False, f"Error: {e}"

    def get_text(self, path: str) -> tuple[bool, str]:
        url = self.base + path
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                return True, data
        except urllib.error.HTTPError as e:
            return False, f"HTTPError {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return False, f"URLError: {e.reason}"
        except Exception as e:
            return False, f"Error: {e}"

    def keypress(self, key: str) -> tuple[bool, str]:
        return self.post(f"/keypress/{urllib.parse.quote(key)}")

    def literal(self, text: str) -> tuple[bool, str]:
        return self.post(f"/keypress/Lit_{urllib.parse.quote(text)}")

    def launch(self, app_id: str) -> tuple[bool, str]:
        return self.post(f"/launch/{urllib.parse.quote(app_id)}")

    def query_apps(self) -> tuple[bool, str]:
        return self.get_text("/query/apps")

    def query_active_app(self) -> tuple[bool, str]:
        return self.get_text("/query/active-app")

    def raw_post(self, raw_path: str) -> tuple[bool, str]:
        path = raw_path if raw_path.startswith("/") else "/" + raw_path
        return self.post(path)

    def raw_get(self, raw_path: str) -> tuple[bool, str]:
        path = raw_path if raw_path.startswith("/") else "/" + raw_path
        return self.get_text(path)


def resolve_key(user_text: str) -> str | None:
    t = user_text.strip()
    if not t:
        return None

    lower = t.lower()
    if lower in ALIASES:
        return ALIASES[lower]

    for key in COMMON_KEYS:
        if lower == key.lower():
            return key

    return None


def fit_lines(text: str, width: int, max_lines: int) -> list[str]:
    lines = []
    raw_lines = text.splitlines() if text else [""]
    for raw in raw_lines:
        if not raw:
            lines.append("")
            if len(lines) >= max_lines:
                break
            continue

        while raw:
            lines.append(raw[:width])
            raw = raw[width:]
            if len(lines) >= max_lines:
                break

        if len(lines) >= max_lines:
            break

    return lines[:max_lines]


def draw_ui(stdscr, ip: str, last_status: str, last_action: str, mini_log: list[str]) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    stdscr.addnstr(0, 2, "Roku ECP Controller", w - 4, curses.A_BOLD)
    stdscr.addnstr(1, 2, f"Target IP: {ip or '(not set)'}", w - 4)
    stdscr.addnstr(2, 2, "Enter repeats current command. Up/Down browse command history.", w - 4)

    stdscr.addnstr(4, 2, "Common commands:", w - 4, curses.A_UNDERLINE)
    stdscr.addnstr(
        5, 2,
        "home back up down left right ok play rev fwd replay info search volup voldown mute",
        w - 4
    )

    stdscr.addnstr(7, 2, "Special commands:", w - 4, curses.A_UNDERLINE)
    special_lines = [
        ":ip                change Roku IP",
        ":apps              query installed apps",
        ":active            query active app",
        ":launch <id>       launch app id",
        ":lit <text>        send literal text",
        ":post <path>       raw POST to ECP path",
        ":get <path>        raw GET from ECP path",
        ":quit              exit",
    ]
    y = 8
    for line in special_lines:
        if y >= h - 12:
            break
        stdscr.addnstr(y, 2, line, w - 4)
        y += 1

    status_y = max(y + 1, 14)
    if status_y < h - 8:
        stdscr.addnstr(status_y, 2, "Last action:", w - 4, curses.A_UNDERLINE)
        stdscr.addnstr(status_y + 1, 4, last_action or "-", w - 6)

        stdscr.addnstr(status_y + 3, 2, "Status:", w - 4, curses.A_UNDERLINE)
        for i, line in enumerate(fit_lines(last_status or "-", max(10, w - 6), 3)):
            stdscr.addnstr(status_y + 4 + i, 4, line, w - 6)

    log_y = h - 8
    if log_y > status_y + 4:
        stdscr.addnstr(log_y, 2, "Recent actions:", w - 4, curses.A_UNDERLINE)
        recent = mini_log[-3:]
        for i, line in enumerate(recent):
            stdscr.addnstr(log_y + 1 + i, 4, line, w - 6)

    stdscr.refresh()


def prompt_line(stdscr, prompt: str, initial: str = "", history: list[str] | None = None) -> str:
    curses.curs_set(1)
    h, w = stdscr.getmaxyx()
    y = h - 2

    buf = list(initial)
    pos = len(buf)

    hist = history[:] if history else []
    hist_index = len(hist)
    working_before_history = "".join(buf)

    while True:
        stdscr.move(y, 0)
        stdscr.clrtoeol()
        stdscr.addnstr(y, 2, prompt + "".join(buf), w - 4)
        cursor_x = min(2 + len(prompt) + pos, w - 1)
        stdscr.move(y, cursor_x)
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (10, 13):
            curses.curs_set(0)
            return "".join(buf).strip()

        if ch == 27:
            curses.curs_set(0)
            return ""

        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if pos > 0:
                del buf[pos - 1]
                pos -= 1
            continue

        if ch == curses.KEY_LEFT:
            pos = max(0, pos - 1)
            continue

        if ch == curses.KEY_RIGHT:
            pos = min(len(buf), pos + 1)
            continue

        if ch == curses.KEY_UP:
            if hist:
                if hist_index == len(hist):
                    working_before_history = "".join(buf)
                hist_index = max(0, hist_index - 1)
                buf = list(hist[hist_index])
                pos = len(buf)
            continue

        if ch == curses.KEY_DOWN:
            if hist:
                if hist_index < len(hist) - 1:
                    hist_index += 1
                    buf = list(hist[hist_index])
                else:
                    hist_index = len(hist)
                    buf = list(working_before_history)
                pos = len(buf)
            continue

        if 32 <= ch <= 126:
            if hist_index != len(hist):
                hist_index = len(hist)
                working_before_history = "".join(buf)
            buf.insert(pos, chr(ch))
            pos += 1


def process_command(client: RokuECPClient, raw: str) -> tuple[str, str, bool]:
    cmd = raw.strip()

    if not cmd:
        return "No command entered.", "", False

    if cmd == ":quit":
        return "Exiting.", ":quit", True

    if cmd == ":apps":
        ok, msg = client.query_apps()
        return msg, ":apps", False

    if cmd == ":active":
        ok, msg = client.query_active_app()
        return msg, ":active", False

    if cmd.startswith(":launch "):
        app_id = cmd[len(":launch "):].strip()
        if not app_id:
            return "Usage: :launch <id>", cmd, False
        ok, msg = client.launch(app_id)
        return msg, cmd, False

    if cmd.startswith(":lit "):
        text = cmd[len(":lit "):]
        ok, msg = client.literal(text)
        return msg, cmd, False

    if cmd.startswith(":post "):
        path = cmd[len(":post "):].strip()
        ok, msg = client.raw_post(path)
        return msg, cmd, False

    if cmd.startswith(":get "):
        path = cmd[len(":get "):].strip()
        ok, msg = client.raw_get(path)
        return msg, cmd, False

    key_name = resolve_key(cmd)
    if key_name:
        ok, msg = client.keypress(key_name)
        return msg, key_name, False

    return "Unknown command/key. Try home, ok, left, right, :apps, :active, :launch <id>, :lit <text>.", cmd, False


def main(stdscr) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)

    ip = prompt_line(stdscr, "Enter Roku IP: ")
    client = RokuECPClient(ip)

    last_status = "Ready."
    last_action = "-"
    mini_log: list[str] = []
    history: list[str] = []
    current_prompt_value = ""

    while True:
        draw_ui(stdscr, client.roku_ip, last_status, last_action, mini_log)

        user_input = prompt_line(
            stdscr,
            "Command: ",
            initial=current_prompt_value,
            history=history
        )

        if not user_input:
            last_status = "No command entered."
            last_action = "-"
            continue

        if user_input == ":ip":
            new_ip = prompt_line(stdscr, "New Roku IP: ", initial=client.roku_ip)
            if new_ip:
                client.roku_ip = new_ip.strip()
                last_status = f"Target IP updated to {client.roku_ip}"
                last_action = ":ip"
                mini_log.append(f"[{time.strftime('%H:%M:%S')}] :ip -> {client.roku_ip}")
            else:
                last_status = "IP change canceled."
                last_action = ":ip"
            continue

        if not history or history[-1] != user_input:
            history.append(user_input)

        current_prompt_value = user_input

        status, action, should_quit = process_command(client, user_input)
        last_status = status
        last_action = action or user_input
        mini_log.append(f"[{time.strftime('%H:%M:%S')}] {last_action}")

        if should_quit:
            break


if __name__ == "__main__":
    curses.wrapper(main)

# prizmatik
