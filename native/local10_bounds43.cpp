// Separate necessary-bound preprocessing, never a rank/existence decoder.
#include <algorithm>
#include <array>
#include <cstdint>
#include <ctime>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
using Term=std::array<uint32_t,3>;using Source=std::array<Term,93>;
struct Basis{
 std::array<int,25>at;std::vector<uint32_t>v;Basis(){at.fill(-1);}
 void add(uint32_t x){for(int p=24;p>=0;--p)if((x>>p)&1U&&at[p]>=0)x^=v[at[p]];if(x){at[31-__builtin_clz(x)]=v.size();v.push_back(x);}}
 unsigned coords(uint32_t x)const{unsigned r=0;for(int p=24;p>=0;--p)if((x>>p)&1U&&at[p]>=0){x^=v[at[p]];r^=1U<<at[p];}if(x)throw std::runtime_error("bad coordinates");return r;}
};
static int rank64(const std::vector<uint64_t>&rows,int columns,int limit){
 std::array<uint64_t,64>basis{};int rank=0;
 for(auto x:rows)while(x){int p=63-__builtin_clzll(x);if(basis[p])x^=basis[p];else{basis[p]=x;++rank;if(rank==columns)return rank;if(rank>limit)return -rank;break;}}
 return rank;
}
using Row=std::array<uint64_t,4>;
static int rank256(const std::vector<Row>&rows,int columns,int limit){
 std::array<Row,224>basis{};std::array<bool,224>used{};int rank=0;
 for(auto x:rows)while(true){int w=3;while(w>=0&&!x[w])--w;if(w<0)break;int p=w*64+63-__builtin_clzll(x[w]);if(p>=columns)throw std::runtime_error("row outsidecolumns");if(used[p]){for(int k=0;k<=w;++k)x[k]^=basis[p][k];}else{basis[p]=x;used[p]=true;++rank;if(rank==columns)return rank;if(rank>limit)return -rank;break;}}
 return rank;
}
static void block(Row&r,unsigned value,int offset){int w=offset/64,b=offset%64;r[w]^=uint64_t(value)<<b;if(b&&w+1<4)r[w+1]^=uint64_t(value)>>(64-b);}
struct Result{std::array<int,3>p1{{-999,-999,-999}},p2{{-999,-999,-999}};int lb1=0,lb2=0;bool pass1=true,pass2=true;};
static Result bounds(const std::array<std::array<unsigned,3>,10>&coords,const std::array<int,3>&d){
 Result result;std::array<std::array<std::array<unsigned,8>,8>,3>fibers{};
 for(int mode=0;mode<3;++mode){std::array<int,2>other{};int n=0;for(int a=0;a<3;++a)if(a!=mode)other[n++]=a;
  for(auto&term:coords)for(unsigned a=term[mode];a;a&=a-1)for(unsigned c=term[other[1]];c;c&=c-1)fibers[mode][__builtin_ctz(a)][__builtin_ctz(c)]^=term[other[0]];
  int a=d[mode],b=d[other[0]],c=d[other[1]];std::vector<uint64_t>rows;
  for(int i=0;i<a;++i)for(int j=i+1;j<a;++j)for(int k=0;k<c;++k)rows.push_back((uint64_t(fibers[mode][j][k])<<(i*b))^(uint64_t(fibers[mode][i][k])<<(j*b)));
  int r=rank64(rows,a*b,9*(a-1));result.p1[mode]=r;int lb=(std::abs(r)+a-2)/(a-1);result.lb1=std::max(result.lb1,lb);
  if(lb>9){result.pass1=false;result.pass2=false;return result;}
 }
 for(int mode=0;mode<3;++mode){std::array<int,2>other{};int n=0;for(int a=0;a<3;++a)if(a!=mode)other[n++]=a;int a=d[mode],b=d[other[0]],c=d[other[1]];
  if(a<3)continue;int pair[8][8]{};int at=0;for(int i=0;i<a;++i)for(int j=i+1;j<a;++j)pair[i][j]=at++;
  std::vector<Row>rows;for(int i=0;i<a;++i)for(int j=i+1;j<a;++j)for(int k=j+1;k<a;++k)for(int w=0;w<c;++w){Row row{};block(row,fibers[mode][i][w],pair[j][k]*b);block(row,fibers[mode][j][w],pair[i][k]*b);block(row,fibers[mode][k][w],pair[i][j]*b);rows.push_back(row);}
  int contribution=(a-1)*(a-2)/2;int r=rank256(rows,at*b,9*contribution);result.p2[mode]=r;int lb=(std::abs(r)+contribution-1)/contribution;result.lb2=std::max(result.lb2,lb);
  if(lb>9){result.pass2=false;return result;}
 }
 return result;
}
int main(int argc,char**argv){
 try{
  if(argc!=5)throw std::runtime_error("usage input candidates prefix CPU-seconds");std::ifstream input(argv[1]);std::string magic;int ns;input>>magic>>ns;if(magic!="LOCAL10SCAN43"||ns!=4)throw std::runtime_error("bad sourceinput");std::array<Source,4>sources{};
  for(auto&s:sources)for(auto&t:s)for(auto&x:t){input>>x;if(!x||x>>25)throw std::runtime_error("bad sourcefactor");}if(!input)throw std::runtime_error("truncatedsources");
  std::string prefix=argv[3];uint64_t next=0;std::array<uint64_t,4>examined{},p1pass{},p2pass{},skipped{};std::ifstream cursor(prefix+".cursor");if(cursor){cursor>>next;for(auto*array:{&examined,&p1pass,&p2pass,&skipped})for(auto&v:*array)cursor>>v;}
  std::ifstream candidates(argv[2]);std::ofstream output(prefix+".tsv",std::ios::app);int s,sample,x,y;uint64_t lo;uint32_t hi;std::array<int,3>d{};uint64_t ordinal=0;clock_t started=clock();double seconds=std::stod(argv[4]);std::unordered_map<std::string,Result>cache;uint64_t hits=0;
  while(candidates>>s>>lo>>hi>>sample>>x>>y>>d[0]>>d[1]>>d[2]){
   if(ordinal++<next)continue;if(double(clock()-started)/CLOCKS_PER_SEC>=seconds){--ordinal;break;}
   if(s<0||s>=4||hi>>29)throw std::runtime_error("bad candidate");if(*std::max_element(d.begin(),d.end())!=8){++skipped[s];next=ordinal;continue;}
   std::vector<int>ids;for(uint64_t z=lo;z;z&=z-1)ids.push_back(__builtin_ctzll(z));for(uint32_t z=hi;z;z&=z-1)ids.push_back(64+__builtin_ctz(z));if(ids.size()!=10)throw std::runtime_error("notten");
   std::array<Basis,3>basis;for(int id:ids)for(int a=0;a<3;++a)basis[a].add(sources[s][id][a]);for(int a=0;a<3;++a)if(int(basis[a].v.size())!=d[a]||d[a]>8||d[a]<2)throw std::runtime_error("candidate shape mismatch");
   std::array<std::array<unsigned,3>,10>coords{};std::array<uint64_t,8>core{};
   for(int j=0;j<10;++j){for(int a=0;a<3;++a)coords[j][a]=basis[a].coords(sources[s][ids[j]][a]);for(unsigned a=coords[j][0];a;a&=a-1)for(unsigned b=coords[j][1];b;b&=b-1)for(unsigned c=coords[j][2];c;c&=c-1){int p=(__builtin_ctz(a)*d[1]+__builtin_ctz(b))*d[2]+__builtin_ctz(c);core[p/64]^=1ULL<<(p%64);}}
   std::string key;for(int a:d)key.push_back(char(a));key.append(reinterpret_cast<const char*>(core.data()),sizeof(core));Result result;auto it=cache.find(key);if(it!=cache.end()){result=it->second;++hits;}else{result=bounds(coords,d);cache.emplace(key,result);}
   ++examined[s];if(result.pass1)++p1pass[s];if(result.pass2)++p2pass[s];output<<s<<' '<<lo<<' '<<hi;for(int a:d)output<<' '<<a;for(int r:result.p1)output<<' '<<r;output<<' '<<result.lb1<<' '<<result.pass1;for(int r:result.p2)output<<' '<<r;output<<' '<<result.lb2<<' '<<result.pass2<<'\n';next=ordinal;
  }
  bool complete=candidates.eof();output.flush();output.close();std::ofstream state(prefix+".cursor.tmp");state<<next;for(auto*array:{&examined,&p1pass,&p2pass,&skipped})for(auto n:*array)state<<' '<<n;state<<'\n';state.close();std::rename((prefix+".cursor.tmp").c_str(),(prefix+".cursor").c_str());
  std::cout<<"{\"status\":\""<<(complete?"NECESSARY_BOUND_SCAN_COMPLETE":"UNKNOWN_CPU_CURSOR")<<"\",\"next_cheap_ordinal\":"<<next<<",\"CPU_seconds\":"<<double(clock()-started)/CLOCKS_PER_SEC<<",\"cache_hits_this_pass\":"<<hits<<",\"counts\":[";
  for(int s=0;s<4;++s){if(s)std::cout<<',';std::cout<<"{\"source\":"<<s<<",\"max8_examined\":"<<examined[s]<<",\"p1_passed\":"<<p1pass[s]<<",\"p2_passed\":"<<p2pass[s]<<",\"maxmode_below8_skipped\":"<<skipped[s]<<'}';}std::cout<<"]}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
}
