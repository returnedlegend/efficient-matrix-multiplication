"""V2 typed external-state adapter; V1 CP math and lifecycle stay unchanged."""
from datetime import datetime

from .fullpassing43 import (CampaignBarrier as _BarrierV1,SourceRuntime,
    guarded_call,solve_cp_core,CAP)


class CampaignBarrier(_BarrierV1):
    def _json(self,path):
        value=super()._json(path)
        if not isinstance(value,dict):
            raise ValueError('external stop/resource state must be a JSON object')
        if path==self.guard_path:
            updated=value.get('updated_utc');identity=value.get('process_identity')
            if not isinstance(updated,str) or not isinstance(identity,dict):
                raise ValueError('invalid resource timestamp/process identity type')
            stamp=datetime.fromisoformat(updated.replace('Z','+00:00'))
            if stamp.tzinfo is None:
                raise ValueError('resource timestamp requires a timezone')
            for field,item in [('pid',value.get('pid')),('start_ticks',identity.get('start_ticks'))]:
                if type(item) is not int or item<=0:
                    raise ValueError('invalid resource '+field+' type/value')
            allocated=value.get('campaign_allocated_bytes')
            if type(allocated) is not int or allocated<0:
                raise ValueError('invalid resource storage count type/value')
        return value
