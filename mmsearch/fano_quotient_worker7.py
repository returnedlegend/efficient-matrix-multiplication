"""Fresh-process CryptoMiniSat backend for the conditional Fano branch."""
import math
import signal


def worker(problem, seconds, memory_mb, sender, assumptions=()):
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb*1024**2, memory_mb*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(seconds)+1, math.ceil(seconds)+2))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        import pycryptosat
        solver = pycryptosat.Solver(threads=1, time_limit=seconds)
        solver.add_clause([problem['nv'], -problem['nv']])
        for row in problem['clauses']:
            solver.add_clause(row)
        for row, rhs in problem['xors']:
            solver.add_xor_clause(row, rhs)
        status, assignment = solver.solve(assumptions=list(assumptions), time_limit=seconds)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result = dict(status='SAT' if status is True else 'FANO_BRANCH_UNSAT' if status is False else 'UNKNOWN',
                      assignment=list(assignment) if status is True else None,
                      solver_version=pycryptosat.__version__,
                      solver_stats=dict(user_seconds=usage.ru_utime, system_seconds=usage.ru_stime,
                                        max_rss_kib=usage.ru_maxrss))
    except Exception as exc:
        result = dict(status='ERROR', error=type(exc).__name__+': '+str(exc))
    try:
        sender.send(result)
    finally:
        sender.close()
