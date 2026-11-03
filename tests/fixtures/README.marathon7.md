These portable controls are unchanged copies of actual campaign42 inputs and results. `marathon7-fixtures.provenance.json` records source paths, original byte hashes, sizes, independent verification and before/after hashes of the four tests whose fixture paths changed. The original campaign remains read-only.

`native_campaign42_rank93.json` is the shared exact93-product F2 control. The breadth and dwell source copies were byte-identical. `native_campaign42_rank96.json` is the actual first higher-rank certificate selected by the old burst summary; tests now read it directly, avoiding the summary’s absolute path. Both certificates passed independent exact verification of all15625 entries and neither is a≤92record.

`compact_rank2_edges43_oracle.py` is the unchanged independent stdlib oracle for tiny exhaustive controls; it imports no production search code. Its test retains the optional `EDGE_ORACLE` path override. These fixtures replace external campaign dependencies without weakening assertions or adding skips.

The existing `held_inventory42_rank113.txt` and its provenance file are also required by held-inventory/mutable-cube tests. They are an exact local113-product fixture derived from classic125, with no improved bound claimed.
