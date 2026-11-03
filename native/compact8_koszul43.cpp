// Bounded batch preprocessing only: exact F2 factor coordinates and p=1 Koszul.
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

static int rank64(const std::vector<uint64_t>& rows) {
  std::array<uint64_t,64> basis{}; int rank=0;
  for (uint64_t value:rows) while(value) {
    int p=63-__builtin_clzll(value);
    if (basis[p]) value^=basis[p]; else {basis[p]=value;++rank;break;}
  }
  return rank;
}
struct Basis {
  std::vector<uint32_t> vectors; std::array<int,25> at;
  Basis(){at.fill(-1);}
  void add(uint32_t value){
    for(int p=24;p>=0;--p)if((value>>p)&1U)if(at[p]>=0)value^=vectors[at[p]];
    if(value){int p=31-__builtin_clz(value);at[p]=vectors.size();vectors.push_back(value);}
  }
  unsigned coordinates(uint32_t value) const {
    unsigned result=0;
    for(int p=24;p>=0;--p)if((value>>p)&1U)if(at[p]>=0){value^=vectors[at[p]];result^=1U<<at[p];}
    if(value)throw std::runtime_error("factor outside exact span");return result;
  }
};
static std::array<int,7> bounds(const std::vector<unsigned char>& core,std::array<int,3> d){
  auto get=[&](int i,int j,int k){return core[(i*d[1]+j)*d[2]+k];};
  std::array<int,7> result{};
  for(int mode=0;mode<3;++mode){
    std::vector<int> other;for(int a=0;a<3;++a)if(a!=mode)other.push_back(a);
    int a=d[mode],b=d[other[0]],c=d[other[1]];
    if(a*b>64||b*c>64)throw std::runtime_error("dimension exceeds64bit kernel");
    std::vector<std::vector<uint64_t>> fibers(a,std::vector<uint64_t>(c));
    std::vector<uint64_t> unfolding(a);
    for(int i=0;i<a;++i)for(int j=0;j<b;++j)for(int k=0;k<c;++k){
      std::array<int,3> pos{};pos[mode]=i;pos[other[0]]=j;pos[other[1]]=k;
      if(get(pos[0],pos[1],pos[2])){fibers[i][k]^=uint64_t(1)<<j;unfolding[i]^=uint64_t(1)<<(j*c+k);}
    }
    result[mode]=rank64(unfolding);result[6]=std::max(result[6],result[mode]);
    std::vector<uint64_t> rows;
    for(int i=0;i<a;++i)for(int j=i+1;j<a;++j)for(int k=0;k<c;++k)
      rows.push_back((fibers[j][k]<<(i*b))^(fibers[i][k]<<(j*b)));
    int r=rank64(rows);result[3+mode]=r;
    if(a>1)result[6]=std::max(result[6],(r+a-2)/(a-1));
  }
  return result;
}
int main(){
  try{
    int count;if(!(std::cin>>count)||count!=4)return 2;
    std::array<std::array<std::array<uint32_t,3>,93>,4> sources{};
    for(auto&source:sources)for(auto&term:source)for(auto&v:term){std::cin>>v;if(v>>25)throw std::runtime_error("mask outside25bits");}
    int queries;std::cin>>queries;
    std::unordered_map<std::string,std::array<int,7>> cache;
    for(int query=0;query<queries;++query){
      int source;uint64_t ordinal,lo,hi;std::cin>>source>>ordinal>>lo>>hi;
      if(source<0||source>=4||hi>>29)throw std::runtime_error("bad source/index mask");
      std::vector<int> ids;for(uint64_t v=lo;v;v&=v-1)ids.push_back(__builtin_ctzll(v));
      for(uint64_t v=hi;v;v&=v-1)ids.push_back(64+__builtin_ctzll(v));
      if(ids.size()!=8)throw std::runtime_error("eight indices required");
      std::array<Basis,3> bases;
      for(int id:ids)for(int a=0;a<3;++a)bases[a].add(sources[source][id][a]);
      std::array<int,3>d{};for(int a=0;a<3;++a)d[a]=bases[a].vectors.size();
      std::vector<unsigned char> core(d[0]*d[1]*d[2]);
      for(int id:ids){
        std::array<unsigned,3> c{};for(int a=0;a<3;++a)c[a]=bases[a].coordinates(sources[source][id][a]);
        for(unsigned a=c[0];a;a&=a-1)for(unsigned b=c[1];b;b&=b-1)for(unsigned w=c[2];w;w&=w-1)
          core[(__builtin_ctz(a)*d[1]+__builtin_ctz(b))*d[2]+__builtin_ctz(w)]^=1;
      }
      std::string key;for(int a:d)key.push_back(char(a));key.append(core.begin(),core.end());
      auto it=cache.find(key);bool cached=it!=cache.end();std::array<int,7> result;
      if(cached)result=it->second;else{result=bounds(core,d);cache.emplace(key,result);}
      std::string hex;const char*digits="0123456789abcdef";
      for(int n=(core.size()+3)/4-1;n>=0;--n){int v=0;for(int b=0;b<4;++b)if(n*4+b<int(core.size())&&core[n*4+b])v|=1<<b;hex.push_back(digits[v]);}
      if(hex.empty())hex="0";
      std::cout<<source<<' '<<ordinal<<' '<<lo<<' '<<hi;
      for(int v:d)std::cout<<' '<<v;for(int v:result)std::cout<<' '<<v;
      std::cout<<' '<<hex<<' '<<int(cached)<<'\n';
    }
  }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 3;}
}
