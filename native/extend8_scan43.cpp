// Separate bounded preprocessing only: selected-factor spans, no tensor decoder.
#include <array>
#include <algorithm>
#include <cstdint>
#include <ctime>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
struct Basis{
 std::array<uint32_t,25> row{};int rank=0;
 uint32_t reduce(uint32_t x)const{for(int p=24;p>=0;--p)if((x>>p)&1U)x^=row[p];return x;}
 void add(uint32_t x){x=reduce(x);if(x){row[31-__builtin_clz(x)]=x;++rank;}}
};
using Term=std::array<uint32_t,3>;using Source=std::array<Term,93>;
struct Base{int source,sample;std::array<int,6> ids;};
struct Candidate{int sample,x,y;std::array<int,3> shape;};
int main(int argc,char**argv){
 try{
  if(argc!=5)throw std::runtime_error("usage input output-prefix CPU-seconds union-directory");
  std::ifstream in(argv[1]);std::string magic;in>>magic;if(magic!="EXTEND8SCAN43")throw std::runtime_error("bad magic");
  int ns,nb;in>>ns;if(ns!=4)throw std::runtime_error("four sources required");std::array<Source,4> sources{};
  for(auto&s:sources)for(auto&t:s)for(auto&x:t){in>>x;if(!x||x>>25)throw std::runtime_error("nonzero25bit source required");}
  in>>nb;if(nb<1||nb>20000)throw std::runtime_error("bad base count");std::vector<Base>bases(nb);
  for(auto&b:bases){in>>b.source>>b.sample;uint64_t lo=0;uint32_t hi=0;for(auto&i:b.ids){in>>i;if(i<0||i>=93)throw std::runtime_error("bad base index");if(i<64){if(lo>>i&1)throw std::runtime_error("duplicate index");lo|=1ULL<<i;}else{if(hi>>(i-64)&1)throw std::runtime_error("duplicate index");hi|=1U<<(i-64);}}if(b.source<0||b.source>=4)throw std::runtime_error("bad source");}
  if(!in)throw std::runtime_error("truncated input");
  std::set<std::tuple<int,uint32_t,uint64_t>> existing;
  for(int s=0;s<4;++s){std::ifstream prior(std::string(argv[4])+"/unions.source-"+std::to_string(s)+".k8.txt");uint64_t lo;uint32_t hi;
   if(!prior)throw std::runtime_error("missing complete prior8input");while(prior>>lo>>hi){if(hi>>29||__builtin_popcountll(lo)+__builtin_popcount(hi)!=8)throw std::runtime_error("bad prior8mask");if(!existing.emplace(s,hi,lo).second)throw std::runtime_error("duplicate prior8mask");}}
  if(existing.size()!=981476)throw std::runtime_error("prior8scope count mismatch");
  std::map<std::tuple<int,uint32_t,uint64_t>,Candidate> found;std::array<uint64_t,4> checks{},passes{};
  int next=0;std::string prefix=argv[2];double seconds=std::stod(argv[3]);std::ifstream old(prefix+".cursor");
  if(old){old>>next;for(auto&n:checks)old>>n;for(auto&n:passes)old>>n;std::ifstream rows(prefix+".tsv");int s;uint32_t hi;uint64_t lo;Candidate c;while(rows>>s>>lo>>hi>>c.sample>>c.x>>c.y>>c.shape[0]>>c.shape[1]>>c.shape[2])found[{s,hi,lo}]=c;}
  clock_t started=clock();
  for(;next<nb;++next){
   if(double(clock()-started)/CLOCKS_PER_SEC>=seconds)break;
   const auto&b=bases[next];std::array<Basis,3> basis;std::array<bool,93>inside{};uint64_t oldlo=0;uint32_t oldhi=0;
   for(int id:b.ids){inside[id]=true;for(int a=0;a<3;++a)basis[a].add(sources[b.source][id][a]);if(id<64)oldlo|=1ULL<<id;else oldhi|=1U<<(id-64);}
   std::vector<int> outside;std::array<std::array<uint32_t,3>,93> residues{};
   for(int id=0;id<93;++id)if(!inside[id]){outside.push_back(id);for(int a=0;a<3;++a)residues[id][a]=basis[a].reduce(sources[b.source][id][a]);}
   for(int xi=0;xi<int(outside.size());++xi)for(int yi=xi+1;yi<int(outside.size());++yi){
    ++checks[b.source];int x=outside[xi],y=outside[yi];std::array<int,3> shape;bool okay=true;
    for(int a=0;a<3;++a){uint32_t u=residues[x][a],v=residues[y][a];int added=u?((!v||u==v)?1:2):(v?1:0);shape[a]=basis[a].rank+added;if(shape[a]>6){okay=false;break;}}
    if(!okay)continue;++passes[b.source];uint64_t lo=oldlo;uint32_t hi=oldhi;for(int id:{x,y})if(id<64)lo|=1ULL<<id;else hi|=1U<<(id-64);
    auto result=found.emplace(std::make_tuple(b.source,hi,lo),Candidate{b.sample,x,y,shape});
    if(!result.second&&result.first->second.shape!=shape)throw std::runtime_error("dedup rank mismatch");
   }
  }
  std::ofstream rows(prefix+".tsv.tmp");std::array<uint64_t,4>unique{},d8{},d5{},lower{},deferred{},novel{};std::ofstream fresh(prefix+".new.tsv.tmp"),oldscope(prefix+".deferred.tsv.tmp");
  for(const auto&[key,c]:found){auto[s,hi,lo]=key;++unique[s];int largest=*std::max_element(c.shape.begin(),c.shape.end());if(largest==6)++d8[s];else if(largest==5)++d5[s];else ++lower[s];bool overlap=existing.count(key);if(overlap)++deferred[s];else ++novel[s];auto emit=[&](std::ostream&stream){stream<<s<<' '<<lo<<' '<<hi<<' '<<c.sample<<' '<<c.x<<' '<<c.y;for(int d:c.shape)stream<<' '<<d;stream<<'\n';};emit(rows);emit(overlap?oldscope:fresh);}rows.close();fresh.close();oldscope.close();std::rename((prefix+".new.tsv.tmp").c_str(),(prefix+".new.tsv").c_str());std::rename((prefix+".deferred.tsv.tmp").c_str(),(prefix+".deferred.tsv").c_str());std::rename((prefix+".tsv.tmp").c_str(),(prefix+".tsv").c_str());
  std::ofstream state(prefix+".cursor.tmp");state<<next;for(auto n:checks)state<<' '<<n;for(auto n:passes)state<<' '<<n;state<<'\n';state.close();std::rename((prefix+".cursor.tmp").c_str(),(prefix+".cursor").c_str());
  std::cout<<"{\"status\":\""<<(next==nb?"CHEAP_SCAN_COMPLETE":"UNKNOWN_CPU_CURSOR")<<"\",\"next_base\":"<<next<<",\"bases\":"<<nb<<",\"CPU_seconds\":"<<double(clock()-started)/CLOCKS_PER_SEC<<",\"counts\":[";
  for(int s=0;s<4;++s){if(s)std::cout<<',';std::cout<<"{\"source\":"<<s<<",\"extension_checks\":"<<checks[s]<<",\"passing_occurrences\":"<<passes[s]<<",\"unique_subsets\":"<<unique[s]<<",\"max_mode6\":"<<d8[s]<<",\"max_mode5\":"<<d5[s]<<",\"max_mode_le4\":"<<lower[s]<<",\"defer_to_existing_portfolio\":"<<deferred[s]<<",\"new_subsets\":"<<novel[s]<<'}';}std::cout<<"]}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
}
