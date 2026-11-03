// Instrumented optional reduction dwell; default0 preserves V2 move/RNG order.
// Exact F2 tensor flip walk. Original implementation of the identities in
// mmsearch/search.py; no third-party solver source is incorporated.
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
#include <unordered_map>
#include <unordered_set>
#include <vector>

using U = uint64_t;
using Term = std::array<uint32_t,3>;
using Terms = std::vector<Term>;
static Term rotate(const Term&t) { return {t[1],t[2],t[0]}; }
static Term canonical(const Term&t) { return std::min(t,std::min(rotate(t),rotate(rotate(t)))); }
static Terms cyclic_expansion(const Terms&raw) {
    Terms out;
    for(auto&t:raw) {
        out.push_back(t);
        auto r=rotate(t);
        if(r!=t){out.push_back(r);out.push_back(rotate(r));}
    }
    return out;
}
static volatile std::sig_atomic_t stopped = 0;
static void stop_handler(int) { stopped = 1; }
static U mix(U x) { x += 0x9e3779b97f4a7c15ULL; x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL; x=(x^(x>>27))*0x94d049bb133111ebULL; return x^(x>>31); }
struct THash { size_t operator()(const Term& t) const { return mix(t[0]) ^ mix(U(t[1])+0x100000000ULL) ^ mix(U(t[2])+0x200000000ULL); } };
struct Fingerprint { U x=0,y=0; bool operator==(const Fingerprint& o)const{return x==o.x&&y==o.y;} };
struct FHash { size_t operator()(const Fingerprint& f)const{return mix(f.x)^f.y;} };
static Fingerprint tfinger(const Term& t) { U h=THash{}(t); return {h,mix(h)}; }

// Every live term belongs to three single-factor and three two-factor buckets.
// Membership positions make deletion and eligibility maintenance constant-time.
struct Bucket { std::vector<int> ids; int eligible=-1; };
struct Index {
    std::unordered_map<U,Bucket> map;
    std::vector<U> eligible;
    Index() { map.reserve(1024); eligible.reserve(512); }
    int add(U key,int id) {
        auto& b=map[key]; int pos=b.ids.size(); b.ids.push_back(id);
        if(b.ids.size()==2) {b.eligible=eligible.size();eligible.push_back(key);} return pos;
    }
    // Returns the id moved into the erased position, or -1.
    int erase(U key,int pos) {
        auto it=map.find(key); auto& b=it->second;
        int moved=b.ids.back(); b.ids[pos]=moved; b.ids.pop_back();
        if(b.ids.size()==1) {
            int p=b.eligible; U last=eligible.back(); eligible[p]=last;
            map.find(last)->second.eligible=p; eligible.pop_back();b.eligible=-1;
        }
        if(b.ids.empty()) map.erase(it);
        return moved;
    }
};
struct Slot { Term term{}; std::array<int,3> sp{},pp{}; int active_pos=0; };
struct State {
    std::vector<Slot> slots; std::vector<int> active,free;
    std::unordered_map<Term,int,THash> lookup;
    Index singles,pairs; Fingerprint fingerprint;
    explicit State(int cap=2048):slots(cap) {lookup.reserve(1024);for(int i=cap-1;i>=0;--i)free.push_back(i);}
    static U skey(const Term&t,int axis){return (U(t[axis])<<2)|axis;}
    static U pkey(const Term&t,int axis){int p=(axis+1)%3,q=(axis+2)%3;return (U(t[p])<<27)|(U(t[q])<<2)|axis;}
    void add(const Term&t) {
        if(free.empty())throw std::runtime_error("slot capacity exceeded");
        int id=free.back();free.pop_back();auto&s=slots[id];s.term=t;s.active_pos=active.size();active.push_back(id);lookup.emplace(t,id);
        for(int a=0;a<3;++a){s.sp[a]=singles.add(skey(t,a),id);s.pp[a]=pairs.add(pkey(t,a),id);}
        auto h=tfinger(t);fingerprint.x^=h.x;fingerprint.y+=h.y;
    }
    void erase(int id) {
        auto&s=slots[id];auto t=s.term;
        for(int a=0;a<3;++a){int m=singles.erase(skey(t,a),s.sp[a]);slots[m].sp[a]=s.sp[a];m=pairs.erase(pkey(t,a),s.pp[a]);slots[m].pp[a]=s.pp[a];}
        int m=active.back();active[s.active_pos]=m;slots[m].active_pos=s.active_pos;active.pop_back();lookup.erase(t);free.push_back(id);
        auto h=tfinger(t);fingerprint.x^=h.x;fingerprint.y-=h.y;
    }
    Terms snapshot()const{Terms t;for(int i:active)t.push_back(slots[i].term);std::sort(t.begin(),t.end());return t;}
    void load(const Terms&t){while(!active.empty())erase(active.back());for(auto&x:t)add(x);}
    bool apply(const Terms&raw,int max_rank) {
        Terms delta;
        for(auto&t:raw){if(!t[0]||!t[1]||!t[2])continue;auto it=std::find(delta.begin(),delta.end(),t);if(it==delta.end())delta.push_back(t);else delta.erase(it);}
        int rank=active.size();for(auto&t:delta)rank+=lookup.count(t)?-1:1;
        if(rank>max_rank||delta.empty())return false;
        Terms additions;for(auto&t:delta){auto it=lookup.find(t);if(it==lookup.end())additions.push_back(t);else erase(it->second);}
        for(auto&t:additions)add(t);
        return true;
    }
};

