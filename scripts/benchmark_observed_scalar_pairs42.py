"""Synthetic scalar pair-map memory benchmark; no production model or target query."""
import argparse
import json
import random
import resource
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--columns',type=int,default=1553);p.add_argument('--bits',type=int,default=625)
    p.add_argument('--seed',type=int,default=4261553);p.add_argument('--memory-mb',type=int,default=768);a=p.parse_args()
    if not 1<=a.columns<=1553 or not 1<=a.bits<=625 or not 384<=a.memory_mb<=1024:p.error('benchmark bounds exceeded')
    resource.setrlimit(resource.RLIMIT_AS,(a.memory_mb*1024**2,a.memory_mb*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(25,26))
    rng=random.Random(a.seed);h=[rng.getrandbits(a.bits) for _ in range(a.columns)];pairs={};started=time.monotonic()
    for i,x in enumerate(h):
        for j in range(i+1,len(h)):pairs.setdefault(x^h[j],(i<<32)|j)
    usage=resource.getrusage(resource.RUSAGE_SELF)
    print(json.dumps(dict(status='SYNTHETIC_MEMORY_CONTROL_PASSED',columns=len(h),bits=a.bits,seed=a.seed,
        pair_count=len(h)*(len(h)-1)//2,distinct_pair_xors=len(pairs),max_rss_kib=usage.ru_maxrss,
        address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0],elapsed_seconds=time.monotonic()-started,
        user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,production_queries=0)))


if __name__=='__main__':main()
