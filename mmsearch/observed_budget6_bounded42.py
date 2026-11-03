"""Hard wall/address-space isolation for the separate budget6 prototype."""
import math
import multiprocessing as mp
import signal
import time
from .observed_budget642 import decode_budget6


def _worker(q,seconds,memory_mb,cursor,branch_budget,max_prefix,sender):
    import resource
    try:
        for kind,soft,hard in ((resource.RLIMIT_AS,memory_mb*1024**2,memory_mb*1024**2),
            (resource.RLIMIT_CPU,math.ceil(seconds)+1,math.ceil(seconds)+2)):
            _,inherited=resource.getrlimit(kind);limit=hard if inherited==resource.RLIM_INFINITY else min(hard,inherited)
            resource.setrlimit(kind,(min(soft,limit),limit))
        result=decode_budget6([int(x,16) for x in q['column_syndromes_hex']],[int(x,16) for x in q['targets_hex']],
            q['weight_bound'],seconds,cursor,lambda record,state:sender.send(dict(message='PROGRESS',record=record,cursor=state)),branch_budget,max_prefix)
        if result['status'].startswith('NO_WEIGHT') and result.get('complete_for_requested_bound'):result['status']='NO_ONE_SUBSPACE_GAIN'
        usage=resource.getrusage(resource.RUSAGE_SELF)
        result['worker_stats']=dict(user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,max_rss_kib=usage.ru_maxrss,
            address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0])
        sender.send(dict(message='RESULT',result=result))
    except MemoryError:sender.send(dict(message='RESULT',result=dict(status='UNKNOWN',reason='worker memory exhaustion')))
    except Exception as error:sender.send(dict(message='RESULT',result=dict(status='ERROR',error=f'{type(error).__name__}: {error}')))
    finally:sender.close()


def _entry(*args):
    signal.signal(signal.SIGTERM,signal.SIG_DFL);signal.signal(signal.SIGINT,signal.SIG_DFL);_worker(*args)


def search_budget6_bounded(q,seconds=30,memory_mb=1024,cursor=None,on_progress=None,cancelled=None,branch_budget=0,max_prefix=65536):
    if not math.isfinite(seconds) or seconds<=0 or type(memory_mb) is not int or not 256<=memory_mb<=1024:raise ValueError('invalid budget6 resource bounds')
    context=mp.get_context('fork');receiver,sender=context.Pipe(duplex=False);latest=cursor;start=time.monotonic();result=None
    child=context.Process(target=_entry,args=(q,seconds,memory_mb,cursor,branch_budget,max_prefix,sender));child.start();sender.close()
    try:
        while result is None:
            if cancelled is not None and cancelled():result=dict(status='UNKNOWN',reason='campaign stop signal',cursor=latest);break
            left=seconds-time.monotonic()+start
            if receiver.poll(max(0,min(left,.05))):
                try:message=receiver.recv()
                except EOFError:result=dict(status='UNKNOWN',reason='worker exited before a complete result',cursor=latest);break
                if message['message']=='PROGRESS':
                    latest=message['cursor']
                    if on_progress is not None:on_progress(message['record'],{k:v for k,v in latest.items() if k!='completed_prefix'})
                else:result=message['result']
            elif left<=0:result=dict(status='UNKNOWN',reason='hard wall limit',cursor=latest);break
    finally:
        child.join(timeout=.02)
        if child.is_alive():child.terminate()
        child.join(timeout=.1)
        if child.is_alive():child.kill();child.join()
        receiver.close()
    if result['status']=='UNKNOWN' and result.get('cursor') is None:result['cursor']=latest
    result.update(quotient_sha256=q['quotient_sha256'],worker_reaped=not child.is_alive(),worker_exitcode=child.exitcode,
        elapsed_seconds=time.monotonic()-start,memory_mb=memory_mb,wall_seconds=seconds,
        scope='Only this recorded fixedP/source observed space; rank3 budget6 and rank2 budget5 Fano extension. Cutoffs remain UNKNOWN.')
    return result