static std::vector<uint8_t> tensor(const Terms& terms,int n) {
    int w=n*n;std::vector<uint8_t> out(w*w*w);
    for(auto&t:terms)for(uint32_t a=t[0];a;a&=a-1)for(uint32_t b=t[1];b;b&=b-1)for(uint32_t c=t[2];c;c&=c-1)
        out[(__builtin_ctz(a)*w+__builtin_ctz(b))*w+__builtin_ctz(c)]^=1;
    return out;
}
static bool exact(const Terms& terms,int n) {
    auto out=tensor(terms,n);int w=n*n;
    for(int i=0;i<n;++i)for(int j=0;j<n;++j)for(int k=0;k<n;++k)out[((i*n+j)*w+j*n+k)*w+k*n+i]^=1;
    return std::none_of(out.begin(),out.end(),[](uint8_t x){return x;});
}
static void atomic_text(const std::string& path,const std::string& content) {
    std::filesystem::path p(path);if(p.has_parent_path())std::filesystem::create_directories(p.parent_path());
    std::ofstream f(path+".tmp");if(!f)throw std::runtime_error("cannot write "+path);f<<content;f.close();if(!f)throw std::runtime_error("write failed "+path);std::filesystem::rename(path+".tmp",path);
}
static void write_terms(const std::string&path,const Terms&t){std::ostringstream s;for(auto&x:t)s<<x[0]<<' '<<x[1]<<' '<<x[2]<<'\n';atomic_text(path,s.str());}
static void write_histogram(std::ostream& out,const std::vector<U>& counts){out<<'{';bool comma=false;for(size_t i=0;i<counts.size();++i)if(counts[i]){if(comma)out<<',';out<<'"'<<i<<"\":"<<counts[i];comma=true;}out<<'}';}
static std::string json_string(const std::string&s){std::string o="\"";for(unsigned char c:s){if(c=='\\'||c=='\"')o+='\\';if(c<32){std::ostringstream h;h<<"\\u00"<<"0123456789abcdef"[c>>4]<<"0123456789abcdef"[c&15];o+=h.str();continue;}o+=c;}return o+'\"';}

