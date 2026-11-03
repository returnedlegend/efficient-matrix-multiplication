"""Budget6 quotient scope and immutable source-column cache."""
from .observed_rank3_lazy42 import SourceRuntime as _SourceRuntime
from .recombine import digest
from .verify import verify_candidate


class SourceRuntime(_SourceRuntime):
    def __init__(self,system):
        super().__init__(system)
        self._prepare_original=self.prepare;self.prepare=self._prepare_budget6
        self._decode_original=self.decode_hit;self.decode_hit=self._decode_budget6_hit
    def _prepare_budget6(self,system,basis,gain=1):
        q=self._prepare_original(system,basis,gain)
        q['scope']='Only this fixedP/source observed rank3 free-value space. Separate exact Fano decoder supports groupweight6; cutoffs and retained-prefix caps stay UNKNOWN.'
        q['quotient_sha256']=digest({k:v for k,v in q.items() if k!='quotient_sha256'})
        self.validate(system,q);return q

    def _decode_budget6_hit(self,system,q,entries):
        answer=self._decode_original(system,q,entries)
        answer['candidate']['metadata'].update(method='observed-rank3-exact-weight6-fano',
            decoder='fano-budget6-v1',requested_group_weight_bound=q['weight_bound'],coordinate_lift_helper='observed-rank3')
        answer['verification']=verify_candidate(answer['candidate'],random_trials=0)
        if not answer['verification']['valid'] or answer['verification']['rank']!=answer['lift']['rank_after'] or answer['verification']['exact_entries_checked']!=system['metadata']['width']**3:
            raise AssertionError('budget6 export failed full tensor verification')
        return answer
