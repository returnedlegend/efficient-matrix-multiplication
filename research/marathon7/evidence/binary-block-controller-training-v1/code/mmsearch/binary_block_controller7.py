"""Small exact-reward contextual bandit over discrete binary CP operators.

No neural network, source loading or ambient-candidate publication. Tensor
coefficients remain GF2; rewards/table statistics are exact integers.
"""
from fractions import Fraction
import hashlib
import json
import random

from . import binary_block_descent7 as block

ORDERS = ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))
OPERATORS = tuple([dict(name="axis_" + "".join(map(str, order)), order=order, kind="none", amount=0)
                   for order in ORDERS] + [
    dict(name="flip1_012", order=(0, 1, 2), kind="flip", amount=1),
    dict(name="flip3_120", order=(1, 2, 0), kind="flip", amount=3),
    dict(name="flip8_201", order=(2, 0, 1), kind="flip", amount=8),
    dict(name="resample_factor_021", order=(0, 2, 1), kind="factor", amount=1),
    dict(name="best_flip3_102", order=(1, 0, 2), kind="best_flip", amount=3),
    dict(name="restart_210", order=(2, 1, 0), kind="restart", amount=0)])
FIXED_CYCLE = (0, 6, 7, 8, 9, 10, 11)
SCHEMA = "binary_block_controller7.policy.v1"


def _tuple_tree(value):
    return tuple(_tuple_tree(v) for v in value) if isinstance(value, list) else value


class Bandit:
    def __init__(self, seed=7):
        block._integer(seed, "bandit seed", -(1 << 63), (1 << 63) - 1)
        self.seed, self.rng, self.table, self.updates = seed, random.Random(seed), {}, 0

    def select(self, context, training=False):
        stats = self.table.get(context, [[0, 0] for _ in OPERATORS])
        if training:
            untried = [i for i, (count, _) in enumerate(stats) if count == 0]
            if untried:
                return self.rng.choice(untried)
            if self.rng.randrange(5) == 0:
                return self.rng.randrange(len(OPERATORS))
        # Frozen/unseen contexts fall back to the plain exact sweep.
        if not any(count for count, _ in stats):
            return 0
        scores = [Fraction(total, count) if count else Fraction(-10**30) for count, total in stats]
        return max(range(len(scores)), key=lambda i: (scores[i], -i))

    def update(self, context, action, reward):
        block._integer(action, "action", 0, len(OPERATORS) - 1)
        if type(reward) is not int:
            raise ValueError("reward statistics must be exact integers")
        stats = self.table.setdefault(context, [[0, 0] for _ in OPERATORS])
        stats[action][0] += 1
        stats[action][1] += reward
        self.updates += 1

    def checkpoint(self):
        return dict(schema=SCHEMA, seed=self.seed, table=json.loads(json.dumps(self.table)),
                    updates=self.updates, rng_state=self.rng.getstate(),
                    operator_names=[op["name"] for op in OPERATORS])

    @classmethod
    def restore(cls, value):
        if value.get("schema") != SCHEMA or value.get("operator_names") != [op["name"] for op in OPERATORS]:
            raise ValueError("policy schema/operator mismatch")
        result = cls(value["seed"])
        total = 0
        if type(value.get("table")) is not dict:
            raise ValueError("policy table must be a dict")
        for context, stats in value["table"].items():
            if type(context) is not str or type(stats) is not list or len(stats) != len(OPERATORS):
                raise ValueError("invalid policy context/arm table")
            for entry in stats:
                if type(entry) is not list or len(entry) != 2 or type(entry[1]) is not int:
                    raise ValueError("invalid integer policy reward")
                block._integer(entry[0], "policy arm count")
                total += entry[0]
        if type(value.get("updates")) is not int or value["updates"] != total:
            raise ValueError("policy update/count mismatch")
        result.table = json.loads(json.dumps(value["table"]))
        result.updates = total
        result.rng.setstate(_tuple_tree(value["rng_state"]))
        return result


