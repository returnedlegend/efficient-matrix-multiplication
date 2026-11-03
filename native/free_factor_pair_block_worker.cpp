// Exact static two-kernel-direction block scan. No floating coefficients.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <unordered_set>
#include <utility>
#include <vector>
using U=uint64_t;using V=std::vector<uint32_t>;using Column=std::array<U,10>;
static volatile std::sig_atomic_t stopped=0;static void stop_handler(int){stopped=1;}
static void atomic_text(const std::string&path,const std::string&data){auto p=std::filesystem::path(path);if(p.has_parent_path())std::filesystem::create_directories(p.parent_path());std::ofstream f(path+".tmp");if(!f)throw std::runtime_error("cannot write");f<<data;f.close();if(!f)throw std::runtime_error("write failed");std::filesystem::rename(path+".tmp",path);}
static void write_vectors(const std::string&path,const V&v){std::ostringstream s;for(auto x:v)s<<x<<'\n';atomic_text(path,s.str());}
struct Options{std::string input,output,input_sha,baseline_sha;double seconds=600,checkpoint=15;int target=92,start_i=0,start_j=1;U max_pairs=0;};
static Options options(int argc,char**argv){Options o;for(int k=1;k<argc;++k){std::string key=argv[k];if(k+1==argc)throw std::runtime_error("missing option value");std::string v=argv[++k];
 if(key=="--input")o.input=v;else if(key=="--output")o.output=v;else if(key=="--seconds")o.seconds=std::stod(v);else if(key=="--target")o.target=std::stoi(v);else if(key=="--start-i")o.start_i=std::stoi(v);else if(key=="--start-j")o.start_j=std::stoi(v);else if(key=="--max-pairs")o.max_pairs=std::stoull(v);else if(key=="--checkpoint-seconds")o.checkpoint=std::stod(v);else if(key=="--input-sha256")o.input_sha=v;else if(key=="--baseline-sha256")o.baseline_sha=v;else throw std::runtime_error("unknown option "+key);}
 if(o.input.empty()||o.output.empty()||!std::isfinite(o.seconds)||o.seconds<0||!std::isfinite(o.checkpoint)||o.checkpoint<=0||o.target<0||o.start_i<0||o.start_j<=o.start_i)throw std::runtime_error("invalid options");
 for(auto&s:{o.input_sha,o.baseline_sha})if(!s.empty()&&(s.size()!=64||s.find_first_not_of("0123456789abcdef")!=std::string::npos))throw std::runtime_error("invalid hash");
 return o;}
struct Bag{std::array<uint32_t,8> value{};std::array<int,8> frequency{};int size=0,zeros=0,maximum=0;
 void add(uint32_t w){zeros+=w==0;for(int i=0;i<size;++i)if(value[i]==w){maximum=std::max(maximum,++frequency[i]);return;}value[size]=w;frequency[size++]=1;maximum=std::max(maximum,1);}
 int count(uint32_t w)const{for(int i=0;i<size;++i)if(value[i]==w)return frequency[i];return 0;}};
struct Opt{uint32_t d=0,e=0;int score=0,zeros=0,upper=0;};
static Opt optimize(const Bag&a,const Bag&b,const Bag&c){Opt out;out.zeros=a.zeros+b.zeros+c.zeros;out.score=out.zeros;out.upper=a.maximum+b.maximum+c.maximum;
 auto consider=[&](uint32_t d,uint32_t e){int score=a.count(d)+b.count(e)+c.count(d^e);if(score>out.score||(score==out.score&&std::pair<uint32_t,uint32_t>{d,e}<std::pair<uint32_t,uint32_t>{out.d,out.e})){out.d=d;out.e=e;out.score=score;}};
 for(int i=0;i<a.size;++i){consider(a.value[i],0);for(int j=0;j<b.size;++j)consider(a.value[i],b.value[j]);for(int j=0;j<c.size;++j)consider(a.value[i],a.value[i]^c.value[j]);}
 for(int i=0;i<b.size;++i){consider(0,b.value[i]);for(int j=0;j<c.size;++j)consider(b.value[i]^c.value[j],b.value[i]);}
 for(int i=0;i<c.size;++i){consider(0,c.value[i]);consider(c.value[i],0);}return out;}
