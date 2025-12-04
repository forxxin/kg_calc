import sys
import re
import winsound
import threading
import signal
import msvcrt
import time
from queue import Queue

stop_all = False

paused = threading.Event()
countdown_active = threading.Event()
alarm_active = threading.Event()
alarm_sound_active = threading.Event()
key_event = threading.Event()

total_seconds = 0
remaining_seconds = 0
last_time = None

key_queue = Queue()

last_display = ""


def parse_time(time_str):
    match = re.match(r"^(((?P<h>\d+):)?(?P<m>\d+):)?(?P<s>\d+(?:\.\d+)?)$", time_str)
    if match:
        d = match.groupdict()
        return int(d['h'] or 0) * 3600 + int(d['m'] or 0) * 60 + float(d['s'])
    raise ValueError("Time format: H:M:S, M:S, or S")

def display(text='', end='\r'):
    global last_display
    if text != last_display:
        print(text + " " * (len(last_display) - len(text)), end=end, flush=True)
        last_display = text

def format_hhmmss(seconds):
    seconds = int(seconds)
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}"

def countdown_thread_func():
    global remaining_seconds, stop_all, last_time
    while not stop_all:
        countdown_active.wait()
        last_time = time.monotonic()
        while countdown_active.is_set() and not stop_all:
            if paused.is_set():
                display("PAUSED")
                time.sleep(0.1)
                continue

            now = time.monotonic()
            elapsed = now - last_time
            if elapsed >= 1.0:
                remaining_seconds -= int(elapsed)
                last_time += int(elapsed)

            if remaining_seconds <= 0:
                remaining_seconds = 0
                countdown_active.clear()
                alarm_active.set()
                alarm_sound_active.set()
                break

            display(format_hhmmss(remaining_seconds))
            time.sleep(0.05)


def alarm_sound_thread_func():
    while not stop_all:
        alarm_sound_active.wait()
        display("Alarm.")
        while alarm_sound_active.is_set() and not stop_all:
            winsound.PlaySound("SystemNotification", winsound.SND_ALIAS)
            time.sleep(0.8)
        winsound.PlaySound(None, winsound.SND_PURGE)


def keyboard_thread_func():
    while not stop_all:
        key = msvcrt.getch()
        # print(f"DEBUG: key pressed: {key}")
        key_queue.put(key)
        key_event.set()


def process_keys():
    global stop_all, remaining_seconds, last_time
    while not key_queue.empty():
        key = key_queue.get().lower()
        if key == b'q' or key == b'\x03': # Q Ctrl+C
            stop_all = True
            countdown_active.clear()
            alarm_active.clear()
            alarm_sound_active.clear()
        elif countdown_active.is_set():
            if key == b' ':
                if paused.is_set():
                    paused.clear()
                    last_time = time.monotonic()
                else:
                    paused.set()
            elif key == b'r':
                remaining_seconds = total_seconds
                paused.clear()
                last_time = time.monotonic()
        elif alarm_active.is_set():
            remaining_seconds = total_seconds
            last_time = time.monotonic()
            countdown_active.set()
            paused.clear()
            alarm_active.clear()
            alarm_sound_active.clear()


def signal_handler(sig, frame):
    global stop_all
    stop_all = True
    countdown_active.clear()
    alarm_active.clear()
    alarm_sound_active.clear()
    winsound.PlaySound(None, winsound.SND_PURGE)
    display('Abort.', end='\n')
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def main():
    global stop_all, total_seconds, remaining_seconds

    if len(sys.argv) != 2:
        print("Usage: python timer.py <time>")
        return

    try:
        total_seconds = parse_time(sys.argv[1])
    except ValueError as e:
        print(f"Error: {e}")
        return

    remaining_seconds = total_seconds

    print("[Space: pause/resume] [R: restart] [Q: quit]")
    print(f"Countdown: {format_hhmmss(total_seconds)} = {int(total_seconds)}s")

    threading.Thread(target=countdown_thread_func, daemon=True).start()
    threading.Thread(target=alarm_sound_thread_func, daemon=True).start()
    threading.Thread(target=keyboard_thread_func, daemon=True).start()

    countdown_active.set()
    paused.clear()

    while not stop_all:
        key_event.wait()
        key_event.clear()
        process_keys()
        time.sleep(0.01)

    display('Exit.', end='\n')


if __name__ == "__main__":
    main()
