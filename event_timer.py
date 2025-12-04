import time
import threading
import winsound
from datetime import datetime, timedelta, timezone
import msvcrt
from queue import Queue
import re

ALARM_TEXT = """
UTC Mo 16:00 # comment
UTC Mo 17:00
UTC Tu 16:00
UTC We 10:00
UTC Th 10:00
UTC Th 14:00
UTC Fr 17:00
UTC Sa 17:00
# UTC Su 16:00
"""

ADVANCE_SECONDS_LIST = [60*5, 0]

LOCAL_TZ = datetime.now().astimezone().tzinfo

stop_all = False
key_queue = Queue()
key_event = threading.Event()
alarm_list = []
alarm_active = threading.Event()

weekday_map = {"Su":6,"Mo":0,"Tu":1,"We":2,"Th":3,"Fr":4,"Sa":5}
weekday_names = ["Su","Mo","Tu","We","Th","Fr","Sa"]

def parse_alarm_line(line):
    line = line.rstrip("\n")
    if not line:
        return None
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    comment = ""
    if "#" in stripped:
        body, comment_part = stripped.split("#", 1)
        comment = comment_part.strip()
        stripped = body.strip()

    parts = stripped.split()
    tz = None
    tz_str = None

    if parts[0].upper().startswith("UTC"):
        tz_str = parts[0].upper()
        if tz_str == "UTC":
            offset = 0
        else:
            m = re.match(r"UTC([+-]\d+)", tz_str)
            offset = int(m.group(1)) if m else 0
        tz = timezone(timedelta(hours=offset))
        parts = parts[1:]
    else:
        tz = LOCAL_TZ
        tz_str = None

    if len(parts) == 2:
        weekday_raw = parts[0]
        time_part = parts[1]
        weekday = weekday_map.get(weekday_raw, None)
    elif len(parts) == 1:
        time_part = parts[0]
        weekday = None
    else:
        return None

    tparts = list(map(int, time_part.split(":")))
    hour = tparts[0]
    minute = tparts[1] if len(tparts) > 1 else 0
    second = tparts[2] if len(tparts) > 2 else 0

    return {
        "hour": hour,
        "minute": minute,
        "second": second,
        "weekday": weekday,
        "tz": tz,
        "tz_str": tz_str,
        "raw": stripped,
        "original_line": line.strip(),
        "comment": comment,
        "advance_triggered": [False]*len(ADVANCE_SECONDS_LIST)
    }

def load_alarms(text):
    alarms = []
    for line in text.splitlines():
        a = parse_alarm_line(line)
        if a:
            alarms.append(a)
    return alarms

def compute_next_occurrences(alarm, base_dt_local=None):
    if base_dt_local is None:
        now_local = datetime.now(LOCAL_TZ)
    else:
        now_local = base_dt_local

    occurrences = []

    now_in_alarm_tz = datetime.now(alarm["tz"])
    candidate_orig = now_in_alarm_tz.replace(
        hour=alarm["hour"],
        minute=alarm["minute"],
        second=alarm["second"],
        microsecond=0
    )

    if alarm["weekday"] is None:
        for w in range(7):
            cand = candidate_orig + timedelta(days=(w - candidate_orig.weekday()) % 7)
            if cand <= now_in_alarm_tz:
                cand += timedelta(days=7)
            cand_local = cand.astimezone(LOCAL_TZ)
            occurrences.append((cand, cand_local))
    else:
        cand = candidate_orig + timedelta(days=(alarm["weekday"] - candidate_orig.weekday()) % 7)
        if cand <= now_in_alarm_tz:
            cand += timedelta(days=7)
        cand_local = cand.astimezone(LOCAL_TZ)
        occurrences.append((cand, cand_local))

    return occurrences

def build_alarm_schedule():
    schedule = []
    for alarm in alarm_list:
        occs = compute_next_occurrences(alarm)
        for orig_dt, local_dt in occs:
            schedule.append((alarm, orig_dt, local_dt))
    return schedule