struct Options {
    std::string input,output,trace;int n=5,target=92,max_rank=99,archive_size=256;
    U reduction_dwell=0;
    U seed=0,steps=1000000000000ULL,plus_every=250,restart_every=50000,archive_every=100;
    double seconds=60,checkpoint_seconds=30;bool allow_arbitrary=false,cyclic=false;
};
static Options options(int argc,char**argv){Options o;for(int i=1;i<argc;++i){std::string k=argv[i];if(k=="--allow-arbitrary"){o.allow_arbitrary=true;continue;}if(k=="--cyclic"){o.cyclic=true;continue;}if(i+1==argc)throw std::runtime_error("missing value for "+k);std::string v=argv[++i];
    if(k=="--input")o.input=v;else if(k=="--output")o.output=v;else if(k=="--trace")o.trace=v;
    else if(k=="--reduction-dwell"){if(v.empty()||v.find_first_not_of("0123456789")!=std::string::npos)throw std::runtime_error("reduction dwell must be a nonnegative integer");o.reduction_dwell=std::stoull(v);}
    else if(k=="--n")o.n=std::stoi(v);else if(k=="--target")o.target=std::stoi(v);else if(k=="--max-rank")o.max_rank=std::stoi(v);else if(k=="--seed")o.seed=std::stoull(v);else if(k=="--steps")o.steps=std::stoull(v);else if(k=="--seconds")o.seconds=std::stod(v);else if(k=="--checkpoint-seconds")o.checkpoint_seconds=std::stod(v);else if(k=="--archive-size")o.archive_size=std::stoi(v);else if(k=="--archive-every")o.archive_every=std::stoull(v);else if(k=="--plus-every")o.plus_every=std::stoull(v);else if(k=="--restart-every")o.restart_every=std::stoull(v);else throw std::runtime_error("unknown option "+k);
    }if(o.input.empty()||o.output.empty()||o.n<1||o.n>5||o.max_rank<1||o.max_rank>1000||o.archive_size<1||!o.archive_every||!o.plus_every||!o.restart_every||!std::isfinite(o.seconds)||!std::isfinite(o.checkpoint_seconds)||o.seconds<0||o.checkpoint_seconds<=0)throw std::runtime_error("invalid options");return o;}