def essential_products(factors):
    parity = set()
    for term in map(tuple, factors):
        if all(term):
            if term in parity:
                parity.remove(term)
            else:
                parity.add(term)
    return sorted(parity)


def exact_reward(before, after, entries, novel, *, verified_exact=False,
                 product_count=None, source_product_count=None):
    """No product-count credit for any nonzero residual, even fewer slots."""
    for value, name in [(before, "loss before"), (after, "loss after"), (entries, "entry count")]:
        block._integer(value, name)
    if verified_exact and after != 0:
        raise ValueError("terminal reward requires independently verified zero loss")
    residual = 1000 * (before - after)
    novelty = 2 * max(1, entries) if novel else 0
    benefit = 0
    if verified_exact:
        block._integer(product_count, "verified product count")
        block._integer(source_product_count, "reference source count")
        benefit = max(0, source_product_count - product_count)
    terminal = 2000 * max(1, entries) * benefit
    return dict(total=residual + novelty + terminal, residual=residual,
                novelty=novelty, terminal=terminal, verified_product_benefit=benefit)


def _state_hash(factors):
    return hashlib.sha256(json.dumps(essential_products(factors), separators=(",", ":")).encode()).hexdigest()


def _context(core, shape, factors, loss, stagnation):
    entries = max(1, len(core))
    level = 0 if loss * 16 <= entries else 1 if loss * 4 <= entries else 2
    support = [set(), set(), set()]
    residual = block._packed(core) ^ block._tensor(factors, shape)
    for index in block._bits(residual):
        a, rem = divmod(index, shape[1] * shape[2])
        b, c = divmod(rem, shape[2])
        for axis, coordinate in enumerate((a, b, c)):
            support[axis].add(coordinate)
    sparse = min(range(3), key=lambda i: (len(support[i]), i))
    return f"L{level}:S{int(stagnation >= 2)}:A{sparse}"