def tz_offset_str(tz):
    try:
        offset = tz.utcoffset(None)
    except:
        try:
            offset = tz.utcoffset(datetime.now(tz))
        except:
            offset = None
    if offset is None:
        return ""
    hours = int(offset.total_seconds() // 3600)
    return f"UTC{hours:+d}"

def print_alarm_schedule():
    schedule = build_alarm_schedule()
    now_local = datetime.now(LOCAL_TZ)
    future_entries = [(a,o,l) for (a,o,l) in schedule if l >= now_local]
    next_entry = min(future_entries, key=lambda x:x[2], default=None)

    schedule_sorted = sorted(
        schedule,
        key=lambda tpl: (tpl[1].astimezone(timezone.utc).weekday(), tpl[1].time(), tpl[1])
    )

    print("\n--- Alarm List ---")
    for alarm, orig_dt, local_dt in schedule_sorted:
        is_next = (next_entry is not None and local_dt == next_entry[2])
        marker = " <-- NEXT" if is_next else ""
        tz_label = alarm.get("tz_str") or tz_offset_str(alarm["tz"])

        orig_str = f"{orig_dt.strftime('%a %H:%M:%S')} ({tz_offset_str(alarm['tz'])})"
        local_str = f"{local_dt.strftime('%a %H:%M:%S')} [local]"
        # comment_str = f"[{alarm['comment']}]" if alarm.get('comment') else ""

        print(f"{orig_str}  =>  {local_str}  [{alarm['original_line']}] {marker}")

    print("-----------------")

last_display = ""
def display(text=''):
    global last_display
    if text != last_display:
        print(text + " " * max(0, len(last_display)-len(text)), end='\r', flush=True)
        last_display = text

def alarm_sound_thread():
    while not stop_all:
        alarm_active.wait()
        while alarm_active.is_set() and not stop_all:
            winsound.PlaySound("SystemNotification", winsound.SND_ALIAS)
            for _ in range(8):
                if stop_all or not alarm_active.is_set():
                    break
                time.sleep(0.1)

def keyboard_thread():
    while not stop_all:
        k = msvcrt.getch()
        key_queue.put(k)
        key_event.set()

def check_missed_alarms_on_start():
    now_local = datetime.now(LOCAL_TZ)
    max_adv = max(ADVANCE_SECONDS_LIST) if ADVANCE_SECONDS_LIST else 0
    schedule = build_alarm_schedule()

    for alarm, orig_dt, local_dt in schedule:
        if local_dt > now_local and (local_dt - timedelta(seconds=max_adv)) <= now_local:
            comment_str = f"[{alarm['comment']}]" if alarm.get('comment') else ""
            display(f"ALARM! (missed) {local_dt.strftime('%Y-%m-%d %H:%M:%S')} [{alarm['original_line']}] {comment_str}")
            alarm_active.set()
            time.sleep(1.2)
            alarm_active.clear()
            alarm['advance_triggered'] = [True]*len(ADVANCE_SECONDS_LIST)

def alarm_loop():
    global stop_all
    while not stop_all:
        now_local = datetime.now(LOCAL_TZ)
        schedule = build_alarm_schedule()

        if not schedule:
            time.sleep(1)
            continue

        next_fire = None

        for alarm, orig_dt, local_dt in schedule:
            for idx, adv in enumerate(ADVANCE_SECONDS_LIST):
                if alarm['advance_triggered'][idx]:
                    continue

                fire_local = local_dt - timedelta(seconds=adv)
                if fire_local < now_local:
                    continue

                if next_fire is None or fire_local < next_fire[0]:
                    next_fire = (fire_local, alarm, orig_dt, idx, adv)

        if next_fire is None:
            time.sleep(1)
            continue

        fire_time_local, alarm_obj, orig_dt, adv_idx, adv_sec = next_fire

        print_alarm_schedule()

        while True:
            now_local = datetime.now(LOCAL_TZ)
            delta = (fire_time_local - now_local).total_seconds()
            if delta <= 0:
                break
            key_event.wait(timeout=min(delta, 60))
            key_event.clear()

            while not key_queue.empty():
                kk = key_queue.get().lower()
                if kk in (b'\x03', b'q'):
                    stop_all = True
                    alarm_active.clear()
                    return

        comment_str = f"[{alarm_obj['comment']}]" if alarm_obj.get('comment') else ""
        display(f"ALARM! {fire_time_local.strftime('%Y-%m-%d %H:%M:%S')} [{alarm_obj['original_line']}] {comment_str} (advance {adv_sec}s)")
        alarm_active.set()
        alarm_obj['advance_triggered'][adv_idx] = True

        stopped = False
        while not stop_all and not stopped:
            key_event.wait()
            key_event.clear()

            while not key_queue.empty():
                kk = key_queue.get().lower()
                if kk in (b'\x03', b'q'):
                    stop_all = True
                    alarm_active.clear()
                    return
                else:
                    alarm_active.clear()
                    stopped = True
            time.sleep(0.05)

def main():
    global alarm_list
    alarm_list = load_alarms(ALARM_TEXT)

    print("Press Ctrl+C or Q to quit, any other key stops alarm")

    threading.Thread(target=alarm_sound_thread, daemon=True).start()
    threading.Thread(target=keyboard_thread, daemon=True).start()

    check_missed_alarms_on_start()

    try:
        alarm_loop()
    except KeyboardInterrupt:
        pass

    print("\nBye.")

if __name__ == "__main__":
    main()
