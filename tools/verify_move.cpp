// Exercise the actual common BIOS with an independent two-bank memory model.
// Link only the external MIT Z80 CPU core; no emulator implementation required.
extern "C" {
#include "z80/z80.h"
}
#include <array>
#include <fstream>
#include <iostream>
#include <vector>
#include <stdexcept>
#include <cstdint>
struct Machine {
 std::array<uint8_t,0x20000> bytes{};
 uint8_t slots[8]={0,1,2,3,4,5,6,7},index=0;
 z80 cpu{};uint64_t switches=0;
 size_t address(uint16_t a)const{return slots[a>>13]*8192+(a&8191);}
 static uint8_t rd(void*p,uint16_t a){auto&m=*(Machine*)p;return m.bytes[m.address(a)];}
 static void wr(void*p,uint16_t a,uint8_t v){auto&m=*(Machine*)p;m.bytes[m.address(a)]=v;}
 static void out(z80*z,uint16_t port,uint8_t v){auto&m=*(Machine*)z->userdata;if((port&255)==0xb4)m.index=v&7;else if((port&255)==0xb5){m.slots[m.index]=v;m.index=(m.index+1)&7;m.switches++;}}
 Machine(const std::vector<uint8_t>&bios){for(size_t i=0;i<bytes.size();i++)bytes[i]=(i*37+(i>>8)*11)&255;std::copy(bios.begin(),bios.end(),bytes.begin()+0xe800);z80_init(&cpu);cpu.userdata=this;cpu.read_byte=rd;cpu.write_byte=wr;cpu.port_out=out;}
 void call(uint16_t pc){cpu.pc=pc;cpu.sp=0xe100;wr(this,0xe100,0xf0);wr(this,0xe101,0xe1);uint64_t end=cpu.cyc+20000000;while(cpu.pc!=0xe1f0&&cpu.cyc<end)z80_step(&cpu);if(cpu.pc!=0xe1f0)throw std::runtime_error("BIOS call timeout");}
 size_t physical(int bank,uint16_t a)const{return a>=0xe000?a:a+(bank==0?0x10000:0);}
};
void test(const std::vector<uint8_t>&bios,int source,int dest,uint16_t from,uint16_t to,uint16_t n,int caller,bool explicit_move=true){
 Machine m(bios);m.cpu.a=caller;m.call(0xe851);
 if(explicit_move){m.cpu.c=source;m.cpu.b=dest;m.call(0xe857);}else source=dest=caller;
 auto expected=m.bytes;
 for(unsigned i=0;i<n;i++)expected[m.physical(dest,uint16_t(to+i))]=expected[m.physical(source,uint16_t(from+i))];
 m.cpu.d=from>>8;m.cpu.e=from;m.cpu.h=to>>8;m.cpu.l=to;m.cpu.b=n>>8;m.cpu.c=n;
 m.switches=0;m.call(0xe84b);
 for(unsigned i=0;i<n;i++)if(m.bytes[m.physical(dest,uint16_t(to+i))]!=expected[m.physical(dest,uint16_t(to+i))])throw std::runtime_error("MOVE data mismatch");
 if(((m.cpu.h<<8)|m.cpu.l)!=uint16_t(to+n)||((m.cpu.d<<8)|m.cpu.e)!=uint16_t(from+n)||m.cpu.b||m.cpu.c)throw std::runtime_error("MOVE register contract");
 for(int i=0;i<7;i++)if(m.slots[i]!=i+(caller==0?8:0))throw std::runtime_error("Caller bank not restored");
 // XMOVE applies to one MOVE only, including zero-length transfers.
 m.bytes[m.physical(caller,0x7000)]=0x5a;m.bytes[m.physical(caller,0x7100)]=0;
 m.cpu.d=0x70;m.cpu.e=0;m.cpu.h=0x71;m.cpu.l=0;m.cpu.b=0;m.cpu.c=1;m.call(0xe84b);
 if(m.bytes[m.physical(caller,0x7100)]!=0x5a)throw std::runtime_error("XMOVE leaked");
}
int main(int argc,char**argv){try{if(argc!=2)return 2;std::ifstream f(argv[1],std::ios::binary);std::vector<uint8_t> bios(std::istreambuf_iterator<char>(f),{});if(bios.empty())return 2;int count=0;
 for(int caller=0;caller<2;caller++)for(int src=0;src<2;src++)for(int dst=0;dst<2;dst++){
  for(int n:{0,1,127,128,129,255,256,384,3200}){test(bios,src,dst,0x3003,0x5007,n,caller);count++;}
  for(auto p:std::vector<std::pair<uint16_t,uint16_t>>{{0xdff0,0x6003},{0x6003,0xdff0},{0xdf80,0xdf90},{0xe280,0xe281},{0xe281,0xe280},{0xfff0,0x6000},{0x6000,0xfff0},{0x3000,0x3001},{0x3001,0x3000}}){test(bios,src,dst,p.first,p.second,257,caller);count++;}
 }
 for(int bank=0;bank<2;bank++){test(bios,bank,bank,0x3000,0x5000,1024,bank,false);count++;}
 std::cout<<"MOVE PASS: "<<count<<" cases (banks, common boundary, wrap, overlap, registers, XMOVE lifetime)\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
