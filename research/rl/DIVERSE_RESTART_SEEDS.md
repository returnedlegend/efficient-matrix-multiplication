# Structural selection of four rank-93 restart states

`scripts/select_diverse93_seeds.py` retains ordered mandatory certificates and
fills the remaining restart slots from a public certificate directory. Every
scanned file must have the strict dense 5x5 F2 schema with integer binary factor
entries and canonical essential rank 93. Duplicate products cancel and zero
products are removed before ranking. Every selected certificate is independently
verified at all 15,625 coefficients before anything is frozen.

For each term, the script interprets each factor mask as a 5x5 binary matrix,
computes its exact GF2 matrix rank, and sorts the three ranks. The counts of
these joint triples form a 35-bin histogram. At each greedy step it maximizes
the minimum histogram L1 distance from the previously selected states, then
maximizes the minimum term-set Jaccard distance. Lexical source path and raw
checksum break remaining ties, making selection independent of pool enumeration
order. Histogram total variation is L1 divided by 186 because every state has
93 essential terms.

These metrics distinguish certificate states. They do not prove algorithm
inequivalence or mathematical novelty. Only the selected four algorithms receive
fresh exhaustive tensor verification; scanning other pool states validates their
schema and essential rank, without representing a new exhaustive verification
of the entire public corpus.

The campaign selection scanned all 307 pool files and froze this order:

1. Mandatory KM93: `seed00-56e2dc2a4ce5e808.json`.
2. Mandatory AlphaEvolve93 F2: `seed01-962b518010483e3a.json`.
3. Public corpus `seed015.json`: `seed02-897eb861a5df9fe7.json`.
4. Public corpus `seed095.json`: `seed03-590f496894897026.json`.

The copies are under
`artifacts/rl_campaign_20261102T210735Z/restart93-seeds/seeds/`.
The first added state has minimum histogram L1 distance 30 and minimum Jaccard
distance 0.368421 from mandatory states. The second has minimum L1 distance 18
and minimum Jaccard distance 0.324324 from the three already selected states.
The manifest records every scanned source checksum and feature histogram,
ordered selected paths, greedy decisions, pairwise distances, exact verification
reports, and code hashes. Selected raw certificate bytes and relevant source
code are copied exclusively, made read-only, and covered by checksums.

```sh
python scripts/select_diverse93_seeds.py \
  --mandatory artifacts/km93_f2.json \
  --mandatory artifacts/rl_campaign_20261102T210735Z/public/alphaevolve93_f2.json \
  --pool artifacts/campaign/public-seeds/fastmatrix-f2/seeds \
  --count 4 --output-dir PATH/new-restart-seeds
```

Three small tests cover exact GF2 matrix rank including dependent rows,
deterministic greedy structural selection, and Jaccard tie breaking with
duplicate-state exclusion:
`python -m unittest tests.test_select_diverse93_seeds`.
