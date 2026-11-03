"""Isolated operator-version fork; inherited learner and global clocks unchanged."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from .rl_finetune43 import Finetune43Controller, phase_usage, recovery_due
from .rl_search import ACTIONS, _write

CHECKPOINT_FORMAT = 'mmsearch-finetune-a2c-v44'
SCHEDULE_FORMAT = 'mmsearch-finetune-schedule-v44'


def raw(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(raw(value)).hexdigest()


def code_hashes44():
    root = Path(__file__).resolve().parents[1]
    names = ['mmsearch/rl_finetune44.py', 'mmsearch/native_bridge44.py',
             'scripts/train_finetune44.py', 'scripts/train_evaluate44.py']
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}


def bridge_context(binding, archive_size):
    verify = hashlib.sha256(Path(__file__).with_name('verify.py').read_bytes()).hexdigest()
    return {'archive_size': archive_size, 'binary_sha256': binding['binary_sha256'],
            'source_sha256': binding['source_sha256'],
            'code_hashes': {'native_bridge44.py': binding['bridge_sha256'], 'verify.py': verify}}


def new_pool_context(old, binding):
    value = copy.deepcopy(old)
    for key, size in [('record_bridge', 8), ('recovery_bridge', 1)]:
        value[key] = bridge_context(binding, old.get(key, {}).get('archive_size', size))
    return value


def preserved_hashes(checkpoint, schedule):
    return {'checkpoint': {key: digest(value) for key, value in checkpoint.items()
                           if key not in ('format', 'code_hashes', 'native', 'pending', 'pool_curriculum', 'operator44')},
            'schedule': {key: digest(value) for key, value in schedule.items()
                         if key not in ('format', 'checkpoint_sha256', 'pool_context', 'operator44')}}


def migrate_payloads(parent_bytes, schedule_bytes, binding, quarantine_path, *, dimension=5):
    """Pure one-time fork; no training, random draws, clock changes or IO."""
    from .native_bridge44 import operator_binding
    if operator_binding(binding['binary_sha256'], binding['source_sha256']) != binding:
        raise ValueError('operator binding mismatch')
    parent, old = json.loads(parent_bytes), json.loads(schedule_bytes)
    if parent.get('format') != 'mmsearch-finetune-a2c-v43' or old.get('format') != 'mmsearch-finetune-schedule-v43':
        raise ValueError('fork requires a coherent completed V43 parent')
    if old.get('checkpoint_sha256') != hashlib.sha256(parent_bytes).hexdigest():
        raise ValueError('parent checkpoint/schedule hash mismatch')
    if old.get('restart_context') != parent.get('restart_curriculum') or old.get('finetune43') != parent.get('finetune43'):
        raise ValueError('parent context mismatch')
    phase_usage(parent['finetune43']['clock'], old['record_cpu'], old['recovery_cpu'])
    config = parent['config']
    if (dimension not in (2, 5) or config['n'] != dimension or config['max_extra'] != 6
            or tuple(parent['actions']) != ACTIONS or parent['policy']['hidden'] != 32
            or len(parent['policy']['params']['W']) != 20 or parent['state']['terminal']):
        raise ValueError('parent architecture/config differs')
    if dimension == 5 and (config['target_rank'] != 92 or len(parent['best']) != 93
                           or config['native_only'] is not True or config['train'] is not True or config['control'] != 'policy'):
        raise ValueError('production fork requires native n5 record policy training')
    if old.get('pool_context') != parent.get('pool_curriculum'):
        raise ValueError('parent pool context differs')
    quarantine = {'format': 'operator44-old-rollout-quarantine-v1',
                  'parent_checkpoint_sha256': hashlib.sha256(parent_bytes).hexdigest(),
                  'samples': copy.deepcopy(parent['pending']), 'count': len(parent['pending']),
                  'policy': 'Retained exactly as provenance; excluded from all new-environment batches; no reward or bootstrap event.'}
    context = {'format': 'operator44-boundary-v1', 'binding': binding,
               'parent_checkpoint_sha256': hashlib.sha256(parent_bytes).hexdigest(),
               'parent_schedule_sha256': hashlib.sha256(schedule_bytes).hexdigest(),
               'quarantine_path': str(Path(quarantine_path).resolve()), 'quarantine_sha256': digest(quarantine),
               'quarantined_samples': len(parent['pending']), 'control_only': dimension == 2,
               'preserved_state_hashes': preserved_hashes(parent, old)}
    child = copy.deepcopy(parent); child['format'] = CHECKPOINT_FORMAT
    child['pending'] = []; child['operator44'] = context
    child['code_hashes'].update(code_hashes44())
    child['pool_curriculum'] = new_pool_context(parent['pool_curriculum'], binding)
    child['native'] = {'binary_sha256': binding['binary_sha256'], 'source_sha256': binding['source_sha256'],
                       'binary': 'operator44-runtime-binding', 'output_dir': 'unlaunched-operator44-fork'}
    schedule = copy.deepcopy(old); schedule['format'] = SCHEDULE_FORMAT
    schedule['operator44'] = context; schedule['pool_context'] = child['pool_curriculum']
    schedule['checkpoint_sha256'] = digest(child)
    if preserved_hashes(child, schedule) != context['preserved_state_hashes']:
        raise AssertionError('operator migration changed inherited numeric state')
    # Dataset and budget values stay identical; only executable bridge identities change.
    for key in set(parent['pool_curriculum'])-{'record_bridge', 'recovery_bridge'}:
        if child['pool_curriculum'][key] != parent['pool_curriculum'][key]:
            raise AssertionError('operator migration changed dataset/budget state')
    return child, schedule, quarantine


def validate_operator(value, native_bridge=None):
    if value.get('format') != CHECKPOINT_FORMAT:
        raise ValueError('operator44 requires its explicit checkpoint version')
    context = value.get('operator44')
    if not context or context.get('format') != 'operator44-boundary-v1':
        raise ValueError('operator44 boundary missing')
    from .native_bridge44 import operator_binding
    binding = context['binding']
    if operator_binding(binding['binary_sha256'], binding['source_sha256']) != binding:
        raise ValueError('operator44 code/profile/worker binding changed')
    if native_bridge is not None and native_bridge.operator_binding != binding:
        raise ValueError('native bridge differs from checkpoint operator44')
    if any(value.get('code_hashes', {}).get(k) != v for k, v in code_hashes44().items()):
        raise ValueError('operator44 runtime code changed')
    q = Path(context['quarantine_path']).read_bytes()
    if hashlib.sha256(q).hexdigest() != context['quarantine_sha256']:
        raise ValueError('old rollout quarantine checksum differs')
    quarantine = json.loads(q)
    if (quarantine.get('parent_checkpoint_sha256') != context['parent_checkpoint_sha256']
            or len(quarantine.get('samples', [])) != context['quarantined_samples']):
        raise ValueError('old rollout quarantine identity differs')
    return context


def read_schedule(checkpoint):
    checkpoint = Path(checkpoint); payload = checkpoint.read_bytes(); value = json.loads(payload)
    if value.get('format') != CHECKPOINT_FORMAT:
        raise ValueError('ordinary V44 resume requires a prepared V44 fork')
    validate_operator(value)
    schedule = json.loads(checkpoint.with_suffix('.schedule.json').read_bytes())
    if schedule.get('format') != SCHEDULE_FORMAT or schedule.get('checkpoint_sha256') != hashlib.sha256(payload).hexdigest():
        raise ValueError('V44 checkpoint/schedule mismatch')
    for field, key in [('restart_curriculum', 'restart_context'), ('finetune43', 'finetune43'),
                       ('operator44', 'operator44'), ('pool_curriculum', 'pool_context')]:
        if not value.get(field) or schedule.get(key) != value[field]:
            raise ValueError('V44 matching context differs: '+field)
    phase_usage(schedule['finetune43']['clock'], schedule['record_cpu'], schedule['recovery_cpu'])
    return schedule


class Finetune44Controller(Finetune43Controller):
    def __init__(self, *args, operator44_context=None, **kwargs):
        self.operator44_context = copy.deepcopy(operator44_context or {})
        super().__init__(*args, **kwargs)

    def candidate(self):
        value = super().candidate(); value['metadata']['operator44'] = copy.deepcopy(self.operator44_context)
        return value

    def save(self, path):
        if not self.operator44_context:
            raise ValueError('V44 save requires explicit prepared boundary')
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        # Existing inherited save layers lengthen basenames; a short private
        # basename avoids exceeding NAME_MAX at this additional version layer.
        with tempfile.TemporaryDirectory(prefix='.v44-', dir=path.parent) as directory:
            staged = Path(directory)/'c'
            super().save(staged)
            value = json.loads(staged.read_bytes()); value['format'] = CHECKPOINT_FORMAT
            value['operator44'] = copy.deepcopy(self.operator44_context)
            value['code_hashes'].update(code_hashes44()); _write(path, value)

    @classmethod
    def load(cls, path, *, native_bridge=None):
        value = json.loads(Path(path).read_bytes())
        if value.get('format') != CHECKPOINT_FORMAT:
            raise ValueError('V44 loader forbids implicit operator migration')
        context = validate_operator(value, native_bridge)
        translated = copy.deepcopy(value); translated['format'] = 'mmsearch-finetune-a2c-v43'
        with tempfile.TemporaryDirectory(prefix='mmsearch-v44-load-') as temporary:
            staged = Path(temporary)/'checkpoint.json'; _write(staged, translated)
            obj = super().load(staged, native_bridge=native_bridge)
        obj.operator44_context = copy.deepcopy(context)
        return obj


def freeze_record44(directory, candidate):
    """Publish the existing global stop marker only after both exact proofs."""
    from .verify import verify_candidate
    from scripts.verify_record42_independent import verify_bytes
    if candidate.get('dimension') != 5 or candidate.get('field') != 2 or not 0 < len(candidate['terms']) <= 92:
        raise ValueError('production record requires n5F2 essential<=92')
    report = verify_candidate(candidate, random_trials=0)
    if not report['valid'] or report['exact_entries_checked'] != 15625:
        raise ValueError('record failed complete tensor verification')
    payload = raw(candidate); independent = verify_bytes(payload)
    if not independent.get('record_eligible') or independent.get('exact_entries_checked') != 15625:
        raise ValueError('record failed second independent checker')
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    proofs = {'WINNER.verification.json': raw(report), 'WINNER.independent.verification.json': raw(independent),
              'WINNER.verify.py': (root/'mmsearch/verify.py').read_bytes(),
              'WINNER.independent.verify.py': (root/'scripts/verify_record42_independent.py').read_bytes()}
    def freeze(name, content):
        path = directory/name
        try:
            with path.open('xb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
        except FileExistsError:
            if path.read_bytes() != content: raise ValueError('record artifact collision')
        path.chmod(0o444)
    for name, content in proofs.items(): freeze(name, content)
    freeze('WINNER.checksums.json', raw({**{k:hashlib.sha256(v).hexdigest() for k,v in proofs.items()},
                                       'WINNER.json':hashlib.sha256(payload).hexdigest()}))
    freeze('WINNER.json', payload)
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
    return report, independent