int main(int argc,char**argv)try {
    Options o=options(argc,argv);std::ifstream input(o.input);if(!input)throw std::runtime_error("cannot read input");
    State state;U a,b,c,limit=U(1)<<(o.n*o.n);while(input>>a){if(!(input>>b>>c))throw std::runtime_error("malformed input triples");if(a>=limit||b>=limit||c>=limit)throw std::runtime_error("factor outside bit width");Term t{uint32_t(a),uint32_t(b),uint32_t(c)};if(!a||!b||!c)continue;auto it=state.lookup.find(t);if(it==state.lookup.end())state.add(t);else state.erase(it->second);}
    if(!input.eof())throw std::runtime_error("malformed input triples");
    Terms best=state.snapshot();if(!o.allow_arbitrary&&!exact(best,o.n))throw std::runtime_error("input is not an exact matrix multiplication tensor");if(int(best.size())>o.max_rank)throw std::runtime_error("initial rank exceeds cap");
    if(o.cyclic)for(auto&t:best)if(!state.lookup.count(rotate(t)))throw std::runtime_error("cyclic search requires full cyclic orbits");
    const auto expected=tensor(best,o.n);std::mt19937_64 rng(o.seed);auto randn=[&](size_t n){return size_t(rng()%n);};
    std::vector<Terms> archive{best};std::vector<Fingerprint> af{state.fingerprint};std::unordered_set<Fingerprint,FHash> seen{state.fingerprint};std::vector<bool> dirty{true};
    U step=0,accepted=0,flips=0,pluses=0,reductions=0,restarts=0,archive_additions=1,rejected=0;
    int max_visited_rank=state.active.size(),max_rank_excess=0;
    std::vector<U> rank_residency(o.max_rank+1,0),rank_after_moves(o.max_rank+1,0),rank_excess_residency(o.max_rank+1,0);
    std::array<U,3> accepted_kind{},rank_up{},rank_down{},rank_equal{};
    std::array<long long,3> rank_delta_sum{};
    U dwell_remaining=0,dwell_steps=0,dwell_windows=0,dwell_rearmed=0,dwell_deferred=0,dwell_no_flip_fallbacks=0,dwell_flip_attempts=0,dwell_restart_events=0;
    std::vector<std::pair<U,int>> history{{0,int(best.size())}};
    auto start=std::chrono::steady_clock::now();auto elapsed=[&](){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();};
    auto check=[&](const Terms&t){if(tensor(t,o.n)!=expected)throw std::runtime_error("tensor identity invariant failed");};
    std::ofstream trace;if(!o.trace.empty()){trace.open(o.trace);if(!trace)throw std::runtime_error("cannot open trace");}
    auto checkpoint=[&](){auto current=state.snapshot();check(best);check(current);write_terms(o.output+".best.txt",best);write_terms(o.output+".current.txt",current);
        for(size_t i=0;i<archive.size();++i)if(dirty[i]){check(archive[i]);write_terms(o.output+".archive/"+std::to_string(i)+".txt",archive[i]);dirty[i]=false;}
        std::ostringstream s;s<<"{\n\"engine\":\"native_f2_flips_v1\",\"dimension\":"<<o.n<<",\"seed\":"<<o.seed<<",\"input\":"<<json_string(o.input)<<",\"steps\":"<<step<<",\"step_budget\":"<<o.steps<<",\"elapsed_seconds\":"<<elapsed()<<",\"seconds_budget\":"<<o.seconds<<",\"best_rank\":"<<best.size()<<",\"current_rank\":"<<state.active.size()<<",\"cyclic\":"<<(o.cyclic?"true":"false")<<",\"target_rank\":"<<o.target<<",\"max_rank\":"<<o.max_rank<<",\"target_reached\":"<<(int(best.size())<=o.target?"true":"false")<<",\"exact\":"<<(!o.allow_arbitrary?"true":"false")<<",\"tensor_invariant_checked\":true,\"accepted_moves\":"<<accepted<<",\"flip_attempts\":"<<flips<<",\"plus_attempts\":"<<pluses<<",\"reduction_attempts\":"<<reductions<<",\"rejected_moves\":"<<rejected<<",\"restarts\":"<<restarts<<",\"archive_size\":"<<archive.size()<<",\"archive_additions\":"<<archive_additions<<",\"plus_every\":"<<o.plus_every<<",\"restart_every\":"<<o.restart_every<<",\"archive_every\":"<<o.archive_every<<",\"stopped_by_signal\":"<<(stopped?"true":"false")<<",\"history\":[";
        for(size_t i=0;i<history.size();++i){if(i)s<<',';s<<"{\"step\":"<<history[i].first<<",\"rank\":"<<history[i].second<<'}';}
        s<<"],\"instrumentation\":\"flip-dwell42-v1\",\"max_visited_rank\":"<<max_visited_rank;
        s<<",\"rank_residency_steps\":";write_histogram(s,rank_residency);
        s<<",\"rank_after_move_steps\":";write_histogram(s,rank_after_moves);
        s<<",\"max_rank_excess\":"<<max_rank_excess<<",\"rank_excess_residency_steps\":";write_histogram(s,rank_excess_residency);
        s<<",\"rank_residency_sampling\":\"before each selected step; sum equals steps\"";
        s<<",\"accepted_by_kind\":{\"flip\":"<<accepted_kind[0]<<",\"plus\":"<<accepted_kind[1]<<",\"reduction\":"<<accepted_kind[2]<<'}';
        s<<",\"rank_changes_by_kind\":{";
        const char* labels[]={"flip","plus","reduction"};
        for(int i=0;i<3;++i){if(i)s<<',';s<<json_string(labels[i])<<":{\"up\":"<<rank_up[i]<<",\"equal\":"<<rank_equal[i]<<",\"down\":"<<rank_down[i]<<",\"delta_sum\":"<<rank_delta_sum[i]<<'}';}
        s<<"},\"reduction_dwell\":"<<o.reduction_dwell<<",\"dwell_remaining\":"<<dwell_remaining
         <<",\"dwell_steps\":"<<dwell_steps<<",\"dwell_windows_started\":"<<dwell_windows<<",\"dwell_windows_rearmed\":"<<dwell_rearmed
         <<",\"dwell_reductions_deferred\":"<<dwell_deferred<<",\"dwell_no_flip_fallback_steps\":"<<dwell_no_flip_fallbacks
         <<",\"dwell_flip_attempts\":"<<dwell_flip_attempts<<",\"dwell_restart_events\":"<<dwell_restart_events<<"}\n";
        atomic_text(o.output+".stats.json",s.str());
    };
    std::signal(SIGTERM,stop_handler);std::signal(SIGINT,stop_handler);checkpoint();double next_checkpoint=o.checkpoint_seconds;
    while(step<o.steps&&int(best.size())>o.target&&!stopped) {
        // Budget clock reads amortized; no more than 255 moves between checks.
        if((step&255)==0){double t=elapsed();if(t>=o.seconds)break;if(t>=next_checkpoint){checkpoint();next_checkpoint=t+o.checkpoint_seconds;}}
        ++step;Terms move;char kind;
        const int before_rank=state.active.size();++rank_residency[before_rank];
        ++rank_excess_residency[before_rank-int(best.size())];
        const bool dwelling=dwell_remaining>0;
        const bool flip_available=!state.singles.eligible.empty();
        const bool defer_reduction=dwelling&&flip_available;
        if(dwelling){++dwell_steps;if(!flip_available)++dwell_no_flip_fallbacks;}
        if(defer_reduction&&!state.pairs.eligible.empty())++dwell_deferred;
        if(!state.pairs.eligible.empty()&&!defer_reduction) {
            ++reductions;kind='r';U key=state.pairs.eligible[randn(state.pairs.eligible.size())];const auto&ids=state.pairs.map.at(key).ids;int axis=key&3;Term x=state.slots[ids[0]].term,y=state.slots[ids[1]].term,z=x;z[axis]^=y[axis];move={x,y,z};
        }else if(step%o.plus_every==0||state.singles.eligible.empty()) {
            ++pluses;kind='p';if(state.active.size()<2)break;size_t i=randn(state.active.size()),j=randn(state.active.size()-1);if(j>=i)++j;
            Term x=state.slots[state.active[i]].term,y=state.slots[state.active[j]].term;int p=randn(3),q=(p+1+randn(2))%3,r=3-p-q;Term f=x,g=x,h=y;f[p]^=y[p];g[p]=y[p];g[r]^=y[r];h[q]^=x[q];if(!o.cyclic||canonical(x)!=canonical(y))move={x,y,f,g,h};
        }else {
            ++flips;kind='f';U key=state.singles.eligible[randn(state.singles.eligible.size())];const auto&ids=state.singles.map.at(key).ids;size_t i=randn(ids.size()),j=randn(ids.size()-1);if(j>=i)++j;int axis=key&3,p=(axis+1)%3,q=(axis+2)%3;if(rng()&1)std::swap(p,q);
            Term x=state.slots[ids[i]].term,y=state.slots[ids[j]].term,f=x,g=y;f[p]^=y[p];g[q]^=x[q];if(!o.cyclic||canonical(x)!=canonical(y))move={x,y,f,g};
        }
        if(o.cyclic)move=cyclic_expansion(move);
        bool ok=state.apply(move,o.max_rank);if(ok)++accepted;else ++rejected;
        const int after_rank=state.active.size();max_visited_rank=std::max(max_visited_rank,after_rank);++rank_after_moves[after_rank];
        max_rank_excess=std::max(max_rank_excess,std::max(0,after_rank-int(best.size())));
        const int index=kind=='f'?0:kind=='p'?1:2;
        if(ok){++accepted_kind[index];const int delta=after_rank-before_rank;rank_delta_sum[index]+=delta;
            if(delta>0)++rank_up[index];else if(delta<0)++rank_down[index];else ++rank_equal[index];}
        if(dwelling){if(kind=='f')++dwell_flip_attempts;--dwell_remaining;}
        if(ok&&kind=='p'&&o.reduction_dwell){if(dwell_remaining)++dwell_rearmed;dwell_remaining=o.reduction_dwell;++dwell_windows;}
        if(trace){trace<<step<<' '<<kind<<' '<<ok;for(auto&t:state.snapshot())trace<<' '<<t[0]<<','<<t[1]<<','<<t[2];trace<<'\n';}
        if(ok&&state.active.size()<best.size()) {
            best=state.snapshot();check(best);archive={best};af={state.fingerprint};seen.clear();seen.insert(state.fingerprint);dirty={true};history.emplace_back(step,best.size());
            std::cerr<<"improvement step="<<step<<" rank="<<best.size()<<" seconds="<<elapsed()<<std::endl;checkpoint();
        }else if(ok&&state.active.size()==best.size()&&step%o.archive_every==0&&seen.find(state.fingerprint)==seen.end()) {
            size_t i=archive.size()<size_t(o.archive_size)?archive.size():randn(archive.size());
            if(i==archive.size()){archive.push_back(state.snapshot());af.push_back(state.fingerprint);dirty.push_back(true);}else{seen.erase(af[i]);archive[i]=state.snapshot();af[i]=state.fingerprint;dirty[i]=true;}
            seen.insert(state.fingerprint);++archive_additions;
        }
        if(step%o.restart_every==0){state.load(archive[randn(archive.size())]);++restarts;if(dwell_remaining)++dwell_restart_events;max_visited_rank=std::max(max_visited_rank,int(state.active.size()));}
    }
    checkpoint();std::cout<<"steps="<<step<<" best_rank="<<best.size()<<" current_rank="<<state.active.size()<<" archive="<<archive.size()<<" seconds="<<elapsed()<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"flip_worker: "<<e.what()<<'\n';return 1;}
