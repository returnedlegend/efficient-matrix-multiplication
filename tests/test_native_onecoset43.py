"""Standalone native decoder controls only; never open a production n5 core."""
import itertools,json,os,random,selectors,shutil,signal,subprocess,tempfile,time,unittest
from pathlib import Path
from mmsearch.compact_coset43 import mode_slices,pair_column,expand_products,solve_core as slow
from mmsearch.compact_coset_fast43 import solve_core as fast
from tests.test_compact_coset43 import brute_tiny
from mmsearch.onecoset_codec43 import verify_sat_result,encode_case,make_request,bind_response

ROOT=Path(__file__).resolve().parents[1]

def rank(values):
    pivots={}
    for x in values:
        while x:
            p=x.bit_length()-1
            if p not in pivots:pivots[p]=x;break
            x^=pivots[p]
    return len(pivots)

def case(core,shape,target,axis):
    slices,other=mode_slices(core,shape,axis)
    return (shape[other[0]],shape[other[1]],shape[axis],target,slices)

def text(cases):
    return 'ONECOSET43 1\n'+''.join(' '.join(map(str,[a,b,f,r,*slices]))+'\n' for a,b,f,r,slices in cases)

@unittest.skipUnless(shutil.which('g++'),'C++ compiler unavailable')
class NativeOneCosetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.binary=Path(os.environ.get('ONECOSET43_BINARY',Path(cls.temp.name)/'native'))
        if not cls.binary.exists():subprocess.run(['g++','-std=c++17','-O2',str(ROOT/'native/onecoset43.cpp'),'-o',str(cls.binary)],check=True,timeout=12)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def run_cases(self,cases,extra=(),timeout=12):
        run=subprocess.run([str(self.binary),'--seconds','10',*extra],input=text(cases),capture_output=True,text=True,timeout=timeout)
        self.assertEqual(run.returncode,0,run.stderr);results=[json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual(len(results),len(cases));self.assertEqual([r['case_index'] for r in results],list(range(len(cases))))
        return results
    def witness(self,result,data):
        a,b,f,target,slices=data;self.assertTrue(result['complete']);self.assertEqual(result['mode_rank'],rank(slices))
        if result['status']!='SAT':return
        self.assertTrue(result['full_original_slices_verified']);self.assertEqual(result['core_entries_checked'],a*b*f)
        products=result['products'];self.assertLessEqual(len(products),target)
        for left,right,free in products:self.assertTrue(0<left<1<<a and 0<right<1<<b and 0<free<1<<f)
        for coordinate,expected in enumerate(slices):
            actual=0
            for left,right,free in products:
                if free>>coordinate&1:actual^=pair_column(left,right,b)
            self.assertEqual(actual,expected)
        support=result['pair_support'];columns=[p['column'] for p in support];self.assertEqual(rank(columns),len(columns))
        basis=result['space_basis'];self.assertEqual(rank(basis),len(basis));self.assertTrue(all(x in slices for x in basis))
        for x in slices:self.assertEqual(rank([*basis,x]),len(basis))
        for j,p in enumerate(support):
            self.assertEqual(p['column'],pair_column(p['left'],p['right'],b));self.assertLess(p['lambda'],1<<len(basis))
            residual=p['column']
            for k,value in enumerate(basis):
                if p['lambda']>>k&1:residual^=value
            self.assertEqual(residual,0 if j<result['inside_rank'] else result['quotient_representative'])

    def test_all256_2931_bounds_all_axes_against_independent_bfs_and_python(self):
        truth=brute_tiny();cases=[];expected=[];contexts=[]
        for packed in range(256):
            core=[packed>>i&1 for i in range(8)]
            for axis in range(3):
                slices,_=mode_slices(core,[2,2,2],axis);d=rank(slices)
                for target in range(d+2):cases.append(case(core,[2,2,2],target,axis));expected.append(truth[packed]<=target);contexts.append((core,axis,target))
        self.assertEqual(len(cases),2931)
        for mode in ['lex','gray']:
            results=self.run_cases(cases,('--enumeration',mode));branches=set()
            for data,result,want,context in zip(cases,results,expected,contexts):
                self.assertEqual(result['status']=='SAT',want,(mode,context,result));self.assertTrue(result['complete']);self.witness(result,data);branches.add(result['case'])
                core,axis,target=context;reference=fast(core,[2,2,2],target,axis=axis);self.assertEqual(result['status'],reference['status'])
                if result['status']=='SAT':
                    other=[j for j in range(3) if j!=axis];products=[]
                    for left,right,free in result['products']:
                        term=[0,0,0];term[other[0]]=left;term[other[1]]=right;term[axis]=free;products.append(term)
                    self.assertEqual(expand_products(products,[2,2,2]),core)
                    self.assertTrue(verify_sat_result(result,core,[2,2,2],target,axis)['valid'])
                    self.assertEqual(encode_case(core,[2,2,2],target,axis).strip(),' '.join(map(str,[*data[:4],*data[4]])))
            self.assertIn('single_nonzero_coset_star_differences_span',branches)

    def test_all512_matrices_rankone_and_ranktwo(self):
        cases=[];expected=[]
        for matrix in range(512):
            d=rank([(matrix>>(3*i))&7 for i in range(3)])
            for target in [1,2]:
                cases.append((3,3,1,target,[matrix]));expected.append('UNKNOWN' if matrix==0 and target==2 else 'SAT' if d<=target else 'LOCAL_UNSAT')
        for result,data,want in zip(self.run_cases(cases),cases,expected):
            self.assertEqual(result['status'],want,(data,result))
            if want!='UNKNOWN':self.witness(result,data)

    def test_random3x3_all_axes_against_independent_python(self):
        rng=random.Random(431103);cases=[];expected=[]
        for _ in range(24):
            core=[rng.randrange(2) for _ in range(27)]
            for axis in range(3):
                d=rank(mode_slices(core,[3,3,3],axis)[0])
                for target in [max(0,d-1),d,d+1]:
                    cases.append(case(core,[3,3,3],target,axis));expected.append(slow(core,[3,3,3],target,axis=axis)['status'])
        for result,data,want in zip(self.run_cases(cases),cases,expected):self.assertEqual(result['status'],want,(data,result));self.witness(result,data)

    def test_highdim_rank9_hyperplane_all_original_slices(self):
        allones=(1<<64)-1;slices=[allones^(1<<(9*i)) for i in range(8)]
        cases=[(8,8,8,8,slices),(8,8,8,9,slices)]
        results=self.run_cases(cases)
        self.assertEqual(results[0]['status'],'LOCAL_UNSAT');self.assertEqual(results[0]['inside_rank'],0)
        self.assertEqual(results[1]['status'],'SAT');self.assertEqual(len(results[1]['products']),9);self.witness(results[1],cases[1])
        original={(1<<i,1<<i) for i in range(8)}|{(255,255)}
        self.assertEqual({(p['left'],p['right']) for p in results[1]['pair_support']},original)
        core=[0]*512
        for k,matrix in enumerate(slices):
            for i in range(8):
                for j in range(8):core[(i*8+j)*8+k]=matrix>>(i*8+j)&1
        self.assertEqual(slow(core,[8,8,8],9,axis=2,max_points=65025)['status'],'SAT')

    def test_zero_duplicate_dependent_slices_and_uint64_boundaries(self):
        cases=[(0,8,3,0,[0,0,0]),(8,8,0,0,[]),(8,8,8,1,[1,0,1,1,0,0,1,0]),(2,2,5,2,[1,8,9,0,1]),(8,8,1,1,[1<<63]),(8,8,1,1,[(1<<64)-1])]
        for result,data in zip(self.run_cases(cases),cases):self.assertEqual(result['status'],'SAT');self.witness(result,data)

    def test_scope_pointcaps_deadlines_markers_and_malformed(self):
        cases=[(2,2,2,2,[1,8]),(2,2,2,3,[1,8])]
        for extra in [('--seconds','0'),('--deadline-unix','0'),('--max-points','2')]:
            for result in self.run_cases(cases,extra):self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete']);self.assertFalse(result['products'])
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'STOP';marker.write_text('stop')
            for result in self.run_cases(cases,('--stop-marker',str(marker))):self.assertEqual(result['status'],'UNKNOWN')
        raw='ONECOSET43 1\n9 1 1 1 1\n1 9 1 1 1\n1 1 9 1 1\n2 2 1 1 16\n2 2 1 -1 1\n2 2 2 4 1 8\n8 8 1 1 18446744073709551616\n2 2 2 2 1\n'
        run=subprocess.run([str(self.binary)],input=raw,capture_output=True,text=True,timeout=2);self.assertEqual(run.returncode,0)
        for row in map(json.loads,run.stdout.splitlines()):self.assertEqual(row['status'],'UNKNOWN');self.assertFalse(row['complete'])

    def test_sigterm_owned_batch_preserves_unknown_unfinished_cases(self):
        matrix=sum(1<<(9*i) for i in range(8));cases=[(8,8,1,2,[matrix])]*300
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input.txt';path.write_text(text(cases))
            process=subprocess.Popen([str(self.binary),'--input',str(path),'--seconds','60'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                first=process.stdout.readline();self.assertTrue(first);process.send_signal(signal.SIGTERM);rest,error=process.communicate(timeout=3)
                self.assertEqual(process.returncode,0,error);results=[json.loads(line) for line in (first+rest).splitlines()]
                self.assertEqual(len(results),300);self.assertTrue(any(r['status']=='UNKNOWN' for r in results));self.assertEqual(results[-1]['status'],'UNKNOWN')
            finally:
                if process.poll() is None:process.kill();process.communicate()

    def test_codec_rejects_corrupt_witness_and_unknown(self):
        core=[1,0,0,0,0,0,0,1];data=case(core,[2,2,2],2,0);result=self.run_cases([data])[0]
        self.assertTrue(verify_sat_result(result,core,[2,2,2],2,0)['valid'])
        corrupt=json.loads(json.dumps(result));corrupt['products'][0][2]^=1
        with self.assertRaises(ValueError):verify_sat_result(corrupt,core,[2,2,2],2,0)
        with self.assertRaises(ValueError):verify_sat_result(dict(result,status='UNKNOWN'),core,[2,2,2],2,0)

    def test_interactive_request_response_flush_and_ledger_alignment(self):
        cores=[[1,0,0,0,0,0,0,1],[1,0,1,0,0,0,0,0]]
        process=subprocess.Popen([str(self.binary),'--seconds','10'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
        try:
            process.stdin.write('ONECOSET43 1\n');process.stdin.flush()
            for index,core in enumerate(cores):
                request=make_request('synthetic-'+str(index),'a'*64,core,[2,2,2],2,index)
                process.stdin.write(request['input_line']);process.stdin.flush()
                self.assertTrue(selector.select(timeout=2),'native failed to flush a response before next request')
                result=json.loads(process.stdout.readline());bound=bind_response(result,request,index,core)
                self.assertEqual(bound['case_id'],request['case_id']);self.assertEqual(bound['source_sha256'],'a'*64)
                with self.assertRaises(ValueError):bind_response(result,request,index+1,core)
                with self.assertRaises(ValueError):bind_response(result,dict(request,input_line_sha256='b'*64),index,core)
            process.stdin.close();self.assertEqual(process.wait(timeout=2),0)
        finally:
            selector.close()
            if process.poll() is None:process.kill();process.wait()
            for stream in [process.stdin,process.stdout,process.stderr]:
                if stream and not stream.closed:stream.close()

    def test_padded_known_two_coset_negative_forces_full65025(self):
        data=(8,8,2,3,[(1<<0)|(1<<9),(1<<18)|(1<<27)])
        result=self.run_cases([data])[0]
        self.assertEqual(result['status'],'LOCAL_UNSAT');self.assertTrue(result['complete'])
        self.assertEqual(result['mode_rank'],2);self.assertEqual(result['inside_rank'],0);self.assertEqual(result['pair_points_tested'],65025)
        core=[0]*128
        for k,matrix in enumerate(data[-1]):
            for i,j in itertools.product(range(8),repeat=2):core[(i*8+j)*2+k]=matrix>>(i*8+j)&1
        self.assertEqual(slow(core,[8,8,2],3,axis=2)['status'],'LOCAL_UNSAT')

if __name__=='__main__':unittest.main()
