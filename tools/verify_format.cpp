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
 require(argc==2,"usage: verify_format /path/to/cpm-project");fs::path root=argv[1],qa=root/"build/format-qa";fs::create_directories(qa);
 const auto boot=read(root/"build/cpm_migrate.d88");auto hdd=read(root/"build/cpm.hdd");
 // Minimal old-layout fixture: two empty directories and a CP/M 2.2 header.
 const std::string label="CP/M-2.2   \r";std::copy(label.begin(),label.end(),hdd.begin()+8192+7);
 for(size_t base:{size_t(32),size_t(32800)})std::fill(hdd.begin()+base*256+3*8192,hdd.begin()+base*256+3*8192+32768,0xe5);
 auto start=[&](const std::string&cmd="FORMAT B:"){auto r=std::make_unique<Runner>();r->mount(0,boot);r->hdd(hdd);require(r->m.boot_from_disk(),"Boot failed");r->wait("A>");r->type(cmd+"\r");r->wait("TO START:");return r;};
 auto r=start();require(r->m.insert_blank_disk(1),"Blank FD failed");auto empty=r->m.disk_image(1);require(empty.size()==0x2b0,"Fixture is not unformatted");r->type("FORMAT B:\r");auto screen=r->wait("A>");require(screen.find("FORMAT AND VERIFY COMPLETE")!=screen.npos,"Format incomplete");require(r->m.disk_image(0)==boot,"A: changed");require(r->m.sasi_image()==hdd,"HDD changed");auto result=r->m.disk_image(1);write(qa/"formatted.d88",result);write(qa/"success.txt",Bytes(screen.begin(),screen.end()));std::cout<<"FORMAT UNFORMATTED FD PASS "<<r->frames<<" frames"<<std::endl;
 // The warm boot must restore BIOS control and allow MIGRATE to load from A:.
 r->type("MIGRATE\r");r->wait("COMMAND:");r->type("B\r");r->wait("TYPE WRITE:");r->type("WRITE\r");screen=r->wait("COMMAND:");require(screen.find("BACKUP COMPLETE")!=screen.npos,"Backup to formatted FD failed");
 r->type("V\r");r->wait("TYPE READ:");r->type("READ\r");screen=r->wait("COMMAND:");require(screen.find("ALL VOLUMES VERIFIED")!=screen.npos,"Formatted FD backup verify failed");require(r->m.sasi_image()==hdd,"Backup/verify changed HDD");require(r->m.disk_image(0)==boot,"Backup/verify changed A:");write(qa/"backup-volume.d88",r->m.disk_image(1));
 r->type("Q\r");r->wait("A>");std::cout<<"MIGRATE BACKUP AND VERIFY AFTER FORMAT PASS"<<std::endl;
 auto reject=[&](int mode,const std::string&answer,const std::string&expected){auto g=start();if(mode!=0)require(g->m.insert_blank_disk(1),"Blank failed");if(mode==2)g->m.set_disk_write_protected(1,true);auto before=g->m.disk_image(1);g->type(answer+"\r");auto s=g->wait("A>","",true);require(s.find(expected)!=s.npos,"Expected format rejection missing");require(g->m.disk_image(1)==before,"Rejected operation changed B:");require(g->m.disk_image(0)==boot,"Rejected operation changed A:");require(g->m.sasi_image()==hdd,"Rejected operation changed HDD");std::cout<<"REJECTION PASS mode="<<mode<<" "<<expected<<std::endl;};
 reject(1,"NO","CANCELLED");reject(0,"FORMAT B:","ERROR:");reject(2,"FORMAT B:","ERROR:");
 // Removal during a physical track write must stop, never report success.
 auto g=start();g->m.insert_blank_disk(1);g->type("FORMAT B:\r");
 for(int i=0;i<1000&&g->m.disk_image(1).size()==0x2b0;i++)g->run(1);
 require(g->m.disk_image(1).size()>0x2b0,"No physical track created before removal");g->m.eject_disk(1);screen=g->wait("A>","",true);require(screen.find("ERROR:")!=screen.npos&&screen.find("FORMAT AND VERIFY COMPLETE")==screen.npos,"Removal not rejected");require(g->m.disk_image(0)==boot&&g->m.sasi_image()==hdd,"Removal altered other disks");std::cout<<"MID-FORMAT REMOVAL PASS"<<std::endl;
 // Formatting A: after loading the command must leave B: and HDD intact.
 auto a=start("FORMAT A:");a->mount(1,boot);require(a->m.insert_blank_disk(0),"Blank A failed");a->type("FORMAT A:\r");screen=a->wait("A>");require(screen.find("FORMAT AND VERIFY COMPLETE")!=screen.npos,"A format incomplete");require(a->m.disk_image(1)==boot&&a->m.sasi_image()==hdd,"A format altered other drives");write(qa/"formatted-a.d88",a->m.disk_image(0));std::cout<<"FORMAT A PASS"<<std::endl;
 reject(1,"FORMAT A:","CANCELLED");
 for(const std::string cmd:{"FORMAT","FORMAT C:","FORMAT D:","FORMAT B", "FORMAT B: A:"}){
  auto x=std::make_unique<Runner>();x->mount(0,boot);x->mount(1,boot);x->hdd(hdd);require(x->m.boot_from_disk(),"Argument boot failed");x->wait("A>");x->type(cmd+"\r");screen=x->wait("A>");require(screen.find("USAGE:")!=screen.npos,"Invalid argument accepted");require(x->m.disk_image(0)==boot&&x->m.disk_image(1)==boot&&x->m.sasi_image()==hdd,"Invalid argument altered media");std::cout<<"ARGUMENT REJECTION PASS: "<<cmd<<std::endl;
 }
 std::cout<<"FORMAT RUNTIME PASS"<<std::endl;return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
