import pathlib,json,hashlib,datetime,collections,sys
from mmsearch.recombine import canonical_terms
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate
from scripts.scan_slice_compressions import _freeze_first_winner
p=pathlib.Path('artifacts/rl_campaign_20261102T210735Z');out=p/'inverse-polarization-audit1';out.mkdir(exist_ok=False)
paths=sorted((p/'fixed1-1/verified').glob('*.json'));events=[];matches=0;best=999;winner=False
for path in paths:
 raw=path.read_bytes();obj=json.loads(raw);terms=set(canonical_terms(obj));cubes={a for a,b,c in terms if a==b==c};seen=set()
 for t in sorted(terms):
  count=collections.Counter(t)
  if len(count)!=2:continue
  a=next(x for x,n in count.items() if n==2);b=next(x for x,n in count.items() if n==1);key=tuple(sorted((a,b)))
  if key in seen:continue
  seen.add(key);c=a^b
  if c not in cubes:continue
  orbit1={(a,a,b),(a,b,a),(b,a,a)};orbit2={(a,b,b),(b,a,b),(b,b,a)}
  if not (orbit1|orbit2)<=(terms):continue
  identity=orbit1|orbit2|{(a,a,a),(b,b,b),(c,c,c)};derived=encode_candidate(sorted(terms^identity),5,method='exact_inverse_cube_polarization',source=str(path),a=a,b=b,c=c)
  sr=verify_candidate(obj,random_trials=0);vr=verify_candidate(derived,random_trials=16)
  assert sr['valid'] and vr['valid'] and vr['exact_entries_checked']==15625
  rank=vr['rank'];best=min(best,rank);matches+=1;h=hashlib.sha256(raw).hexdigest();event=dict(source=str(path),source_sha256=h,source_rank=len(terms),derived_rank=rank,a=a,b=b,c=c,verification=vr)
  (out/f'match-{matches:04d}.json').write_text(json.dumps(derived,sort_keys=True,indent=2)+'\n');events.append(event)
  if rank<=92:_freeze_first_winner(out,derived);winner=True;break
 if winner:break
report=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),method='inverse exact binary cubic polarization',sources_considered=len(paths),matches=matches,best_derived_rank=None if best==999 else best,winner=winner,events=events,scope='Only explicit cube plus paired repeated-factor cyclic-orbit patterns; failure is not rank lower bound')
(out/'result.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='events'}))
