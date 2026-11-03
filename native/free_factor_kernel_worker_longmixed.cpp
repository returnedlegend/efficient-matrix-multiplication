// Longmixed sampler:50% uniform support>8 catalog +50% original wide mixture.
// Algebra, PW invariant, acceptance guards and resource bounds unchanged.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <unordered_set>
#include <vector>

using U=uint64_t;
using V=std::vector<uint32_t>;
using Column=std::array<U,10>;
struct Circuit {int kind;std::vector<int> groups;};
static volatile std::sig_atomic_t stopped=0;
static void stop_handler(int){stopped=1;}
static U mix(U x){x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
static U fingerprint(const V&v){U h=0;for(size_t i=0;i<v.size();++i)if(v[i])h^=mix((U(i)<<32)|v[i]);return h;}
static void atomic_text(const std::string&path,const std::string&data){
    auto p=std::filesystem::path(path);if(p.has_parent_path())std::filesystem::create_directories(p.parent_path());
    std::ofstream f(path+".tmp");if(!f)throw std::runtime_error("cannot write "+path);f<<data;f.close();
    if(!f)throw std::runtime_error("write failed "+path);
    std::filesystem::rename(path+".tmp",path);
}
static void write_vectors(const std::string&path,const V&v){std::ostringstream s;for(auto x:v)s<<x<<'\n';atomic_text(path,s.str());}
struct Options {
    std::string input,output,profile="longmixed";
    U seed=0,steps=1000000000000ULL,plus_every=500,restart_every=100000000,archive_every=1000;
    int target=92,headroom=6,archive_size=16,memory_mb=512;
    double seconds=1800,checkpoint_seconds=15;
};
static Options options(int argc,char**argv){
    Options o;
    for(int i=1;i<argc;++i){std::string k=argv[i];if(i+1==argc)throw std::runtime_error("missing option value");std::string v=argv[++i];
        if(k=="--input")o.input=v;else if(k=="--output")o.output=v;else if(k=="--profile")o.profile=v;
        else if(k=="--seed")o.seed=std::stoull(v);else if(k=="--steps")o.steps=std::stoull(v);
        else if(k=="--plus-every")o.plus_every=std::stoull(v);else if(k=="--restart-every")o.restart_every=std::stoull(v);
        else if(k=="--archive-every")o.archive_every=std::stoull(v);else if(k=="--target")o.target=std::stoi(v);
        else if(k=="--headroom")o.headroom=std::stoi(v);else if(k=="--archive-size")o.archive_size=std::stoi(v);
        else if(k=="--memory-mb")o.memory_mb=std::stoi(v);else if(k=="--seconds")o.seconds=std::stod(v);
        else if(k=="--checkpoint-seconds")o.checkpoint_seconds=std::stod(v);else throw std::runtime_error("unknown option "+k);
    }
    if(o.input.empty()||o.output.empty()||o.target<0||o.headroom<0||o.headroom>32||o.archive_size<1||o.archive_size>16||
       o.memory_mb<64||o.memory_mb>512||!o.plus_every||!o.restart_every||!o.archive_every||!std::isfinite(o.seconds)||
       o.seconds<0||!std::isfinite(o.checkpoint_seconds)||o.checkpoint_seconds<=0||
       (o.profile!="mixed"&&o.profile!="short"&&o.profile!="wide"&&o.profile!="longmixed"))throw std::runtime_error("invalid options");
    return o;
}

int main(int argc,char**argv)try{
    Options o=options(argc,argv);rlimit limit{rlim_t(o.memory_mb)*1024*1024,rlim_t(o.memory_mb)*1024*1024};
    if(setrlimit(RLIMIT_AS,&limit))throw std::runtime_error("cannot enforce memory limit");
    std::ifstream input(o.input);std::string magic;int n,p,count;std::array<int,3> permutation{};
    if(!(input>>magic>>n>>p>>count)||magic!="MMKERNELWIDE1"||n<2||n>5||p<1||p>10000||count<0||count>50000)
        throw std::runtime_error("invalid kernel input header");
    if(!(input>>permutation[0]>>permutation[1]>>permutation[2]))throw std::runtime_error("missing mode permutation");
    auto sorted=permutation;std::sort(sorted.begin(),sorted.end());if(sorted!=std::array<int,3>{0,1,2})throw std::runtime_error("invalid mode permutation");
    int width=n*n;U bound=U(1)<<width;V current(p);std::vector<Column> columns(p);std::vector<std::vector<int>> support(p);
    std::unordered_set<std::string> unique_pairs;
    for(int g=0;g<p;++g){U a,b,w;if(!(input>>a>>b>>w)||!a||!b||a>=bound||b>=bound||w>=bound)throw std::runtime_error("invalid pair/vector");
        auto key=std::to_string(a)+","+std::to_string(b);if(!unique_pairs.insert(key).second)throw std::runtime_error("duplicate fixed pair");
        current[g]=uint32_t(w);columns[g].fill(0);
        for(U x=a;x;x&=x-1)for(U y=b;y;y&=y-1){int r=__builtin_ctzll(x)*width+__builtin_ctzll(y);columns[g][r/64]^=U(1)<<(r%64);support[g].push_back(r);}
    }
    std::vector<Circuit> circuits;std::array<std::vector<int>,3> kinds;std::vector<int> long_catalog;
    for(int ci=0;ci<count;++ci){int kind,size;if(!(input>>kind>>size)||kind<0||kind>2||size<3||size>128)throw std::runtime_error("invalid circuit header");
        if((kind==0&&size!=3)||(kind==1&&size!=4))throw std::runtime_error("circuit class/size mismatch");
        Circuit c{kind,{}};Column total{};std::unordered_set<int> distinct;
        for(int j=0;j<size;++j){int g;if(!(input>>g)||g<0||g>=p||!distinct.insert(g).second)throw std::runtime_error("invalid circuit index");
            c.groups.push_back(g);for(size_t k=0;k<total.size();++k)total[k]^=columns[g][k];}
        if(std::any_of(total.begin(),total.end(),[](U x){return x;}))throw std::runtime_error("nonkernel circuit rejected");
        kinds[kind].push_back(ci);if(size>8)long_catalog.push_back(ci);circuits.push_back(c);
    }
    if(o.profile=="longmixed"&&long_catalog.empty())throw std::runtime_error("longmixed requires support>8 catalog");
    std::string extra;if(input>>extra)throw std::runtime_error("trailing kernel input tokens");
    V target(width*width);
    for(int i=0;i<n;++i)for(int j=0;j<n;++j)for(int k=0;k<n;++k){std::array<int,3> coords{i*n+j,j*n+k,k*n+i};
        target[coords[permutation[0]]*width+coords[permutation[1]]]^=uint32_t(1)<<coords[permutation[2]];}
    auto check=[&](const V&state){if(int(state.size())!=p)throw std::runtime_error("state length mismatch");V observed(width*width);
        for(int g=0;g<p;++g){if(state[g]>=bound)throw std::runtime_error("vector outside width");if(state[g])for(int row:support[g])observed[row]^=state[g];}
        if(observed!=target)throw std::runtime_error("original PW=Y invariant failed");};
    check(current);
    V best=current;std::vector<int> active,position(p,-1);
    auto rebuild=[&](){active.clear();std::fill(position.begin(),position.end(),-1);for(int g=0;g<p;++g)if(current[g]){position[g]=active.size();active.push_back(g);}};
    rebuild();int best_rank=active.size();U hash=fingerprint(current);std::mt19937_64 rng(o.seed);
    auto randn=[&](size_t size){return size_t(rng()%size);};
    std::vector<V> archive{best};std::vector<U> archive_hash{hash};std::vector<bool> dirty{true};std::unordered_set<U> seen{hash};
    U steps=0,accepted=0,rejected=0,uphill=0,restarts=0,archive_additions=1,long_attempts=0,long_accepted=0;std::array<U,3> attempts{};U explicit_long_draws=0,wide_mixture_draws=0,explicit_long_accepted=0,wide_mixture_long_attempts=0,wide_mixture_long_accepted=0;
    std::vector<std::pair<U,int>> history{{0,best_rank}};
    auto start=std::chrono::steady_clock::now();auto elapsed=[&](){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();};
    auto checkpoint=[&](){check(best);check(current);write_vectors(o.output+".best.w.txt",best);write_vectors(o.output+".current.w.txt",current);
        for(size_t i=0;i<archive.size();++i)if(dirty[i]){check(archive[i]);write_vectors(o.output+".archive/"+std::to_string(i)+".w.txt",archive[i]);dirty[i]=false;}
        std::ostringstream s;s<<"{\"engine\":\"native-fixed-pair-kernel-walk-longmixed-v1\",\"raw_state_kind\":\"free-factor-vector-model\","
          <<"\"dimension\":"<<n<<",\"width\":"<<width<<",\"pair_count\":"<<p<<",\"circuit_count\":"<<count<<",\"seed\":"<<o.seed
          <<",\"steps\":"<<steps<<",\"step_budget\":"<<o.steps<<",\"elapsed_seconds\":"<<elapsed()<<",\"seconds_budget\":"<<o.seconds
          <<",\"best_rank\":"<<best_rank<<",\"current_rank\":"<<active.size()<<",\"target_rank\":"<<o.target
          <<",\"target_reached\":"<<(best_rank<=o.target?"true":"false")<<",\"headroom\":"<<o.headroom<<",\"max_rank\":"<<best_rank+o.headroom
          <<",\"linear_exact\":true,\"tensor_invariant_checked\":true,\"full_matrix_verified\":false,\"accepted_moves\":"<<accepted
          <<",\"rejected_moves\":"<<rejected<<",\"uphill_moves\":"<<uphill<<",\"restarts\":"<<restarts
          <<",\"archive_size\":"<<archive.size()<<",\"archive_additions\":"<<archive_additions
          <<",\"three_attempts\":"<<attempts[0]<<",\"four_attempts\":"<<attempts[1]<<",\"combo_attempts\":"<<attempts[2]
          <<",\"max_supported_circuit_size\":128,\"long_support_attempts\":"<<long_attempts<<",\"long_support_accepted\":"<<long_accepted<<",\"profile\":\""<<o.profile<<"\",\"plus_every\":"<<o.plus_every<<",\"restart_every\":"<<o.restart_every
          <<",\"long_catalog_size\":"<<long_catalog.size()<<",\"explicit_long_draws\":"<<explicit_long_draws<<",\"wide_mixture_draws\":"<<wide_mixture_draws
          <<",\"explicit_long_accepted\":"<<explicit_long_accepted<<",\"wide_mixture_long_attempts\":"<<wide_mixture_long_attempts<<",\"wide_mixture_long_accepted\":"<<wide_mixture_long_accepted
          <<",\"sampler\":\"longmixed:50pct-uniform-long-plus50pct-original-wide\""
          <<",\"memory_limit_mb\":"<<o.memory_mb<<",\"stopped_by_signal\":"<<(stopped?"true":"false")<<",\"history\":[";
        for(size_t i=0;i<history.size();++i){if(i)s<<',';s<<"{\"step\":"<<history[i].first<<",\"rank\":"<<history[i].second<<'}';}s<<"]}\n";
        atomic_text(o.output+".stats.json",s.str());};
    std::signal(SIGTERM,stop_handler);std::signal(SIGINT,stop_handler);checkpoint();double next=o.checkpoint_seconds;
    while(steps<o.steps&&best_rank>o.target&&!stopped&&!circuits.empty()){
        if((steps&255)==0){double t=elapsed();if(t>=o.seconds)break;if(t>=next){checkpoint();next=t+o.checkpoint_seconds;}}
        ++steps;bool explicit_long=o.profile=="longmixed"&&randn(2)==0;int ci;
        if(explicit_long){++explicit_long_draws;ci=long_catalog[randn(long_catalog.size())];}
        else{if(o.profile=="longmixed")++wide_mixture_draws;
            int roll=randn(100),kind=o.profile=="short"?(roll<80?0:roll<95?1:2):(o.profile=="wide"||o.profile=="longmixed")?(roll<20?0:roll<50?1:2):(roll<50?0:roll<85?1:2);
            ci=kinds[kind].empty()?randn(circuits.size()):kinds[kind][randn(kinds[kind].size())];}
        const auto&c=circuits[ci];++attempts[c.kind];if(c.groups.size()>8){++long_attempts;if(o.profile=="longmixed"&&!explicit_long)++wide_mixture_long_attempts;}
        bool plus=steps%o.plus_every==0;uint32_t d=0;
        if(plus&&randn(10)==0){do{d=uint32_t(rng()&(bound-1));}while(!d);}
        else if((plus||randn(10)==0)&&!active.empty())d=current[active[randn(active.size())]];
        else{int frequency=0;for(int g:c.groups)if(current[g]){int f=0;for(int h:c.groups)f+=current[h]==current[g];if(f>frequency||(f==frequency&&(rng()&1))){frequency=f;d=current[g];}}}
        int delta=0;if(d)for(int g:c.groups)delta+=(current[g]==0)-(current[g]==d);
        bool ok=d&&(delta<=0||plus)&&int(active.size())+delta<=best_rank+o.headroom;
        if(ok){int before=active.size();for(int g:c.groups){uint32_t old=current[g],value=old^d;if(old)hash^=mix((U(g)<<32)|old);if(value)hash^=mix((U(g)<<32)|value);
                if(!old&&value){position[g]=active.size();active.push_back(g);}else if(old&&!value){int at=position[g],last=active.back();active[at]=last;position[last]=at;active.pop_back();position[g]=-1;}current[g]=value;}
            if(int(active.size())!=before+delta)throw std::runtime_error("incremental active delta mismatch");
            ++accepted;if(explicit_long)++explicit_long_accepted;if(c.groups.size()>8){++long_accepted;if(o.profile=="longmixed"&&!explicit_long)++wide_mixture_long_accepted;}if(delta>0)++uphill;
            if(int(active.size())<best_rank){best=current;best_rank=active.size();check(best);archive={best};archive_hash={hash};dirty={true};seen.clear();seen.insert(hash);history.emplace_back(steps,best_rank);checkpoint();}
            else if(int(active.size())==best_rank&&steps%o.archive_every==0&&!seen.count(hash)){
                size_t at=archive.size()<size_t(o.archive_size)?archive.size():randn(archive.size());
                if(at==archive.size()){archive.push_back(current);archive_hash.push_back(hash);dirty.push_back(true);}else{seen.erase(archive_hash[at]);archive[at]=current;archive_hash[at]=hash;dirty[at]=true;}seen.insert(hash);++archive_additions;
            }
        }else ++rejected;
        if(steps%o.restart_every==0){current=archive[randn(archive.size())];rebuild();hash=fingerprint(current);++restarts;}
    }
    checkpoint();std::cout<<"steps="<<steps<<" best_rank="<<best_rank<<" current_rank="<<active.size()<<" seconds="<<elapsed()<<'\n';return 0;
}catch(const std::exception&error){std::cerr<<"free_factor_kernel_worker_longmixed: "<<error.what()<<'\n';return 1;}
