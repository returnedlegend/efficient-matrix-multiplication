"""V43 target-latency labels, source isolation, replay and optimizer continuity."""
import copy
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest

from mmsearch.recovery_pool import bounded_mix, freeze_json
from mmsearch.rl_finetune43 import Finetune43Controller
from mmsearch.rl_recovery43 import screen43, freeze43, SourceRecoveryPool43, evaluation_sources43
from mmsearch.rl_restart_curriculum import RestartRecordController
from mmsearch.rl_search import _write, term_hash
from mmsearch.search import encode_candidate, decode_candidate, naive_terms
from scripts.train_recovery_pool43 import replay43
from scripts.train_finetune43 import read_schedule
from tests.test_rl_restart_curriculum import seeds_fixture

ROOT = Path(__file__).resolve().parents[1]


def probes(unknown=1, early_target=False):
    values = []
    for index, profile in enumerate(("exploit", "explore", "long_walk")):
        missed = index < unknown
        values.append({"profile": profile, "status": "unknown_within_probe" if missed else "known_bound_recovered",
                       "best_rank": 94 if missed else 93, "attempted_moves": 50000 if missed else 3000,
                       "step_budget": 50000, "first_improvement_step": 1})
    if early_target:
        values[-1].update(status="known_bound_recovered", best_rank=93, attempted_moves=1)
    return values


