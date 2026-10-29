#!/usr/bin/env python3
from pdf_semantic_timeline_v8 import build_payload

meta={"recording_time_sec":40.0,"recording_time_exact":True,"recording_time_basis":"accepted_capture_samples","pdf_timeline_schema":"v8.0-gamma-pdf-events-v1"}
events=[
 {"seq":1,"time":5.0,"type":"pdf_open","pdf_id":"pdf_a","page":8},
 {"seq":2,"time":5.6,"type":"pdf_page","pdf_id":"pdf_a","page":9},
 {"seq":3,"time":6.5,"type":"pdf_page","pdf_id":"pdf_a","page":10},
 {"seq":4,"time":24.7,"type":"pdf_page","pdf_id":"pdf_a","page":11},
 {"seq":5,"time":26.2,"type":"pdf_page","pdf_id":"pdf_a","page":12},
 {"seq":6,"time":30.2,"type":"pdf_close","pdf_id":"pdf_a","page":12},
 {"seq":7,"time":35.0,"type":"pdf_open","pdf_id":"pdf_b","page":1},
 {"seq":8,"time":35.0,"type":"pdf_page","pdf_id":"pdf_b","page":2},
]
p=build_payload(meta,events,generated_at="test")
e=p["entries"]
assert [x["semantic_weight"] for x in e] == ["ignore","ignore","strong","weak","include","ignore","include"], e
assert e[0]["dwell"] == 0.6
assert e[1]["dwell"] == 0.9
assert e[2]["dwell"] == 18.2
assert e[5]["dwell"] == 0.0  # same timestamp; seq 7 loses immediately to seq 8
assert e[-1]["dwell"] == 5.0  # final page extends to recording end
assert p["source"]["llm_used"] is False
assert p["summary"]["counts"] == {"ignore":3,"weak":1,"include":2,"strong":1}
print("PASS: V8.0-eta semantic timeline core")
