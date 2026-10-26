from __future__ import annotations
from .common import write_json,now
class BudgetExceeded(ValueError):pass

class BudgetLedger:
    def __init__(self,limits: dict,path,existing: dict|None=None):
        self.path=path;self.limits=limits
        self.data=existing or {'schema_version':1,'limits':limits,'spent':{k:0 for k in ['tool_calls','audit_runs','comparisons','index_operations','decoded_pixels','wall_seconds','llm_requests','review_pairs','questions']},'model_usage':'not_run','model_cost_usd':0,'entries':[]}
    def remaining(self,key: str) -> float:
        mapping={'tool_calls':'max_tool_calls','audit_runs':'max_core_audit_runs','comparisons':'max_comparisons_total','index_operations':'max_index_operations_total','decoded_pixels':'max_total_decoded_pixels','wall_seconds':'max_tool_wall_seconds','questions':'max_questions','review_pairs':'max_review_pairs'}
        return max(0,self.limits[mapping[key]]-self.data['spent'][key])
    def check_reservation(self,kind: str,allocation: dict|None=None,*,final: bool=False) -> dict:
        """Validate without writing a run or starting work; reserve repeats this check."""
        if any(e['status']=='pending' for e in self.data['entries']):raise BudgetExceeded('Pending reservation; recovery required')
        reserve_calls=0 if final else self.limits['finalization_reserve_tool_calls']
        reserve_time=0 if final else self.limits['finalization_reserve_seconds']
        if self.remaining('tool_calls')<=reserve_calls or self.remaining('wall_seconds')<=reserve_time:raise BudgetExceeded('Finalization budget reserved')
        a={'tool_calls':1,'wall_seconds':self.remaining('wall_seconds')-reserve_time,**(allocation or {})}
        if kind=='audit':a['audit_runs']=1
        for k,v in a.items():
            if v<0 or v>self.remaining(k):raise BudgetExceeded(f'Insufficient {k}')
        return a
    def reserve(self,kind: str,allocation: dict|None=None,*,final: bool=False) -> dict:
        a=self.check_reservation(kind,allocation,final=final)
        entry={'call_id':f'call-{len(self.data["entries"])+1:04d}','kind':kind,'status':'pending','reserved_at':now(),'reservation':a}
        self.data['entries'].append(entry);self.save();return entry
    def settle(self,entry: dict,actual: dict|None,*,error: str|None=None) -> None:
        if entry['status']!='pending':raise ValueError('Reservation already settled')
        charge=entry['reservation'].copy() if actual is None else {**{k:0 for k in entry['reservation']},**actual,'tool_calls':1}
        if entry['kind']=='audit':charge['audit_runs']=1
        # Unknown means conservatively charged, never zeroed.
        for k,v in charge.items():
            if v<0:raise ValueError('Negative usage')
            self.data['spent'][k]+=v
        entry.update(status='unknown' if actual is None else 'settled',actual=charge,error=error,settled_at=now(),refund={k:max(0,v-charge.get(k,0)) for k,v in entry['reservation'].items()})
        entry['overrun']={k:v-entry['reservation'].get(k,0) for k,v in charge.items() if v>entry['reservation'].get(k,0)}
        self.save()
    def recover_pending(self) -> None:
        for e in self.data['entries']:
            if e['status']=='pending':self.settle(e,None,error='Interrupted process; conservative charge, no automatic replay')
    def save(self) -> None:write_json(self.path,self.data)
