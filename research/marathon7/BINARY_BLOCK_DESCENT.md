# Exact binary block-coordinate CP prototype

The separate prototype `mmsearch/binary_block_descent7.py` optimizes a supplied
compact binary tensor using at most14 product slots and mode dimensions<=15.
All target coefficients and factors are literal GF2 bits, represented by exact
bit masks. The loss is the INTEGER number of incorrect full tensor entries.
No real-valued ALS, tolerance, thresholding or rounding is involved.

## Exact factor-block step

Fix V,W in R product slots. Their opposite-pair columns P_t=v_t tensor w_t
define a binary code word sum(x_t P_t) for each x in F2^R. Each U row has an
independent target matrix slice and an independent R-bit coefficient vector.
Therefore minimizing full Hamming tensor loss over U is exactly the sum of
the closest-codeword distances of those rows. Gray enumeration visits ALL
2^R choices, including duplicate codewords from dependent columns, with one
column XOR per step. The selected row coefficient vectors transpose directly
into the new U factors. The argument applies unchanged to V and W blocks.

Every complete block step attains the exact global minimum for THAT block,
so integer full residual loss cannot increase. Ties preserve the current row
when it is already optimal; otherwise a deterministic smallest mask is used.
Thus flat sweeps identify block-coordinate fixed points rather than artificial
tie cycles. Discrete bit perturbations and independent random restarts are
separate actions and can raise current loss; the best observed loss never rises.
This does not imply convergence to a globally optimal rank-R decomposition.

## Scope and safe output

`exact_block_update(core,shape,factors,axis,...)` returns BLOCK_MINIMUM only after
all2^R words and independent scalar full-loss checks complete. `optimize` runs
alternating blocks and bounded perturbations/restarts. All failed, timed out,
capped or stopped searches return UNKNOWN, never a global CP negative. Limits
are rank14, mode width15, codewords16384 and timeout<=120s, with the fixed C7
deadline. History storage caps at10000 entries and reports omitted events.
Zero factor vectors are allowed inactive slots, so the model means CP<=R.

Zero residual observations are only RAW_EXACT_COMPACT. They are bound to the
supplied core hash, checked by packed full expansion and an independent scalar
loop, and marked publication_eligible=false/requires_ambient_verification=true.
Their object has no ambient candidate dimension/terms format, so the operations
candidate loader rejects it. No output path or publication is provided. A caller
must expand through the exact original mode bases, verify every ambient tensor
entry independently, and pass the existing lifecycle/publication barriers before
any result can become an eligible matrix-multiplication candidate.

For a15-product packet, the full target core is the XOR of ALL15 original
products. An initial14-slot approximation may drop one source product; the
target must never be truncated. Shared-mode bases, source indices and exact
actual-image witnesses remain caller metadata. The prototype does not read
packets, sources, N=5 targets or external datasets.

## What changes relative to dominated isolated atom extensions

The rejected plus/cube extensions kept an exact tensor while selecting from a
fixed enlarged atom dictionary. Complete kernel-projection certificates mapped
every new-using solution back to a cheaper old-dictionary solution. This search
instead changes factor BIT VECTORS inside whole mode-image spaces and rebuilds
the pair code at each block. It can create atoms outside those fixed dictionaries.
Its rank-slot count stays fixed while intermediate tensors may have nonzero
residual. The fixed-dictionary dominance certificates therefore do not constrain
this larger factor search. Exact block minima are still only local steps in a
nonconvex finite landscape; success on hard packets is unproven.

## Controls and planned evidence

Tests independently brute force complete factor blocks for60 random tiny
axis instances, repair all84 single-factor-bit corruptions of the known n2
Strassen7 decomposition, check dependent-code ties, deterministic replay,
monotonic block/best losses, bounded impossible-capacity failure, zero modes,
literal input types and late/timeout UNKNOWN behavior. These are known fixtures,
not improved matrix multiplication algorithms. The separate benchmark has no
production input option: it tests known n2 random starts and one synthetic9^3
rank14 block under CPU1/nice10/512MiB and records failures as well as successes.
Actual measured outcomes are appended after running; no N=5 search is authorized.

## Measured tiny landscape and block cost

The frozen run `research/marathon7/evidence/binary-block-descent-tiny-v2/`
contains exact input fixtures,109 run records, source snapshots and a summary.
It ran on CPU1 nice10 with a512MiB address-space limit in0.581s, with11,904KiB
high-water RSS. No N=5 target, packet catalogue or production source was read.

| Control |Observed outcome |
|---|---|
| Known Strassen7,84 single-bit corruptions, fixed U/V/W order, no perturb/restart |84 raw exact compact repairs |
| Twelve random rank7 starts on the known n2 tensor, up to2 restarts and3 perturbations per run |12 UNKNOWN; best residual losses3..8 |
| Each of8 schoolbook8 products dropped to initialize7 slots; up to10 three-bit perturbations, no restart |8 UNKNOWN; all retain best loss1 |
| One-slot approximation to the elementary rank2 diagonal tensor |UNKNOWN with positive residual |
| Synthetic9x9x9 target, rank14, one full exact factor block |16,384 words in38.4ms; residual357 ->203 |

The three additional repair runs that put the corrupted axis first also recover
the known compact witness. No raw observation is promoted or claimed novel.
The schoolbook drop-one control is particularly relevant to future15->14 packet
initializations: being one coefficient away from an exact tensor can still be
a coordinate-wise trap. The random-start failures show that exact individual
blocks do not solve the coupled finite landscape. Hamming loss also depends on
the chosen compact mode bases even though zero residual is basis-independent.
These measured failures must accompany the feasibility/timing result.

The library checks its own UTC/monotonic limit at every codeword. A future
production driver should force canonical lifecycle checks at dispatch/block/
publication barriers and poll file-based resource state in bounded batches,
while checking local signal flags each step; it should not pay a filesystem
campaign scan for every Hamming-distance comparison. No production driver or
ambient promotion is included in this prototype.
