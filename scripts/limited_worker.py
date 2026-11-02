"""Run one research command with CPU affinity, memory and wall-clock limits."""
import argparse
import datetime
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu', type=int, required=True)
    parser.add_argument('--memory-mb', type=int, required=True)
    parser.add_argument('--seconds', type=int, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or args.memory_mb < 64 or args.seconds < 1:
        raise ValueError('command and positive resource budgets required')
    args.prefix.parent.mkdir(parents=True, exist_ok=True)
    config=args.prefix.parent/'campaign.json'
    if config.exists():
        text=json.loads(config.read_text()).get('deadline_utc')
        if text:
            remaining=int(datetime.datetime.fromisoformat(text.replace('Z','+00:00')).timestamp()-time.time())
            if remaining<1:raise SystemExit('global campaign deadline reached')
            args.seconds=min(args.seconds,remaining)
    def limits():
        os.setsid()
        os.sched_setaffinity(0, {args.cpu})
        cap = args.memory_mb * 1024**2
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic()
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    stopped = False
    def interrupt(signum, frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    with args.prefix.with_suffix('.log').open('a') as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                   preexec_fn=limits)
        state = dict(command=command, started_utc=stamp, pid=process.pid,
                     cpu=args.cpu, memory_mb=args.memory_mb, wall_seconds=args.seconds)
        args.prefix.with_suffix('.running.json').write_text(json.dumps(state, indent=2)+'\n')
        while process.poll() is None and not stopped and time.monotonic()-started < args.seconds:
            time.sleep(1)
        timed_out = process.poll() is None
        if timed_out:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
        code = process.wait()
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    state.update(exit_code=code, timed_out=timed_out, interrupted=stopped,
                 elapsed_seconds=time.monotonic()-started,
                 cpu_seconds=usage.ru_utime+usage.ru_stime, max_rss_kib=usage.ru_maxrss)
    args.prefix.with_suffix('.result.json').write_text(json.dumps(state, indent=2)+'\n')
    args.prefix.with_suffix('.running.json').unlink(missing_ok=True)
    print(json.dumps(state), flush=True)
    return 124 if timed_out else (code if code >= 0 else 128-code)


if __name__ == '__main__':
    raise SystemExit(main())
