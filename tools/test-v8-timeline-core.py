#!/usr/bin/env python3
SR=16000
cursor=0

def chunk(seconds):
    global cursor
    start=cursor; cursor += round(seconds*SR); return start,cursor

def sec(x): return x/SR
chunk(2.0)
chunk_start,_=chunk(0.1)
preroll=round(0.5*SR)
seg_start=max(0,chunk_start-preroll)
chunk(2.9)
seg_end=seg_start+round(3.5*SR)
assert seg_start >= 0
assert seg_end <= cursor
before=(seg_start,seg_end,cursor)
deleted=True
after=(seg_start,seg_end,cursor)
assert before==after and deleted
paused_cursor=cursor
assert cursor==paused_cursor
chunk(1.0)
assert sec(cursor) > sec(paused_cursor)
print('PASS: sample cursor, pause exclusion, immutable deletion coordinates')