class V43Tests(unittest.TestCase):
    def test_validation_test_source_reservation_is_deterministic_disjoint_and_not_outcome_conditioned(self):
        partition = {"train": ["old", "new"], "heldout": ["a", "b", "c", "d"]}
        result = evaluation_sources43(partition)
        self.assertEqual(result, evaluation_sources43({"train": ["new", "old"], "heldout": ["d", "c", "b", "a"]}))
        expected = sorted(partition["heldout"], key=lambda key:hashlib.sha256(("v43-final:"+key).encode()).hexdigest())[:2]
        self.assertEqual(result["test"], sorted(expected))
        self.assertFalse(set(result["test"]) & set(result["validation"]))
        self.assertEqual(set(result["test"]+result["validation"]), set(partition["heldout"]))

    def test_partial_gain_at_first_move_is_allowed_but_early_target_any_profile_is_excluded(self):
        label, reason = screen43(probes(1))
        self.assertIsNone(reason)
        self.assertEqual(label["task_bucket"], "informative_challenge")
        self.assertFalse(label["strict_hard"])
        self.assertTrue(screen43(probes(3))[0]["strict_hard"])
        self.assertEqual(screen43(probes(0))[0]["task_bucket"], "delayed_control")
        self.assertEqual(screen43(probes(2, early_target=True))[1], "early_target_recovery")
        incomplete = probes(3)
        incomplete[1]["attempted_moves"] = 49999
        self.assertEqual(screen43(incomplete)[1], "incomplete_unknown_probe")

    def test_exact_replay_requires_source_completed_steps_and_recorded_hash(self):
        base = set(naive_terms(2))
        terms, mixing = bounded_mix(base, n=2, rng=random.Random(11), known_rank=8, record_rank=7,
                                   steps=100, max_rank=11, seconds=10)
        entry = {"source_index": 0, "mix_seed": 11, "mixing": mixing}
        restored, report = replay43(entry, [base], n=2, known_rank=8, record_rank=7)
        self.assertEqual(restored, terms)
        self.assertEqual(report["steps"], 100)
        bad = copy.deepcopy(entry)
        bad["mixing"]["term_hash"] = "mismatch"
        with self.assertRaisesRegex(ValueError, "reproduce"): replay43(bad, [base], n=2, known_rank=8, record_rank=7)
        with self.assertRaisesRegex(ValueError, "source"): replay43(entry, [set(naive_terms(3))], n=2, known_rank=8, record_rank=7)

    def test_v4_to_v43_preserves_all_actor_adam_rng_pending_and_resumes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seeds, _ = seeds_fixture(root)
            old = RestartRecordController(naive_terms(2), n=2, target_rank=1, seed=33, rollout=5,
                                          pool_context={"old": "frozen"})
            old.bind_restarts(seeds, interval=300, record_cpu=0)
            old.restart_if_due(0)
            for _ in range(7): old.step(cost_seconds=0)
            path = root/"old.json"
            old.save(path)
            original = path.read_bytes()
            agent = Finetune43Controller.load(path)
            self.assertEqual(agent.policy.state(), old.policy.state())
            self.assertEqual(agent.rng.getstate(), old.rng.getstate())
            self.assertEqual(agent.pending, json.loads(original)["pending"])
            self.assertEqual(path.read_bytes(), original)
            agent.finetune_context = {"clock": {"record_origin": 0, "recovery_origin": 0}, "curriculum_sha256": "test"}
            target = root/"v43.json"
            agent.save(target)
            _write(target.with_suffix(".schedule.json"), {
                "format": "mmsearch-finetune-schedule-v43", "checkpoint_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "restart_context": agent.restart_context, "finetune43": agent.finetune_context,
                "record_cpu": 0, "recovery_cpu": 0})
            read_schedule(target)
            other = Finetune43Controller.load(target)
            for _ in range(17): self.assertEqual(agent.step(cost_seconds=0), other.step(cost_seconds=0))
            self.assertEqual(agent.policy.state(), other.policy.state())
            self.assertEqual(agent.rng.getstate(), other.rng.getstate())
            self.assertIn("finetune43", agent.candidate()["metadata"])
            self.assertNotIn("finetune42", agent.candidate()["metadata"])

    def test_real5x5_frozen_tasks_have_source_isolation_and_strict_labels(self):
        fixture = ROOT/"artifacts/km93_f2.json"
        if not fixture.exists(): self.skipTest("verified93 fixture unavailable")
        base = set(decode_candidate(json.loads(fixture.read_text()), 5))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partition = {"train": [f"train{i}" for i in range(4)], "heldout": ["held0", "held1", "held2", "held3"]}
            declaration = {"partition": partition}
            entries = []
            for index, term in enumerate(sorted(base)[:16]):
                a, b, c = term
                d = 1 << ((index+1)%25)
                if d == c: d ^= 3
                terms = base-{term} | {(a,b,d), (a,b,c^d)}
                if len(terms) != 94: continue
                split = "train" if index < 10 else "heldout"
                source = partition[split][index % len(partition[split])]
                ps = probes(3 if index%5 == 0 else 1 if index%3 else 0)
                label, _ = screen43(ps)
                value = encode_candidate(terms, 5, source_term_hash=source)
                entries.append({"status": "retained", "source_term_hash": source, "term_hash": term_hash(terms),
                                "probes": ps, **label, **freeze_json(root/"raw/candidates", value)})
            _write(root/"raw/manifest.json", {"entries": entries})
            manifest = freeze43(root/"raw", root/"frozen", declaration)
            pool = SourceRecoveryPool43(root/"frozen")
            self.assertGreaterEqual(manifest["counts"]["heldout"]["challenge"], 2)
            delayed = 0
            rng = random.Random(2)
            for episode in range(50):
                key, _, entry = pool.choose(rng, episode_index=episode, delayed_used=delayed)
                delayed += entry["task_bucket"] == "delayed_control"
                self.assertNotIn(key, pool.heldout)
                self.assertIn(entry["source_term_hash"], partition["train"])
            value = json.loads((root/"frozen/manifest.json").read_text())
            value["entries"][0]["strict_hard"] = not value["entries"][0]["strict_hard"]
            _write(root/"frozen/manifest.json", value)
            with self.assertRaisesRegex(ValueError, "labels"): SourceRecoveryPool43(root/"frozen")


if __name__ == "__main__":
    unittest.main()
