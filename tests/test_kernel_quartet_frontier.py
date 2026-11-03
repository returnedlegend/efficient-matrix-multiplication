import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel_wide import native_input
from mmsearch.free_factor_sat import build_system
from mmsearch.kernel_quartet_frontier import reconstruct, select_diverse, verify_export, compress_export
from mmsearch.search import encode_candidate, naive_terms

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT/'native/free_factor_quartet_frontier_worker'


def plateau_tensor(split=False):
    terms = list(naive_terms(2))
    if split:
        terms.remove((2,4,1));terms.extend(((3,4,1),(1,4,1)))
    padding = [(5,1,0)]+[(a,b,0) for a in (3,6,7) for b in (1,2,3)]
    dictionary = terms+padding
    system = build_system(dictionary,2,'uv',encode_candidate(terms,2))
    ids = {tuple(pair): i for i,pair in enumerate(system['pairs'])}
    supports = [[ids[a,1] for a in (1,4,5)]]+[[ids[a,b] for b in (1,2,3)] for a in (3,6,7)]
    return system,[dict(class_id=0,support=s) for s in supports],dictionary


@unittest.skipUnless(BINARY.exists(),'frontier worker not built')
class FrontierTests(unittest.TestCase):
    def test_full_tensor_plateau_gap1_compression_and_corruption(self):
        system,circuits,dictionary = plateau_tensor()
        raw = native_input(system,circuits); catalog=b'MMKQUARTETS1 1\n0 1 2 3\n'
        input_sha=hashlib.sha256(raw).hexdigest();catalog_sha=hashlib.sha256(catalog).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input';source.write_bytes(raw);cat=root/'catalog';cat.write_bytes(catalog);prefix=root/'out'
            command=[str(BINARY),'--input',str(source),'--catalog',str(cat),'--output',str(prefix),'--target','7','--seconds','2',
                     '--input-sha256',input_sha,'--catalog-sha256',catalog_sha,'--seed','44']
            done=subprocess.run(command,capture_output=True,text=True,timeout=4)
            self.assertEqual(done.returncode,0,done.stderr)
            stats=json.loads(prefix.with_suffix('.stats.json').read_text());self.assertEqual(stats['status'],'NO_TARGET')
            index=prefix.with_suffix('.frontier.txt').read_bytes()
            records=reconstruct(system,circuits,[(0,1,2,3)],index,prefix,input_sha,catalog_sha,44,1)
            self.assertEqual(sorted(record['rank'] for record in records),[8,8,9])
            self.assertEqual(sorted(record['gap'] for record in records),[0,0,1])
            self.assertEqual(sum(record['origin']=='xor-sampled' for record in records),1)
            for record in select_diverse(records):
                candidate,report,metadata=verify_export(system,circuits,record)
                self.assertEqual((report['valid'],report['exact_entries_checked']),(True,64))
                compressed,checked,proof=compress_export(candidate)
                self.assertEqual((checked['valid'],checked['rank'],checked['exact_entries_checked']),(True,8,64))
                self.assertTrue(proof['fixed_point']);self.assertFalse(metadata['record_claim'])
            # Exact source/cursor bindings are mandatory on both reconstruction and resume.
            with self.assertRaises(ValueError): reconstruct(system,circuits,[(0,1,2,3)],index,prefix,'0'*64,catalog_sha,44,1)
            lines=index.decode().splitlines();fields=lines[1].split();fields[10]=str(int(fields[10])+1);lines[1]=' '.join(fields)
            with self.assertRaises(ValueError):reconstruct(system,circuits,[(0,1,2,3)],('\n'.join(lines)+'\n').encode(),prefix,input_sha,catalog_sha,44,1)
            original=records[0]['block_optimum_rank'];records[0]['block_optimum_rank']=original-1
            with self.assertRaises(ValueError):verify_export(system,circuits,records[0])
            records[0]['block_optimum_rank']=original
            resume=root/'resume'
            done=subprocess.run(command[:command.index('--output')]+['--output',str(resume)]+command[command.index('--output')+2:]+
                ['--start-row','1','--frontier-load',str(prefix.with_suffix('.frontier.txt'))],capture_output=True,text=True,timeout=4)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertEqual(resume.with_suffix('.frontier.txt').read_bytes(),index)
            with self.assertRaises(ValueError):select_diverse(records,17)


if __name__=='__main__':unittest.main()
