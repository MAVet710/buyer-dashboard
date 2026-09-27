"""Bounded summaries, not copies of provider payloads or invented business counts."""
import hashlib
import json


def import_summary(result):
    conflicts=set()
    inspected=0
    truncated=False
    def walk(value,depth=0):
        nonlocal inspected,truncated
        inspected+=1
        if inspected>10000 or depth>12:
            truncated=True
            return
        if isinstance(value,dict):
            for name,child in value.items():
                if name in {'conflicts','identity_conflicts'} and isinstance(child,list):
                    for issue in child[:1000]:
                        conflicts.add(hashlib.sha256(json.dumps(issue,sort_keys=True,default=str).encode()).hexdigest())
                    truncated |= len(child)>1000
                elif name not in {'records','payload','raw','raw_payload','source'}:
                    walk(child,depth+1)
        elif isinstance(value,list):
            for child in value[:1000]:walk(child,depth+1)
            truncated |= len(value)>1000
    walk(result)
    return {'conflict_count':len(conflicts),'summary_truncated':truncated,
            'business_records_created_count':None,
            'note':'Provider processing counts are not counts of newly created business records.'}
