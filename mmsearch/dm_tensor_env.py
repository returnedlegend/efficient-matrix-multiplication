"""DeepMind dm_env adapter for the exact algebraic operator controller.

This is API integration with dm_env, not the original AlphaTensor environment.
Factories create fresh search episodes and may explicitly share one policy.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import dm_env
from dm_env import specs
import numpy as np

from .rl_search import ACTIONS, FEATURES
from .verify import verify_candidate


class DmTensorEnv(dm_env.Environment):
    """Explicit-reset environment with verified terminal certificate retention.

    ``reset`` constructs a new controller. ``step`` after LAST requires an
    explicit reset, so a successful search is never silently overwritten.
    Terminal artifacts retain immutable JSON bytes internally across resets;
    the public accessor returns detached copies for callers to persist.
    """
    def __init__(self, controller_factory):
        if not callable(controller_factory):
            raise TypeError("controller_factory must be callable")
        self._factory = controller_factory
        self.controller = None
        self.last_transition = None
        self._ended = False
        self._terminal_artifacts = []

    def action_spec(self):
        return specs.DiscreteArray(len(ACTIONS), dtype=np.int32, name="operator")

    def observation_spec(self):
        return specs.Array((FEATURES,), dtype=np.float64, name="controller_features")

    def _observation(self):
        observation = np.array(self.controller.features(), dtype=np.float64, copy=True)
        self.observation_spec().validate(observation)
        if not np.isfinite(observation).all():
            raise ValueError("controller features must be finite")
        return observation

    def reset(self):
        controller = self._factory()
        if controller is self.controller:
            raise ValueError("controller_factory must return fresh search state")
        self.controller = controller
        self._ended = False
        self.last_transition = None
        # An explicit zero reward makes episode starts safe for reward summation.
        return dm_env.TimeStep(dm_env.StepType.FIRST, 0.0, 1.0, self._observation())

    @property
    def terminal_artifacts(self):
        """Detached verified certificate/report/checksum records, across resets."""
        return [json.loads(payload) for payload in self._terminal_artifacts]

    def step(self, action):
        if self.controller is None:
            raise RuntimeError("reset must be called before step")
        if self._ended:
            raise RuntimeError("terminal result retained; call reset explicitly for a fresh episode")
        if isinstance(action, (bool,np.bool_)) or not isinstance(action, (int,np.integer)):
            raise ValueError("action must be an integer operator index")
        action = int(action)
        if not 0 <= action < len(ACTIONS) or not self.controller.mask()[action]:
            raise ValueError("action is unavailable in current state")
        event = copy.deepcopy(self.controller.step(action))
        reward = float(event["reward"])
        if not math.isfinite(reward):
            raise ValueError("controller reward must be finite")
        observation = self._observation()
        if bool(event.get("terminal", False)) != bool(self.controller.terminal):
            raise ValueError("controller terminal event and state disagree")
        if self.controller.terminal:
            candidate = copy.deepcopy(self.controller.candidate())
            report = verify_candidate(candidate, random_trials=0)
            if not report["valid"] or report["rank"] > self.controller.target_rank:
                raise ValueError("controller terminal certificate failed independent verification")
            payload = (json.dumps(candidate,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
            checksum = hashlib.sha256(payload).hexdigest()
            record = dict(candidate=candidate, verification=report, candidate_sha256=checksum,
                          candidate_serialization="sorted compact JSON plus newline")
            self._terminal_artifacts.append(json.dumps(record,sort_keys=True,allow_nan=False).encode())
            event["terminal_candidate_sha256"] = checksum
            event["terminal_verification"] = report
            self.last_transition = event
            self._ended = True
            return dm_env.termination(reward,observation)
        self.last_transition = event
        return dm_env.transition(reward,observation)
