// Real Z80 migration test against the project-owned native emulator API.
// Compile with a matching 64-bit host core; no ROMs or EmuZ source are used.
#include "core/mz2500.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <vector>
namespace fs=std::filesystem;
using Bytes=std::vector<uint8_t>;
Bytes read(const fs::path&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("Missing "+p.string());return Bytes(std::istreambuf_iterator<char>(f),{});}
void write(const fs::path&p,const Bytes&b){std::ofstream f(p,std::ios::binary);f.write((const char*)b.data(),b.size());if(!f)throw std::runtime_error("Write failed");}
void require(bool ok,const char*why){if(!ok)throw std::runtime_error(why);}
bool ends(const std::string&s,const std::string&tail){return s.size()>=tail.size()&&s.compare(s.size()-tail.size(),tail.size(),tail)==0;}
struct Runner {
 mz::Mz2500 m;uint64_t frames=0;
 void run(int n){float audio[2048];while(n--){m.run_frame();m.read_audio(audio,2048);frames++;}}
 std::string screen(){char b[8192];m.screen_text(b,sizeof b);std::string s=b;while(!s.empty()&&isspace((unsigned char)s.back()))s.pop_back();return s;}
 void type(const std::string&s){for(char c:s){int row,bit;if(c=='\r'){row=3;bit=2;}else if(c==' '){row=3;bit=1;}else if(c==':'){row=9;bit=2;}else{int n=toupper((unsigned char)c)-64;row=4+(n>>3);bit=n&7;}m.set_key(row,bit,true);run(4);m.set_key(row,bit,false);run(4);}}
 std::string wait(const std::string&a,const std::string&b="",bool allow_error=false){for(int i=0;i<250000;i+=32){run(32);auto s=screen();if(!allow_error&&s.find("ERROR:")!=std::string::npos)throw std::runtime_error(s);if(ends(s,a)||(!b.empty()&&ends(s,b)))return s;if(i%32768==0)std::cout<<"WAIT "<<frames<<" cycles "<<m.cpu().cyc<<" "<<a<<std::endl;}throw std::runtime_error("Timeout\n"+screen());}
 void mount(int n,const Bytes&data){require(m.insert_disk_bytes(n,data),"FD mount failed");}
 void hdd(const Bytes&data){require(m.insert_sasi_image(data.data(),data.size(),256),"HDD mount failed");}
};
int main(int argc,char**argv){try{
 require(argc==4,"usage: measure_performance HDD BOOT_FD DATA_FD");
 auto h=std::make_unique<Runner>();h->hdd(read(argv[1]));require(h->m.boot_from_disk(),"HDD boot failed");
 for(int i=0;;i++){require(i<3000,"HDD boot timeout");h->run(1);if(ends(h->screen(),"C>"))break;}
 std::cout<<"HDD boot seconds: "<<double(h->m.cpu().cyc)/6000000<<std::endl;
 auto r=std::make_unique<Runner>();r->mount(0,read(argv[2]));r->mount(1,read(argv[3]));require(r->m.boot_from_disk(),"FD boot failed");r->wait("A>");
 for(const std::string drive:{"B:","A:","B:"}){auto start=r->m.cpu().cyc;r->type(drive+"\r");for(int i=0;;i++){require(i<3000,"Drive selection timeout");r->run(1);if(ends(r->screen(),drive.substr(0,1)+">"))break;}std::cout<<drive<<" selection seconds (including key input): "<<double(r->m.cpu().cyc-start)/6000000<<std::endl;}
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
