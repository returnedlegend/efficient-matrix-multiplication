# Exact 366-orbit finite-code result

The one authorized cost-at-most-92 SAT query returned **complete UNSAT for the sealed 366-orbit dictionary**. The independently verified rank-93 seed belongs to this dictionary, so its finite optimum is exactly 93. This is not a global bilinear-rank lower bound or a lower bound for all C3 decompositions. No candidate or continuation was produced.

The model uses all 123 independent kernel selectors and 366 orbit variables, with `x = seed XOR Kα` in 366 native XOR constraints. Complete kernel rank/nullity and every full/compressed column were rechecked before the query. The exact integer cost is `3N+C`, with 361 nonfixed variables and five cube variables. Cost ≤92 is encoded as `N≤29 OR (N≤30 AND C≤2)` through a branch gate and sequential cardinality CNF. The resulting model has 20,054 variables and 39,733 CNF clauses. There are no assumptions or extra symmetry restrictions.

Eight frozen owner controls and 13 independent targeted controls passed. They include exhaustive cardinality assignments, independent literal-code/integer-budget assignments, a nontrivial finite N2 code with seed cost 13 and SAT at cost 8 / UNSAT at cost 5, exact persisted-formula roundtrip, malformed-model rejection, callback/UTC tampering, and late or stalled worker reaping. The independent reviewer regenerated all 366 columns and checked rank 243, complete kernel dimension 123, the rank-93 seed, formula and dependency pins.

The actual call used pinned CryptoMiniSat **5.17.0**, one thread, CPU3 / 1,024 MiB. CMS returned UNSAT after 0.728515 seconds including formula insertion; its worker used 0.616408 CPU seconds. The bounded outer job finished normally in **2.006869 wall seconds / 1.810323 CPU seconds**, peak RSS 54,720 KiB. The worker exited 0 and was reaped. The authorized limits were 60 seconds for the solver, 80 seconds internally and 110 seconds externally.

A queued setup attempt failed before output-directory creation or any solver call: its inherited nice 19 could not be changed to nice 10. Root explicitly authorized a direct `limited_worker.py` launch from nice 0 using the **same frozen code, config, formula and resource envelope**. That direct launch is the single actual SAT query. The setup error and direct launch records are retained separately; no failed setup is counted as a mathematical negative.

Primary pins:

- Dictionary: `12ceaae3e96013a56fb960383f7f34531793977661ce65a47f94f88c838481f5`.
- Formula body: `d15f9e38cb813936456c0d30a7876116524264c728f809ba61ebb51f8412b7b6`.
- Config: `c5ee72a75a0b1935f6cd264b73606eeda2ee56c732098836d9aadc787c7a68f9`.
- Result summary: `d8373c95c2edcb43c3dd392409bd0262a8ca8272bc94a196982912d4104c6a52`.
- Raw solver result: `f0e794ebc7f0900b206c742befba1c46bdb3bd299240f257e66ff65b23825fdf`.
- Independent final QA: `7332a753db372b7abd582f237a161678a3d59b4da8c3ac329b81c8ef4ac99d47`.

Artifacts are under `cyclic-native-orbit7-sat001-001` and `cyclic-native-orbit7-sat001-seal-v1`. Small evidence: `evidence/cyclic-native-orbit7-sat001.json` (`c0930e1c45a79783301cfbfacf5255bf99b039a1cf42f7eb37f8cb7827231a32`). The compressed formula/result/runtime bundle is `evidence/cyclic-native-orbit7-sat001-bundle-v1.tar.gz`; its pin is `8050a3dfc29f9c5a4783e858f8c92a1ccc0041472b4f33198ba173c11831e762` (410,856 bytes), and it contains the exact historical command and setup-correction context. Further code queries would require a changed dictionary or another justified new experiment; this instance is completely closed at the requested budget.