def run_controller(core, shape, rank, *, initial_factors=None, source_product_count=None,
                   mode="fixed", policy=None, training=False, seed=7, max_actions=100,
                   timeout_seconds=120, cancelled=None, deadline_utc=block.DEADLINE):
    core, shape, initial_factors = block._validate(core, shape, initial_factors)
    block._integer(rank, "rank", 0, block.MAX_RANK)
    block._integer(seed, "controller seed", -(1 << 63), (1 << 63) - 1)
    block._integer(max_actions, "action cap", 0, 10000)
    if initial_factors is not None and len(initial_factors) != rank:
        raise ValueError("initial factor slots differ from fixed target rank")
    if mode not in ("fixed", "uniform", "bandit") or (mode == "bandit" and not isinstance(policy, Bandit)):
        raise ValueError("invalid controller/policy mode")
    if training and mode != "bandit":
        raise ValueError("only bandit mode may update the learned table")
    source_product_count = rank + 1 if source_product_count is None else source_product_count
    block._integer(source_product_count, "source product count")
    guard = block._Guard(timeout_seconds, cancelled, deadline_utc)
    rng = random.Random(seed)
    def random_factors():
        return [tuple(rng.randrange(1, 1 << d) if d else 0 for d in shape) for _ in range(rank)]
    factors = list(initial_factors) if initial_factors is not None else random_factors()
    best = list(factors)
    loss = best_loss = block.residual_loss(core, shape, factors)
    visited = {_state_hash(factors)}
    history = []
    stagnation = blocks = reward_total = terminal_total = 0

    def finish(status, case):
        reason = guard.reason()
        if reason:
            status, case = "UNKNOWN", reason
        result = dict(status=status, complete=status == "RAW_EXACT_COMPACT", case=case,
            field=2, shape=list(shape), fixed_rank=rank, source_product_count=source_product_count,
            mode=mode, training=training, seed=seed, best_loss=best_loss,
            best_factors=[list(t) for t in best], actions=len(history), block_updates=blocks,
            reward_total=reward_total, terminal_reward_total=terminal_total, history=history,
            elapsed_seconds=__import__("time").monotonic() - guard.started,
            input_sha256=block._input_digest(core, shape), publication_eligible=False,
            requires_ambient_verification=True, no_global_unsat_claim=True,
            checkpoint=dict(kind="diagnostic_search_state", current_factors=[list(t) for t in factors],
                current_loss=loss, best_factors=[list(t) for t in best], best_loss=best_loss,
                visited_state_hashes=sorted(visited), rng_state=rng.getstate(), stagnation=stagnation,
                policy=policy.checkpoint() if policy else None))
        if status == "RAW_EXACT_COMPACT":
            if block.scalar_loss(core, shape, best) != 0:
                raise AssertionError("controller raw exact observation failed scalar verification")
            late = guard.reason()
            if late:
                result.update(status="UNKNOWN", complete=False, case=late, after_cutoff=True)
            result["raw_compact"] = dict(products=[list(t) for t in essential_products(best)],
                shape=list(shape), exact_entries_checked=len(core), packed_and_scalar_losses=[0, 0],
                ambient_verified=False)
        return result

    try:
        guard.check()
        if loss == 0:
            return finish("RAW_EXACT_COMPACT", "already_exact_input_no_training_credit")
        for step in range(max_actions):
            guard.check()
            context = _context(core, shape, factors, loss, stagnation)
            action = (FIXED_CYCLE[step % len(FIXED_CYCLE)] if mode == "fixed" else
                      rng.randrange(len(OPERATORS)) if mode == "uniform" else policy.select(context, training))
            op = OPERATORS[action]
            before = loss
            current = [list(t) for t in (best if op["kind"] == "best_flip" else factors)]
            if op["kind"] == "restart":
                current = [list(t) for t in random_factors()]
            elif op["kind"] in ("flip", "best_flip"):
                choices = [(t, a, b) for t in range(rank) for a in range(3) for b in range(shape[a])]
                for t, a, b in rng.sample(choices, min(op["amount"], len(choices))):
                    current[t][a] ^= 1 << b
            elif op["kind"] == "factor" and rank:
                axes = [a for a in range(3) if shape[a]]
                if axes:
                    t, a = rng.randrange(rank), rng.choice(axes)
                    current[t][a] = rng.randrange(1 << shape[a])
            proposal = [tuple(t) for t in current]
            final_loss = block.residual_loss(core, shape, proposal)
            for axis in op["order"]:
                guard.check()
                answer = block.exact_block_update(core, shape, proposal, axis,
                    timeout_seconds=max(0, guard.seconds - (__import__("time").monotonic() - guard.started)),
                    cancelled=cancelled, deadline_utc=deadline_utc)
                if answer["status"] != "BLOCK_MINIMUM":
                    raise block._Stopped(answer.get("case", "block_incomplete"))
                proposal, final_loss = answer["factors"], answer["loss_after"]
                blocks += 1
                if final_loss == 0:
                    break
            guard.check()
            key = _state_hash(proposal)
            novel = key not in visited
            visited.add(key)
            exact = final_loss == 0
            if exact and block.scalar_loss(core, shape, proposal) != 0:
                raise AssertionError("terminal training credit failed scalar compact check")
            guard.check()
            reward = exact_reward(before, final_loss, len(core), novel, verified_exact=exact,
                product_count=len(essential_products(proposal)) if exact else None,
                source_product_count=source_product_count if exact else None)
            if training:
                policy.update(context, action, reward["total"])
            factors, loss = list(proposal), final_loss
            reward_total += reward["total"]
            terminal_total += reward["terminal"]
            if loss < best_loss:
                best, best_loss = list(factors), loss
                stagnation = 0
            else:
                stagnation += 1
            history.append(dict(step=step, context=context, action=action, operator=op["name"],
                loss_before=before, loss_after=loss, best_loss=best_loss, reward=reward,
                fixed_rank=rank, compact_zero_verified=exact))
            if exact:
                return finish("RAW_EXACT_COMPACT", "verified_zero_compact_residual")
        return finish("UNKNOWN", "action_budget")
    except block._Stopped as exc:
        return finish("UNKNOWN", str(exc))
