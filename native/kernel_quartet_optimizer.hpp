#pragma once
#include <algorithm>
#include <array>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <stdexcept>
#include <unordered_map>
#include <vector>
namespace quartet {
using Mask=uint32_t;using U=uint64_t;
struct Bag {
 std::vector<Mask> values;std::unordered_map<Mask,int> frequency;int zeros=0,maximum=0,groups=0;
 void add(Mask value){if(++groups>128)throw std::runtime_error("parity class exceeds128 groups");auto found=frequency.find(value);if(found==frequency.end())values.push_back(value);maximum=std::max(maximum,++frequency[value]);zeros+=value==0;}
 int count(Mask value)const{auto found=frequency.find(value);return found==frequency.end()?0:found->second;}
};
using Bags=std::array<Bag,16>;
struct Basis {std::array<int,4> classes{},transform{};unsigned present=0;int size=0;};
using Bases=std::array<std::vector<Basis>,5>;
inline Bases make_bases(){Bases out;out[0].push_back(Basis{});for(unsigned mask=1;mask<(1U<<15);++mask){if(__builtin_popcount(mask)>4)continue;Basis basis;basis.present=mask;for(int s=1;s<16;++s)if(mask>>(s-1)&1)basis.classes[basis.size++]=s;std::array<int,4> row{},rhs{};for(int i=0;i<basis.size;++i){row[i]=basis.classes[i];rhs[i]=1<<i;}int p=0;for(int bit=0;bit<4;++bit){int k=p;while(k<basis.size&&!(row[k]>>bit&1))++k;if(k==basis.size)continue;std::swap(row[k],row[p]);std::swap(rhs[k],rhs[p]);for(int j=0;j<basis.size;++j)if(j!=p&&(row[j]>>bit&1)){row[j]^=row[p];rhs[j]^=rhs[p];}++p;}if(p!=basis.size)continue;for(int j=0;j<p;++j)basis.transform[__builtin_ctz(unsigned(row[j]))]=rhs[j];out[p].push_back(basis);}return out;}
inline int present_rank(unsigned present){std::array<int,4> pivot{};int rank=0;for(int s=1;s<16;++s)if(present>>(s-1)&1){int row=s;for(int bit=3;bit>=0;--bit)if(row>>bit&1){if(pivot[bit])row^=pivot[bit];else{pivot[bit]=row;++rank;break;}}}return rank;}
struct Opt {std::array<Mask,4> move{};int score=0,zeros=0,upper=0,rank=0,basis_count=0;bool complete=true;U candidates=0,workload=0;};
inline Opt optimize(const Bags&bags,const Bases&all,const std::chrono::steady_clock::time_point&deadline,const volatile std::sig_atomic_t*stopped=nullptr){Opt out;unsigned present=0;for(int s=1;s<16;++s){out.zeros+=bags[s].zeros;out.upper+=bags[s].maximum;if(bags[s].groups)present|=1U<<(s-1);}out.score=out.zeros;out.rank=present_rank(present);
 for(const auto&basis:all[out.rank])if((basis.present&present)==basis.present){++out.basis_count;U count=1;for(int k=0;k<basis.size;++k)count*=bags[basis.classes[k]].values.size();out.workload+=count;}
 if(!out.rank||out.score==out.upper)return out;
 const std::vector<Mask> zero{0};
 for(const auto&basis:all[out.rank]){if((basis.present&present)!=basis.present)continue;const auto&a=bags[basis.classes[0]].values;const auto&b=basis.size>1?bags[basis.classes[1]].values:zero;const auto&c=basis.size>2?bags[basis.classes[2]].values:zero;const auto&d=basis.size>3?bags[basis.classes[3]].values:zero;
 for(Mask w:a)for(Mask x:b)for(Mask y:c)for(Mask z:d){if((out.candidates&1023)==0&&((stopped&&*stopped)||std::chrono::steady_clock::now()>=deadline)){out.complete=false;return out;}std::array<Mask,4> value{w,x,y,z},move{};for(int v=0;v<4;++v)for(int t=0;t<basis.size;++t)if(basis.transform[v]>>t&1)move[v]^=value[t];int score=0;for(int s=1;s<16;++s)if(present>>(s-1)&1){Mask shifted=0;for(int bit=0;bit<4;++bit)if(s>>bit&1)shifted^=move[bit];score+=bags[s].count(shifted);}++out.candidates;if(score>out.score||(score==out.score&&move<out.move)){out.score=score;out.move=move;}if(out.score==out.upper)return out;}}
 return out;
}
inline Opt optimize_components(const Bags&bags,const Bases&all,const std::chrono::steady_clock::time_point&deadline,const volatile std::sig_atomic_t*stopped=nullptr){std::array<int,4> component{1,2,4,8};for(int s=1;s<16;++s)if(bags[s].groups){int merged=0;for(int bit=0;bit<4;++bit)if(s>>bit&1)merged|=component[bit];for(int bit=0;bit<4;++bit)if(component[bit]&merged)component[bit]=merged;}Opt out;unsigned done=0;for(int bit=0;bit<4;++bit){unsigned mask=component[bit];if(done&mask)continue;done|=mask;Bags sub;for(int s=1;s<16;++s)if((unsigned(s)&mask)==unsigned(s))sub[s]=bags[s];auto local=optimize(sub,all,deadline,stopped);out.complete&=local.complete;out.score+=local.score;out.zeros+=local.zeros;out.upper+=local.upper;out.rank+=local.rank;out.basis_count+=local.basis_count;out.candidates+=local.candidates;out.workload+=local.workload;for(int j=0;j<4;++j)out.move[j]^=local.move[j];if(!out.complete)return out;}return out;}
}
