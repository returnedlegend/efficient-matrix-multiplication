"""Fresh-process single-thread CMS worker for one finite cyclic code query."""
import math,signal,time

def worker(problem,seconds,memory_mb,sender,assumptions=()):
    signal.signal(signal.SIGTERM,signal.SIG_DFL);signal.signal(signal.SIGINT,signal.SIG_DFL)
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(memory_mb*1024**2,memory_mb*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(seconds)+1,math.ceil(seconds)+2));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        import pycryptosat
        started=time.monotonic();solver=pycryptosat.Solver(threads=1,time_limit=seconds);solver.add_clause([problem['nv'],-problem['nv']])
        for row in problem['clauses']:solver.add_clause(row)
        for row,rhs in problem['xors']:solver.add_xor_clause(row,rhs)
        answer,assignment=solver.solve(assumptions=list(assumptions),time_limit=seconds);usage=resource.getrusage(resource.RUSAGE_SELF)
        result=dict(status='SAT' if answer is True else 'FINITE_CODE_UNSAT' if answer is False else 'UNKNOWN',assignment=list(assignment) if answer is True else None,solver_version=pycryptosat.__version__,solver_stats=dict(backend='CryptoMiniSat',threads=1,declared_variables=solver.nb_vars(),cnf_clauses=len(problem['clauses']),native_xors=len(problem['xors']),elapsed_seconds=time.monotonic()-started,user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,max_rss_kib=usage.ru_maxrss))
    except Exception as error:result=dict(status='ERROR',error=type(error).__name__+': '+str(error))
    try:sender.send(result)
    finally:sender.close()
