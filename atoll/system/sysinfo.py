"""CPU, memory and battery readings from /proc and /sys."""
import glob


def read_cpu():
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    return v[3] + v[4], sum(v)  # (idle + iowait, total)


def cpu_percent(prev, cur):
    total = cur[1] - prev[1]
    return 0.0 if total <= 0 else 100.0 * (1 - (cur[0] - prev[0]) / total)


def mem_percent():
    m = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            m[k] = int(v.split()[0])
    return 100.0 * (1 - m["MemAvailable"] / m["MemTotal"]), m["MemTotal"] / 1048576


def low_battery():
    for bat in glob.glob("/sys/class/power_supply/BAT*"):
        try:
            with open(bat + "/status") as f, open(bat + "/capacity") as c:
                if f.read().strip() == "Discharging" and int(c.read()) < 10:
                    return True
        except (OSError, ValueError):
            pass
    return False
