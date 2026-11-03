"""Resource-bounded rank3 decoder with streamed completed-branch checkpoints."""
import math
import multiprocessing as mp
import signal
import time
from .observed_rank342 import _emit,basis_values,decode_rank3,rank
from .observed_plane42 import decode_weight3
from .observed_weight442 import decode_weight4


def _worker(q,seconds,memory_mb,cursor,branch_budget,sender):
    import resource
    try:
        for kind,soft,hard in ((resource.RLIMIT_AS,memory_mb*1024**2,memory_mb*1024**2),
                               (resource.RLIMIT_CPU,math.ceil(seconds)+1,math.ceil(seconds)+2)):
            _,inherited=resource.getrlimit(kind);limit=hard if inherited==resource.RLIM_INFINITY else min(hard,inherited)
            resource.setrlimit(kind,(min(soft,limit),limit))
        columns=[int(value,16) for value in q['column_syndromes_hex']];targets=[int(value,16) for value in q['targets_hex']]
        target_rank=rank(targets);bound=q['weight_bound']
        if target_rank>bound:
            result=dict(status='NO_GAIN_RANK_BOUND',searched_bound=bound,complete_for_requested_bound=True)
        elif target_rank==3:
            def progress(record,state):sender.send(dict(message='PROGRESS',record=record,cursor=state))
            result=decode_rank3(columns,targets,bound,seconds,cursor,progress,branch_budget)
        elif not target_rank:
            result=_emit(columns,targets,[],bound,'zero_target')
        else:
            reduced_targets=basis_values(targets)
            if len(reduced_targets)==1:reduced_targets.append(0)
            searched=min(bound,4 if target_rank==2 else 3)
            child=(decode_weight4(columns,reduced_targets,seconds) if target_rank==2 and searched==4 else
                   decode_weight3(columns,reduced_targets,searched,seconds))
            if child['status']=='HIT':result=_emit(columns,targets,[entry[0] for entry in child['entries']],bound,'older_lower_rank_decoder')
            elif child['status']=='UNKNOWN':result=child
            elif searched<bound:result=dict(status='UNKNOWN',reason='requested lower-rank budget is not closed by the older decoder',
                searched_bound=searched,partial_negative=child,complete_for_requested_bound=False)
            else:result=dict(child,complete_for_requested_bound=True)
        if result['status'].startswith('NO_WEIGHT'):
            if result.get('complete_for_requested_bound'):result['status']='NO_ONE_SUBSPACE_GAIN'
            else:result['status']='PARTIAL_NO_WEIGHT_LE5'
        usage=resource.getrusage(resource.RUSAGE_SELF)
        result['worker_stats']=dict(user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,max_rss_kib=usage.ru_maxrss,
            address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0])
        sender.send(dict(message='RESULT',result=result))
    except MemoryError:sender.send(dict(message='RESULT',result=dict(status='UNKNOWN',reason='worker memory exhaustion')))
    except Exception as error:sender.send(dict(message='RESULT',result=dict(status='ERROR',error=f'{type(error).__name__}: {error}')))
    finally:sender.close()


def _entry(*args):
    signal.signal(signal.SIGTERM,signal.SIG_DFL);signal.signal(signal.SIGINT,signal.SIG_DFL);_worker(*args)


def search_bounded(q,seconds=30,memory_mb=1024,cursor=None,on_progress=None,cancelled=None,branch_budget=0):
    if not math.isfinite(seconds) or seconds<=0 or type(memory_mb) is not int or not 128<=memory_mb<=1536:
        raise ValueError('invalid rank3 worker resource bounds')
    context=mp.get_context('fork');receiver,sender=context.Pipe(duplex=False)
    child=context.Process(target=_entry,args=(q,seconds,memory_mb,cursor,branch_budget,sender))
    start=time.monotonic();result=None;prefix=[] if cursor is None else [dict(record) for record in cursor['completed_prefix']]
    latest=cursor;child.start();sender.close()
    try:
        while result is None:
            if cancelled is not None and cancelled():
                result=dict(status='UNKNOWN',reason='campaign stop signal',cursor=latest);break
            left=seconds-(time.monotonic()-start)
            if receiver.poll(max(0,min(left,.1))):
                try:message=receiver.recv()
                except EOFError:
                    result=dict(status='ERROR',error='rank3 worker exited without result');break
                if message['message']=='PROGRESS':
                    record=message['record']
                    if record['branch']!=len(prefix):raise AssertionError('noncontiguous completed-branch stream')
                    prefix.append(record);latest=dict(message['cursor'],completed_prefix=prefix)
                    if on_progress is not None:on_progress(record,message['cursor'])
                else:result=message['result']
            elif left<=0 or (cancelled is not None and cancelled()):
                result=dict(status='UNKNOWN',reason='hard wall/stop signal',cursor=latest);break
    finally:
        child.join(timeout=.02)
        if child.is_alive():child.terminate()
        child.join(timeout=.1)
        if child.is_alive():child.kill();child.join()
        receiver.close()
    if result['status']=='UNKNOWN' and not result.get('cursor') and latest is not None:result['cursor']=latest
    result.update(quotient_sha256=q['quotient_sha256'],worker_reaped=not child.is_alive(),worker_exitcode=child.exitcode,
        memory_mb=memory_mb,wall_seconds=seconds,elapsed_seconds=time.monotonic()-start,
        scope='Only the recorded fixedP/source rank3 observed space. Exact negative through groupweight5; larger budgets remain nonclosed.')
    return result