int main(int argc,char**argv)try{
 Options o=options(argc,argv);rlimit limit{512ULL*1024*1024,512ULL*1024*1024};if(setrlimit(RLIMIT_AS,&limit))throw std::runtime_error("memory limit failed");
 std::ifstream in(o.input);std::string magic;int n,p,c;std::array<int,3> perm{};
 if(!(in>>magic>>n>>p>>c)||magic!="MMKERNEL1"||n<2||n>5||p<1||p>10000||c<0||c>50000)throw std::runtime_error("invalid header");
 if(!(in>>perm[0]>>perm[1]>>perm[2]))throw std::runtime_error("missing permutation");
 auto sorted=perm;std::sort(sorted.begin(),sorted.end());if(sorted!=std::array<int,3>{0,1,2})throw std::runtime_error("invalid permutation");
 int width=n*n;U bound=U(1)<<width;V baseline(p);std::vector<Column> columns(p);std::vector<std::vector<int>> rows(p);std::unordered_set<U> unique_pairs;
 for(int g=0;g<p;++g){U a,b,w;if(!(in>>a>>b>>w)||!a||!b||a>=bound||b>=bound||w>=bound)throw std::runtime_error("invalid pair/model");if(!unique_pairs.insert((a<<25)|b).second)throw std::runtime_error("duplicate pair");baseline[g]=w;columns[g].fill(0);for(U x=a;x;x&=x-1)for(U y=b;y;y&=y-1){int r=__builtin_ctzll(x)*width+__builtin_ctzll(y);columns[g][r/64]^=U(1)<<(r%64);rows[g].push_back(r);}}
 std::vector<std::vector<int>> supports(c);for(int k=0;k<c;++k){int kind,size;if(!(in>>kind>>size)||kind<0||kind>2||size<3||size>8)throw std::runtime_error("invalid short circuit");Column total{};std::unordered_set<int> distinct;for(int j=0;j<size;++j){int g;if(!(in>>g)||g<0||g>=p||!distinct.insert(g).second)throw std::runtime_error("invalid group");supports[k].push_back(g);for(int x=0;x<10;++x)total[x]^=columns[g][x];}if(std::any_of(total.begin(),total.end(),[](U x){return x;}))throw std::runtime_error("nonkernel circuit rejected");std::sort(supports[k].begin(),supports[k].end());}
 std::string extra;if(in>>extra)throw std::runtime_error("trailing input");V target(width*width);for(int i=0;i<n;++i)for(int j=0;j<n;++j)for(int k=0;k<n;++k){std::array<int,3> xyz{i*n+j,j*n+k,k*n+i};target[xyz[perm[0]]*width+xyz[perm[1]]]^=uint32_t(1)<<xyz[perm[2]];}
 auto check=[&](const V&w){V observed(width*width);for(int g=0;g<p;++g){if(w[g]>=bound)throw std::runtime_error("mask out of range");if(w[g])for(int r:rows[g])observed[r]^=w[g];}if(observed!=target)throw std::runtime_error("original PW=Y failed");};check(baseline);
 int baseline_rank=std::count_if(baseline.begin(),baseline.end(),[](uint32_t x){return x;});V best=baseline;int best_rank=baseline_rank;
 struct Single{uint32_t d;int delta;};std::vector<Single> single(c);int minimum_single=0;
 for(int i=0;i<c;++i){Bag a;for(int g:supports[i])a.add(baseline[g]);uint32_t d=0;for(int j=0;j<a.size;++j)if(a.frequency[j]>a.count(d)||(a.frequency[j]==a.count(d)&&a.value[j]<d))d=a.value[j];single[i]={d,a.zeros-a.count(d)};minimum_single=std::min(minimum_single,single[i].delta);}
 U total=U(c)*(c-1)/2,considered=0,disjoint_pruned=0,bound_pruned=0,exact=0,disjoint=0;int next_i=o.start_i,next_j=o.start_j,last_i=-1,last_j=-1;std::string status="RUNNING",reason="";
 if(c>1&&(o.start_i>c-1||(o.start_i<c-1&&o.start_j>=c)))throw std::runtime_error("cursor outside catalog");
 auto ordinal=[&](int i,int j){return i>=c-1?total:U(i)*(2*U(c)-i-1)/2+U(j-i-1);};U prefix=ordinal(o.start_i,o.start_j);
 auto start=std::chrono::steady_clock::now();auto elapsed=[&](){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();};
 auto checkpoint=[&](){check(best);write_vectors(o.output+".best.w.txt",best);write_vectors(o.output+".current.w.txt",best);std::ostringstream s;
 s<<"{\"engine\":\"exact-two-kernel-block-scan-v1\",\"status\":\""<<status<<"\",\"reason\":\""<<reason<<"\",\"dimension\":"<<n<<",\"pair_count\":"<<p<<",\"circuit_count\":"<<c<<",\"target_rank\":"<<o.target<<",\"best_rank\":"<<best_rank<<",\"current_rank\":"<<best_rank<<",\"baseline_rank\":"<<baseline_rank<<",\"target_reached\":"<<(best_rank<=o.target?"true":"false")<<",\"linear_exact\":true,\"tensor_invariant_checked\":true,\"full_matrix_verified\":false,\"steps\":"<<considered<<",\"pairs_total\":"<<total<<",\"prefix_pairs_skipped\":"<<prefix<<",\"pairs_considered\":"<<considered<<",\"disjoint_pairs\":"<<disjoint<<",\"disjoint_pruned\":"<<disjoint_pruned<<",\"bound_pruned\":"<<bound_pruned<<",\"exact_evaluated\":"<<exact<<",\"minimum_single_delta\":"<<minimum_single<<",\"next_i\":"<<next_i<<",\"next_j\":"<<next_j<<",\"last_complete_i\":"<<last_i<<",\"last_complete_j\":"<<last_j<<",\"elapsed_seconds\":"<<elapsed()<<",\"seconds_budget\":"<<o.seconds<<",\"input_sha256\":\""<<o.input_sha<<"\",\"baseline_sha256\":\""<<o.baseline_sha<<"\"}\n";atomic_text(o.output+".stats.json",s.str());};
 std::signal(SIGTERM,stop_handler);std::signal(SIGINT,stop_handler);checkpoint();double next_checkpoint=o.checkpoint;bool done=false;
 if(best_rank<=o.target){status="MODEL_FOUND";reason="baseline already meets target";done=true;}
 for(int i=o.start_i;i<c-1&&!done;++i)for(int j=(i==o.start_i?o.start_j:i+1);j<c;++j){
   if((considered&255)==0&&(elapsed()>=o.seconds||stopped)){status="UNKNOWN";reason=stopped?"interrupted":"wall budget";done=true;break;}
   if(o.max_pairs&&considered>=o.max_pairs){status="UNKNOWN";reason="pair budget";done=true;break;}
   std::array<int,8> ga{},gb{},gc{};int na=0,nb=0,nc=0;size_t x=0,y=0;auto&a=supports[i];auto&b=supports[j];
   while(x<a.size()||y<b.size()){if(y==b.size()||(x<a.size()&&a[x]<b[y]))ga[na++]=a[x++];else if(x==a.size()||b[y]<a[x])gb[nb++]=b[y++];else{gc[nc++]=a[x];++x;++y;}}
   Opt optimum;bool hit=false;
   if(!nc){++disjoint;optimum.d=single[i].d;optimum.e=single[j].d;hit=baseline_rank+single[i].delta+single[j].delta<=o.target;if(!hit)++disjoint_pruned;}
   else{Bag aa,bb,cc;for(int k=0;k<na;++k)aa.add(baseline[ga[k]]);for(int k=0;k<nb;++k)bb.add(baseline[gb[k]]);for(int k=0;k<nc;++k)cc.add(baseline[gc[k]]);
     int zeros=aa.zeros+bb.zeros+cc.zeros,upper=aa.maximum+bb.maximum+cc.maximum;
     if(upper<zeros+baseline_rank-o.target)++bound_pruned;else{++exact;optimum=optimize(aa,bb,cc);hit=baseline_rank+optimum.zeros-optimum.score<=o.target;}}
   ++considered;last_i=i;last_j=j;next_i=j+1<c?i:i+1;next_j=j+1<c?j+1:i+2;
   if(hit){V moved=baseline;for(int g:supports[i])moved[g]^=optimum.d;for(int g:supports[j])moved[g]^=optimum.e;check(moved);int rank=std::count_if(moved.begin(),moved.end(),[](uint32_t z){return z;});if(rank>o.target)throw std::runtime_error("block objective/actual rank mismatch");best=moved;best_rank=rank;std::ostringstream witness;witness<<"{\"circuit_i\":"<<i<<",\"circuit_j\":"<<j<<",\"d\":"<<optimum.d<<",\"e\":"<<optimum.e<<",\"before_rank\":"<<baseline_rank<<",\"after_rank\":"<<rank<<",\"linear_verified\":true}\n";atomic_text(o.output+".solution.json",witness.str());status="MODEL_FOUND";reason="pending independent global verification";done=true;break;}
   if((considered&4095)==0&&elapsed()>=next_checkpoint){checkpoint();next_checkpoint=elapsed()+o.checkpoint;}
 }
 if(!done){status="NO_TARGET";reason="finite pair suffix exhausted";}checkpoint();std::cout<<status<<" pairs="<<considered<<" best_rank="<<best_rank<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"pair_block_worker: "<<e.what()<<'\n';return 1;}
