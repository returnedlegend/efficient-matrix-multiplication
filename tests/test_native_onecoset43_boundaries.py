"""Protocol/cutoff boundary controls for the independent all-pairs oracle."""
import itertools,json,selectors,subprocess,tempfile,time,unittest
from pathlib import Path
from tests import test_native_onecoset43 as controls
from mmsearch.compact_coset43 import expand_products
from mmsearch.onecoset_codec43 import verify_sat_result,make_request,bind_response,encode_case

class NativeOneCosetBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):controls.NativeOneCosetTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):controls.NativeOneCosetTests.tearDownClass.__func__(cls)
    run_cases=controls.NativeOneCosetTests.run_cases
    witness=controls.NativeOneCosetTests.witness

    def test_rectangular_shapes_every_axis_and_dependent_free_coordinates(self):
        shape=[3,4,5];core=expand_products([[5,9,21],[2,6,6]],shape)
        cases=[controls.case(core,shape,2,axis) for axis in range(3)]
        for axis,(data,result) in enumerate(zip(cases,self.run_cases(cases))):
            self.assertEqual(result['status'],'SAT');self.witness(result,data)
            self.assertTrue(verify_sat_result(result,core,shape,2,axis)['valid'])
        boundaries=[(8,7,1,1,[1<<55]),(7,8,1,1,[1<<55]),(1,8,8,1,[255,0,255,255,0,0,255,0])]
        for data,result in zip(boundaries,self.run_cases(boundaries)):self.assertEqual(result['status'],'SAT');self.witness(result,data)

    def test_truncated_rows_do_not_consume_next_case_or_overrun_output(self):
        lines=['2 2 2 2 1','2 3 1 1 1 2','9 7 1 1 1','7 9 1 1 1','2 3 1 1 64','2 3 1 1 1']
        raw='ONECOSET43 1\n'+'\n'.join(lines)  # Valid final row intentionally has no final newline.
        run=subprocess.run([str(self.binary)],input=raw,capture_output=True,text=True,timeout=2);self.assertEqual(run.returncode,0,run.stderr)
        rows=[json.loads(x) for x in run.stdout.splitlines()];self.assertEqual(len(rows),len(lines));self.assertEqual([r['case_index'] for r in rows],list(range(len(lines))))
        self.assertEqual([r['status'] for r in rows],['UNKNOWN']*5+['SAT']);self.assertTrue(all(len(x)<4096 for x in run.stdout.splitlines()))
        for raw in ['ONECOSET43 1\n','ONECOSET43','WRONG 1\n']:
            run=subprocess.run([str(self.binary)],input=raw,capture_output=True,text=True,timeout=2)
            self.assertEqual(run.stdout,'');self.assertEqual(run.returncode==0,raw=='ONECOSET43 1\n')

    def test_existing_output_is_untouched_and_invalid_cli_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'existing';path.write_bytes(b'immutable sentinel')
            run=subprocess.run([str(self.binary),'--output',str(path)],input='ONECOSET43 1\n',capture_output=True,text=True,timeout=2)
            self.assertNotEqual(run.returncode,0);self.assertEqual(path.read_bytes(),b'immutable sentinel')
        for flag,value in [('--seconds','1junk'),('--seconds','nan'),('--seconds','-1'),('--seconds','601'),('--memory-mb','512junk'),('--memory-mb','769'),('--enumeration','bogus')]:
            run=subprocess.run([str(self.binary),flag,value],input='ONECOSET43 1\n',capture_output=True,text=True,timeout=2)
            self.assertNotEqual(run.returncode,0);self.assertEqual(run.stdout,'')

    def test_stop_marker_created_during_active_compute_leaves_unknown_suffix(self):
        partial=False
        for attempt in range(3):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);marker=root/'STOP';path=root/'input.txt';matrix=sum(1<<(9*i) for i in range(8))
                path.write_text(controls.text([(8,8,1,2,[matrix])]*100))
                process=subprocess.Popen([str(self.binary),'--input',str(path),'--stop-marker',str(marker),'--enumeration','lex','--seconds','10'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
                try:
                    self.assertTrue(selector.select(timeout=2));first=process.stdout.readline();self.assertTrue(first)
                    time.sleep(.004);marker.write_text('created during batch')
                    rest,error=process.communicate(timeout=3);self.assertEqual(process.returncode,0,error)
                    rows=[json.loads(x) for x in (first+rest).splitlines()];self.assertEqual(len(rows),100);self.assertEqual([r['case_index'] for r in rows],list(range(100)))
                    index=next(i for i,r in enumerate(rows) if r['status']=='UNKNOWN');self.assertTrue(all(r['status']=='UNKNOWN' and not r['complete'] and not r['products'] for r in rows[index:]))
                    partial=partial or any(0<r['pair_points_tested']<65025 for r in rows if r['status']=='UNKNOWN')
                finally:
                    selector.close()
                    if process.poll() is None:process.kill();process.communicate()
            if partial:break
        self.assertTrue(partial,'control did not observe a partially enumerated case at STOP')

    def test_strict_frontend_target_and_nonnegative_case_index(self):
        core=[1,0,0,0,0,0,0,0]
        for target in [-1,10]:
            with self.assertRaises(ValueError):encode_case(core,[2,2,2],target,0)
            with self.assertRaises(ValueError):make_request('invalid','a'*64,core,[2,2,2],target,0)
        request=make_request('valid','a'*64,core,[2,2,2],1,0);row=self.run_cases([controls.case(core,[2,2,2],1,0)])[0]
        with self.assertRaises(ValueError):bind_response(dict(row,case_index=-1),request,-1,core)

if __name__=='__main__':unittest.main()
