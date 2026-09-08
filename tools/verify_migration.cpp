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
 void type(const std::string&s){for(char c:s){int row,bit;if(c=='\r'){row=3;bit=2;}else{int n=toupper((unsigned char)c)-64;row=4+(n>>3);bit=n&7;}m.set_key(row,bit,true);run(4);m.set_key(row,bit,false);run(4);}}
 std::string wait(const std::string&a,const std::string&b="",bool allow_error=false){for(int i=0;i<250000;i+=32){run(32);auto s=screen();if(!allow_error&&s.find("ERROR:")!=std::string::npos)throw std::runtime_error(s);if(ends(s,a)||(!b.empty()&&ends(s,b)))return s;if(i%32768==0)std::cout<<"WAIT "<<frames<<" cycles "<<m.cpu().cyc<<" "<<a<<std::endl;}throw std::runtime_error("Timeout\n"+screen());}
 void mount(int n,const Bytes&data){require(m.insert_disk_bytes(n,data),"FD mount failed");}
 void hdd(const Bytes&data){require(m.insert_sasi_image(data.data(),data.size(),256),"HDD mount failed");}
};
int main(int argc,char**argv){try{
 static_assert(sizeof(((z80*)nullptr)->cyc)>=8,"Migration test requires a 64-bit cycle counter");
 require(argc==2,"usage: verify_migration /path/to/cpm-project");fs::path root=argv[1],qa=root/"build/migration-qa";
 const auto old=read(qa/"old.hdd"),blank=read(root/"build/migration_blank.d88"),boot=read(root/"build/cpm_migrate.d88");
 auto runner=std::make_unique<Runner>();auto&r=*runner;r.mount(0,boot);r.hdd(old);require(r.m.boot_from_disk(),"Boot failed");r.wait("A>");r.type("MIGRATE\r");r.wait("COMMAND:");r.type("B\r");r.wait("TYPE WRITE:");std::vector<Bytes> volumes;
 for(int n=1;;n++){r.mount(1,blank);r.type("WRITE\r");auto s=r.wait("TYPE WRITE:","COMMAND:");auto v=r.m.disk_image(1);write(qa/("volume-"+std::to_string(n)+".d88"),v);volumes.push_back(v);std::cout<<"BACKUP volume "<<n<<std::endl;if(ends(s,"COMMAND:")){require(s.find("BACKUP COMPLETE")!=s.npos,"Backup not complete");break;}}
 require(r.m.sasi_image()==old,"BACKUP changed source HDD");r.type("V\r");
 for(size_t i=0;i<volumes.size();i++){r.wait("TYPE READ:");r.mount(1,volumes[i]);r.type("READ\r");std::cout<<"VERIFY volume "<<i+1<<std::endl;}
 auto s=r.wait("COMMAND:");require(s.find("ALL VOLUMES VERIFIED")!=s.npos,"Verification incomplete");require(r.m.sasi_image()==old,"VERIFY changed source HDD");r.type("R\r");r.wait("TYPE ERASE TO START:");r.type("ERASE\r");
 for(size_t i=0;i<volumes.size();i++){r.wait("TYPE READ:");r.mount(1,volumes[i]);r.type("READ\r");std::cout<<"RESTORE volume "<<i+1<<std::endl;}
 s=r.wait("COMMAND:");require(s.find("MIGRATION COMPLETE")!=s.npos,"Restore incomplete");write(qa/"restored.hdd",r.m.sasi_image());write(qa/"restore-screen.txt",Bytes(s.begin(),s.end()));r.m.eject_disk(0);r.m.eject_disk(1);require(r.m.boot_from_disk(),"HDD boot failed");s=r.wait("C>");require(s.find("v3.1.2")!=s.npos,"Wrong OS after restore");write(qa/"hdd-boot-screen.txt",Bytes(s.begin(),s.end()));std::cout<<"MIGRATION RUNTIME PASS: "<<volumes.size()<<" volumes; "<<r.frames<<" frames"<<std::endl;
 // A fresh process cannot restore without first verifying the full archive.
 auto guard=std::make_unique<Runner>();guard->mount(0,boot);guard->hdd(old);require(guard->m.boot_from_disk(),"Guard boot failed");guard->wait("A>");guard->type("MIGRATE\r");guard->wait("COMMAND:");guard->type("R\r");s=guard->wait("A>","",true);require(s.find("RUN V AND VERIFY")!=s.npos,"Restore guard missing");require(guard->m.sasi_image()==old,"Rejected restore wrote HDD");std::cout<<"RESTORE GUARD PASS"<<std::endl;
 // Corrupt media and wrong volume are rejected before any HDD write.
 auto reject=[&](Bytes disk,const char*message){
  auto g=std::make_unique<Runner>();g->mount(0,boot);g->hdd(old);require(g->m.boot_from_disk(),"Negative boot failed");g->wait("A>");g->type("MIGRATE\r");g->wait("COMMAND:");g->type("V\r");g->wait("TYPE READ:");g->mount(1,disk);g->type("READ\r");auto screen=g->wait("A>","",true);require(screen.find(message)!=screen.npos,"Expected rejection missing");require(g->m.sasi_image()==old,"Rejected archive wrote HDD");std::cout<<"REJECTION PASS: "<<message<<std::endl;
 };
 auto corrupt=volumes[0];size_t track=corrupt[32]|(size_t(corrupt[33])<<8)|(size_t(corrupt[34])<<16)|(size_t(corrupt[35])<<24);
 corrupt[track+16]^=1;reject(corrupt,"INVALID BACKUP HEADER");
 corrupt=volumes[0];corrupt[track+2*272+16]^=1;reject(corrupt,"BACKUP PAYLOAD CRC FAILED");
 reject(volumes[1],"WRONG VOLUME NUMBER");
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
