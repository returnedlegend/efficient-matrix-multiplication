// Separate necessary-bound pass. Reuse only exact source-coordinate primitives.
#define main local10_bounds_reference_main
#include "local10_bounds43.cpp"
#undef main
struct SpanResult{
 std::array<int,3>span{{-1,-1,-1}},tested{},points{};
 std::array<std::array<unsigned,8>,3>witness{};bool excluded=false;
};
static bool rank_le2(uint64_t matrix,int rows,int columns){
 unsigned first=0,second=0,mask=(1U<<columns)-1;
 for(int i=0;i<rows;++i){unsigned row=unsigned(matrix>>(i*columns))&mask;
  if(!row||row==first||row==second||row==(first^second))continue;
  if(!first)first=row;else if(!second)second=row;else return false;
 }
 return true;
}
static SpanResult span_bound(const std::array<std::array<unsigned,3>,10>&coords,const std::array<int,3>&d){
 SpanResult result;
 for(int mode=0;mode<3;++mode){
  if(d[mode]!=8)continue;std::array<int,2>other{};int n=0;for(int a=0;a<3;++a)if(a!=mode)other[n++]=a;
  int b=d[other[0]],c=d[other[1]];std::vector<uint64_t>slices(8);
  for(auto term:coords){uint64_t pair=0;for(unsigned x=term[other[0]];x;x&=x-1)pair^=uint64_t(term[other[1]])<<(__builtin_ctz(x)*c);
   for(unsigned x=term[mode];x;x&=x-1)slices[__builtin_ctz(x)]^=pair;}
  if(rank64(slices,b*c,64)!=8)throw std::runtime_error("modeimage rank not8");
  std::array<unsigned,8>basis{};int rank=0;unsigned previous=0;uint64_t matrix=0;
  for(unsigned k=1;k<256;++k){unsigned gray=k^(k>>1),changed=gray^previous;matrix^=slices[__builtin_ctz(changed)];previous=gray;++result.tested[mode];
   if(!rank_le2(matrix,b,c))continue;++result.points[mode];unsigned x=gray;
   while(x){int p=31-__builtin_clz(x);if(basis[p])x^=basis[p];else{basis[p]=x;result.witness[mode][rank]=gray;++rank;break;}}
   if(rank==8)break; // Eight explicit lowrank witnesses suffice for a pass.
  }
  result.span[mode]=rank;
  if(rank<8){if(result.tested[mode]!=255)throw std::runtime_error("incomplete negative enumeration");result.excluded=true;break;}
 }
 return result;
}
int main(int argc,char**argv){
 try{
  if(argc!=5)throw std::runtime_error("usage sources necessarybounds prefix CPU-seconds");std::ifstream input(argv[1]);std::string magic;int ns;input>>magic>>ns;if(magic!="LOCAL10SCAN43"||ns!=4)throw std::runtime_error("bad input");std::array<Source,4>sources{};
  for(auto&s:sources)for(auto&t:s)for(auto&x:t){input>>x;if(!x||x>>25)throw std::runtime_error("bad sourcefactor");}if(!input)throw std::runtime_error("truncated input");
  std::string prefix=argv[3];uint64_t next=0;std::array<uint64_t,4>checked{},excluded{},passed{};std::ifstream old(prefix+".cursor");if(old){old>>next;for(auto*array:{&checked,&excluded,&passed})for(auto&x:*array)old>>x;}
  std::ifstream candidates(argv[2]);std::ofstream output(prefix+".tsv",std::ios::app);clock_t started=clock();double seconds=std::stod(argv[4]);uint64_t ordinal=0,hits=0;int source;uint64_t lo;uint32_t hi;std::array<int,3>d{},p1{},p2{};int l1,l2,pass1,pass2;std::unordered_map<std::string,SpanResult>cache;
  while(candidates>>source>>lo>>hi>>d[0]>>d[1]>>d[2]>>p1[0]>>p1[1]>>p1[2]>>l1>>pass1>>p2[0]>>p2[1]>>p2[2]>>l2>>pass2){
   if(ordinal++<next)continue;if(double(clock()-started)/CLOCKS_PER_SEC>=seconds){--ordinal;break;}if(!pass2){next=ordinal;continue;}
   if(source<0||source>=4||hi>>29||*std::max_element(d.begin(),d.end())!=8)throw std::runtime_error("bad candidate");
   std::vector<int>ids;for(uint64_t z=lo;z;z&=z-1)ids.push_back(__builtin_ctzll(z));for(uint32_t z=hi;z;z&=z-1)ids.push_back(64+__builtin_ctz(z));if(ids.size()!=10)throw std::runtime_error("notten");
   std::array<Basis,3>basis;for(int id:ids)for(int a=0;a<3;++a)basis[a].add(sources[source][id][a]);for(int a=0;a<3;++a)if(int(basis[a].v.size())!=d[a]||d[a]>8)throw std::runtime_error("shape mismatch");
   std::array<std::array<unsigned,3>,10>coords{};std::array<uint64_t,8>core{};
   for(int j=0;j<10;++j){for(int a=0;a<3;++a)coords[j][a]=basis[a].coords(sources[source][ids[j]][a]);for(unsigned a=coords[j][0];a;a&=a-1)for(unsigned b=coords[j][1];b;b&=b-1)for(unsigned c=coords[j][2];c;c&=c-1){int p=(__builtin_ctz(a)*d[1]+__builtin_ctz(b))*d[2]+__builtin_ctz(c);core[p/64]^=1ULL<<(p%64);}}
   std::string key;for(int a:d)key.push_back(char(a));key.append(reinterpret_cast<const char*>(core.data()),sizeof(core));auto it=cache.find(key);SpanResult result;
   if(it!=cache.end()){result=it->second;++hits;}else{result=span_bound(coords,d);cache.emplace(key,result);}
   ++checked[source];if(result.excluded)++excluded[source];else ++passed[source];output<<source<<' '<<lo<<' '<<hi<<' '<<result.excluded;
   for(int mode=0;mode<3;++mode){output<<' '<<result.span[mode]<<' '<<result.tested[mode]<<' '<<result.points[mode];for(auto x:result.witness[mode])output<<' '<<x;}output<<'\n';next=ordinal;
  }
  bool complete=candidates.eof();output.close();std::ofstream state(prefix+".cursor.tmp");state<<next;for(auto*array:{&checked,&excluded,&passed})for(auto x:*array)state<<' '<<x;state<<'\n';state.close();std::rename((prefix+".cursor.tmp").c_str(),(prefix+".cursor").c_str());
  std::cout<<"{\"status\":\""<<(complete?"LOWRANK_SPAN_SCAN_COMPLETE":"UNKNOWN_CPU_CURSOR")<<"\",\"next_bound_ordinal\":"<<next<<",\"CPU_seconds\":"<<double(clock()-started)/CLOCKS_PER_SEC<<",\"cache_hits_this_pass\":"<<hits<<",\"counts\":[";
  for(int s=0;s<4;++s){if(s)std::cout<<',';std::cout<<"{\"source\":"<<s<<",\"checked\":"<<checked[s]<<",\"excluded_rank9\":"<<excluded[s]<<",\"bound_passed_not_existence\":"<<passed[s]<<'}';}std::cout<<"]}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
}
