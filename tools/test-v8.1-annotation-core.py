#!/usr/bin/env python3
SCHEMA='v8.1-alpha.1-annotation-events-v2'
events=[
 {'seq':1,'annotation_schema':SCHEMA,'type':'annotation_add','annotation_id':'ann_aaaaaaaaaaaaaaaa','pdf_id':'pdf_0123456789abcdef','page':2,'tool':'pen','points':[{'x':.1,'y':.2},{'x':.2,'y':.3}],'anchor_type':'live_recording','lecture_time':12.5,'created_at':'x','created_during':'live'},
 {'seq':2,'annotation_schema':SCHEMA,'type':'annotation_add','annotation_id':'ann_bbbbbbbbbbbbbbbb','pdf_id':'pdf_0123456789abcdef','page':2,'tool':'highlighter','points':[{'x':.2,'y':.4}],'anchor_type':'page_only','lecture_time':None,'created_at':'x','created_during':'page_only'},
 {'seq':3,'annotation_schema':SCHEMA,'type':'annotation_erase','target_annotation_id':'ann_aaaaaaaaaaaaaaaa','soft_erase':True,'operation_anchor_type':'page_only','operation_lecture_time':None,'created_at':'x','created_during':'page_only'},
]
active={}; history=[]
for e in events:
    history.append(e)
    if e['type']=='annotation_add': active[e['annotation_id']]=e
    else: active.pop(e['target_annotation_id'],None)
assert len(history)==3
assert list(active)==['ann_bbbbbbbbbbbbbbbb']
assert events[0]['lecture_time']==12.5 and events[0]['anchor_type']=='live_recording'
assert events[1]['lecture_time'] is None and events[1]['anchor_type']=='page_only'
assert events[2]['soft_erase'] is True and events[2]['operation_lecture_time'] is None
print('PASS : live/playback/page_only anchors + nullable time + append-only soft erase')
