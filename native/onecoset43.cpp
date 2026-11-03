// Standalone exact F2 local CP feasibility for r <= dim(S)+1; UNLAUNCHED.
// Input: ONECOSET43 1, then a b free target M0 ... M(free-1) per line.
// Mi uses row i / column j at bit i*b+j. Output factors are (left,right,free).
// Stored factor witnesses are original rank-one points, never RREF combinations.
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#include <sys/resource.h>

using U=uint64_t;
static volatile std::sig_atomic_t interrupted=0;
static void on_signal(int){interrupted=1;}
struct Options {
    std::string input,output,enumeration="gray";
    double seconds=60,deadline=std::numeric_limits<double>::infinity();
    U max_points=65025;int memory_mb=512;
    std::vector<std::string> stop_markers;
};
static U unsigned_value(const std::string& s){
    U value=0;auto parsed=std::from_chars(s.data(),s.data()+s.size(),value);
    if(s.empty()||parsed.ec!=std::errc()||parsed.ptr!=s.data()+s.size())throw std::runtime_error("invalid unsigned decimal");
    return value;
}
static double real_value(const std::string& s){
    size_t end=0;double value=std::stod(s,&end);
    if(end!=s.size())throw std::runtime_error("invalid real option");
    return value;
}
static Options options(int argc,char** argv){
    Options o;
    for(int i=1;i<argc;++i){
        std::string key=argv[i];if(++i==argc)throw std::runtime_error("missing option value");std::string v=argv[i];
        if(key=="--input")o.input=v;else if(key=="--output")o.output=v;
        else if(key=="--seconds")o.seconds=real_value(v);else if(key=="--deadline-unix")o.deadline=real_value(v);
        else if(key=="--stop-marker")o.stop_markers.push_back(v);else if(key=="--max-points")o.max_points=unsigned_value(v);
        else if(key=="--enumeration")o.enumeration=v;else if(key=="--memory-mb"){U memory=unsigned_value(v);if(memory>768)throw std::runtime_error("memory option exceeds768MiB");o.memory_mb=memory;}
        else throw std::runtime_error("unknown option");
    }
    if(!std::isfinite(o.seconds)||o.seconds<0||o.seconds>600||std::isnan(o.deadline)||o.memory_mb<64||o.memory_mb>768
       ||(o.enumeration!="gray"&&o.enumeration!="lex"))throw std::runtime_error("unsupported options");
    return o;
}
struct Stop {
    const Options& o;std::chrono::steady_clock::time_point start=std::chrono::steady_clock::now();
    bool operator()()const {
        if(interrupted||std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()>=o.seconds)return true;
        if(std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count()>=o.deadline)return true;
        for(const auto& path:o.stop_markers){std::error_code error;bool exists=std::filesystem::exists(path,error);if(error||exists)return true;}
        return false;
    }
};
struct Image {
    std::array<U,64> pivots{};std::array<uint8_t,64> coordinates{};
    std::vector<U> originals;
    std::pair<U,uint8_t> project(U x)const {
        uint8_t mask=0;
        for(int p=63;p>=0;--p)if((x>>p&1)&&pivots[p]){x^=pivots[p];mask^=coordinates[p];}
        return {x,mask};
    }
    void insert(U x){
        auto reduced=project(x);if(!reduced.first)return;
        if(originals.size()==8)throw std::runtime_error("image rank exceeds8");
        int p=63-__builtin_clzll(reduced.first);pivots[p]=reduced.first;
        coordinates[p]=reduced.second^(1u<<originals.size());originals.push_back(x);
    }
    U expand(unsigned mask)const {U x=0;for(size_t i=0;i<originals.size();++i)if(mask>>i&1)x^=originals[i];return x;}
};
struct CoordinateBasis {
    std::array<uint8_t,8> pivots{};unsigned rank=0;
    bool insert(uint8_t x){
        for(int p=7;p>=0;--p)if(x>>p&1){if(pivots[p])x^=pivots[p];else{pivots[p]=x;++rank;return true;}}
        return false;
    }
};
struct Point {U column=0;uint8_t left=0,right=0,lambda=0;};
static U pair_column(unsigned left,unsigned right,unsigned b){
    U x=0;for(unsigned i=0;left;++i,left>>=1)if(left&1)x^=U(right)<<(i*b);return x;
}
static bool rankone(U value,unsigned a,unsigned b,Point& p){
    if(!value)return false;
    unsigned right=0,left=0,mask=(1u<<b)-1;
    for(unsigned i=0;i<a;++i){unsigned row=value>>(i*b)&mask;if(row){if(right&&row!=right)return false;right=row;left|=1u<<i;}}
    if(!right)return false;
    p.column=value;p.left=left;p.right=right;return true;
}
struct Bucket {
    Point anchor;CoordinateBasis span;std::array<Point,8> chosen{};unsigned chosen_count=0;
};
struct Case {unsigned a=0,b=0,free=0,target=0;std::vector<U> slices;bool supported=false;};
static Case parse_case(const std::string& line){
    Case c;std::istringstream input(line);std::vector<std::string> tokens;std::string token;while(input>>token)tokens.push_back(token);
    if(tokens.size()<4)return c;
    U a=unsigned_value(tokens[0]),b=unsigned_value(tokens[1]),f=unsigned_value(tokens[2]),r=unsigned_value(tokens[3]);
    if(a>8||b>8||f>8||a*b>64||r>9)return c;
    c.a=a;c.b=b;c.free=f;c.target=r;
    if(tokens.size()!=4+f)return c;
    for(unsigned j=0;j<f;++j){U x=unsigned_value(tokens[j+4]);if(a*b<64&&(x>>(a*b)))return c;c.slices.push_back(x);}
    c.supported=true;return c;
}
struct Result {
    std::string status="UNKNOWN",reason="unsupported or malformed input",method="",proof_case="";
    unsigned d=0,h=0;U span_tested=0,pairs_tested=0,inside_points=0,buckets=0,quotient=0;
    bool complete=false,enumeration_complete=false;std::vector<U> space_basis;std::vector<Point> support;std::vector<std::array<unsigned,3>> products;
};
static void emit_witness(Result& r,const Case& c,const std::vector<Point>& support,const Stop& stop){
    if(stop()){r.status="UNKNOWN";r.reason="cutoff before witness decode";return;}
    std::array<U,64> pivots{};std::array<uint16_t,64> masks{};
    if(support.size()>9||support.size()>c.target)throw std::runtime_error("support bound violated");
    for(size_t j=0;j<support.size();++j){
        U x=support[j].column;uint16_t mask=1u<<j;
        if(x!=pair_column(support[j].left,support[j].right,c.b))throw std::runtime_error("original factor witness differs");
        for(int p=63;p>=0;--p)if(x>>p&1){if(pivots[p]){x^=pivots[p];mask^=masks[p];}else{pivots[p]=x;masks[p]=mask;break;}}
        if(!x)throw std::runtime_error("selected support is dependent");
    }
    std::vector<unsigned> free(support.size(),0);
    for(unsigned coordinate=0;coordinate<c.free;++coordinate){
        U x=c.slices[coordinate];uint16_t mask=0;
        for(int p=63;p>=0;--p)if((x>>p&1)&&pivots[p]){x^=pivots[p];mask^=masks[p];}
        if(x)throw std::runtime_error("original slice not represented");
        for(size_t j=0;j<support.size();++j)if(mask>>j&1)free[j]^=1u<<coordinate;
    }
    std::vector<std::array<unsigned,3>> products;
    for(size_t j=0;j<support.size();++j)if(free[j])products.push_back({support[j].left,support[j].right,free[j]});
    for(unsigned coordinate=0;coordinate<c.free;++coordinate){
        U reconstructed=0;for(const auto& p:products)if(p[2]>>coordinate&1)reconstructed^=pair_column(p[0],p[1],c.b);
        if(reconstructed!=c.slices[coordinate])throw std::runtime_error("full original-slice expansion failed");
    }
    if(stop()){r.status="UNKNOWN";r.reason="cutoff after full original-slice verification";return;}
    r.status="SAT";r.reason="";r.complete=true;r.support=support;r.products=products;
}
static Result solve(const Case& c,const Options& o,const Stop& stop){
    Result r;if(!c.supported)return r;
    if(stop()){r.reason="cutoff before case";return r;}
    Image image;for(U x:c.slices)image.insert(x);r.d=image.originals.size();r.space_basis=image.originals;
    if(stop()){r.reason="cutoff after image basis";return r;}
    if(c.target<r.d){r.status="LOCAL_UNSAT";r.reason="";r.proof_case="mode_rank_exceeds_target";r.complete=true;return r;}
    if(c.target>r.d+1){r.reason="target exceeds mode-rank-plus-one scope";return r;}
    if(!r.d){r.proof_case="zero_tensor";emit_witness(r,c,{},stop);return r;}
    r.method="enumerate_image_rankone_then_one_coset";
    U span_count=(1u<<r.d)-1;
    if(span_count>o.max_points){r.reason="image enumeration cap";return r;}
    CoordinateBasis inside;std::vector<Point> chosen_inside;
    for(unsigned mask=1;mask<=span_count;++mask){
        if(stop()){r.reason="cutoff during image enumeration";return r;}
        ++r.span_tested;Point p;
        if(rankone(image.expand(mask),c.a,c.b,p)){++r.inside_points;p.lambda=mask;if(inside.insert(mask))chosen_inside.push_back(p);}
    }
    r.h=inside.rank;
    if(r.h==r.d){r.proof_case="inside_points_span_mode_image";emit_witness(r,c,chosen_inside,stop);return r;}
    if(c.target==r.d){r.status="LOCAL_UNSAT";r.reason="";r.proof_case="inside_points_do_not_span";r.complete=true;r.enumeration_complete=true;return r;}
    U pair_count=((1u<<c.a)-1)*((1u<<c.b)-1);
    if(pair_count>o.max_points){r.reason="pair enumeration cap";return r;}
    std::unordered_map<U,Bucket> buckets;buckets.reserve(pair_count);
    for(unsigned left=1;left<(1u<<c.a);++left){
        std::array<U,8> raw{},q{};std::array<uint8_t,8> lambda{};
        for(unsigned j=0;j<c.b;++j){raw[j]=pair_column(left,1u<<j,c.b);auto v=image.project(raw[j]);q[j]=v.first;lambda[j]=v.second;}
        U matrix=0,residue=0;uint8_t coordinates=0;unsigned previous=0;
        for(unsigned ordinal=1;ordinal<(1u<<c.b);++ordinal){
            // Clock and marker checks are bounded to <=63 pair points apart.
            if((r.pairs_tested&63)==0&&stop()){r.reason="cutoff during pair enumeration";r.buckets=buckets.size();return r;}
            unsigned right=o.enumeration=="gray"?(ordinal^(ordinal>>1)):ordinal;
            if(o.enumeration=="gray"){
                unsigned j=__builtin_ctz(right^previous);matrix^=raw[j];residue^=q[j];coordinates^=lambda[j];previous=right;
            }else{matrix=pair_column(left,right,c.b);auto v=image.project(matrix);residue=v.first;coordinates=v.second;}
            ++r.pairs_tested;if(!residue)continue;
            Point p{matrix,uint8_t(left),uint8_t(right),coordinates};
            auto found=buckets.find(residue);
            if(found==buckets.end()){
                Bucket bucket;bucket.anchor=p;bucket.span=inside;buckets.emplace(residue,bucket);continue;
            }
            auto& bucket=found->second;
            if(bucket.span.insert(coordinates^bucket.anchor.lambda))bucket.chosen[bucket.chosen_count++]=p;
            if(bucket.span.rank==r.d){
                r.quotient=residue;r.buckets=buckets.size();r.proof_case="single_nonzero_coset_star_differences_span";
                std::vector<Point> support=chosen_inside;support.push_back(bucket.anchor);
                for(unsigned j=0;j<bucket.chosen_count;++j)support.push_back(bucket.chosen[j]);
                emit_witness(r,c,support,stop);return r;
            }
        }
    }
    r.buckets=buckets.size();
    if(stop()){r.reason="cutoff after pair enumeration";return r;}
    r.status="LOCAL_UNSAT";r.reason="";r.proof_case="no_single_coset_spans";r.complete=true;r.enumeration_complete=true;return r;
}
static void write_result(std::ostream& out,U index,const Case& c,Result r,const Options& o,const Stop& stop){
    // Last cancellation check before either SAT or a local negative is published.
    if(stop()){r.status="UNKNOWN";r.reason="cutoff before result publication";r.complete=false;r.enumeration_complete=false;r.products.clear();r.support.clear();}
    out<<"{\"format\":\"native-onecoset43-v1\",\"case_index\":"<<index<<",\"status\":\""<<r.status
       <<"\",\"reason\":\""<<r.reason<<"\",\"case\":\""<<r.proof_case<<"\",\"complete\":"<<(r.complete?"true":"false")
       <<",\"left_width\":"<<c.a<<",\"right_width\":"<<c.b<<",\"free_width\":"<<c.free<<",\"target\":"<<c.target
       <<",\"mode_rank\":"<<r.d<<",\"inside_rank\":"<<r.h<<",\"inside_points\":"<<r.inside_points
       <<",\"span_vectors_tested\":"<<r.span_tested<<",\"pair_points_tested\":"<<r.pairs_tested
       <<",\"all_pair_points\":"<<((1u<<c.a)-1)*((1u<<c.b)-1)<<",\"nonzero_cosets_seen\":"<<r.buckets
       <<",\"enumeration\":\""<<o.enumeration<<"\",\"enumeration_complete\":"<<(r.enumeration_complete?"true":"false")
       <<",\"quotient_representative\":"<<r.quotient<<",\"full_original_slices_verified\":"<<(r.status=="SAT"?"true":"false")
       <<",\"core_entries_checked\":"<<(r.status=="SAT"?c.a*c.b*c.free:0)<<",\"space_basis\":[";
    for(size_t j=0;j<r.space_basis.size();++j){if(j)out<<',';out<<r.space_basis[j];}
    out<<"],\"products\":[";
    for(size_t j=0;j<r.products.size();++j){if(j)out<<',';const auto& p=r.products[j];out<<'['<<p[0]<<','<<p[1]<<','<<p[2]<<']';}
    out<<"],\"pair_support\":[";
    for(size_t j=0;j<r.support.size();++j){if(j)out<<',';const auto& p=r.support[j];out<<"{\"column\":"<<p.column<<",\"left\":"<<unsigned(p.left)<<",\"right\":"<<unsigned(p.right)<<",\"lambda\":"<<unsigned(p.lambda)<<'}';}
    out<<"]}\n";out.flush();if(!out)throw std::runtime_error("result write failed");
}
int main(int argc,char** argv)try{
    Options o=options(argc,argv);Stop stop{o};std::signal(SIGTERM,on_signal);std::signal(SIGINT,on_signal);
    rlim_t memory=U(o.memory_mb)*1024*1024;rlimit limit{memory,memory};if(setrlimit(RLIMIT_AS,&limit))throw std::runtime_error("memory limit failed");
    rlimit core{0,0};setrlimit(RLIMIT_CORE,&core);
    std::ifstream file;std::istream* input=&std::cin;if(!o.input.empty()){file.open(o.input);if(!file)throw std::runtime_error("input open failed");input=&file;}
    std::ofstream output;std::ostream* out=&std::cout;if(!o.output.empty()){if(std::filesystem::exists(o.output))throw std::runtime_error("output already exists");output.open(o.output);if(!output)throw std::runtime_error("output open failed");out=&output;}
    std::string line;if(!std::getline(*input,line)||line!="ONECOSET43 1")throw std::runtime_error("expected ONECOSET43 1 header");
    U index=0;while(std::getline(*input,line)){if(line.empty())continue;Case c;Result result;
        try{if(line.size()>4096)throw std::runtime_error("line too long");c=parse_case(line);result=solve(c,o,stop);}
        catch(const std::bad_alloc&){result=Result{};result.reason="memory allocation cutoff";}
        catch(const std::exception&){result=Result{};result.reason="unsupported input or internal witness error";}
        write_result(*out,index++,c,result,o,stop);
    }
    if(!input->eof())throw std::runtime_error("input read failed");
    return 0;
}catch(const std::exception& e){std::cerr<<"onecoset43: "<<e.what()<<'\n';return 1;}
