/* MZ-2500 file migration: source HDD is never written during BACKUP/VERIFY.
 * Backup disks are preformatted 640K 2DD media, NOT CP/M filesystems.
 * CRC32 protects each 8K chunk before restore writes any of its records.
 */
#include "migration.h"
#include "generated.h"
#define CHUNK 8192
#define VOLREC 4800
#define HDRREC 4
#define DIRREC 256
#define MAXBLK 2042
#define NEWMAX 2038
#define MAXVOL 28
static u8 buffer[CHUNK],header[512],scratch[128],catalogbuf[128],line[20];
static u32 verified_headers[MAXVOL];
static u8 used[MAXBLK],fcb[36],dstfcb[36];
static u16 mapping[MAXBLK],blocks[MAXBLK];
/* Directory identity index: hash matches are confirmed against raw entries. */
static u32 identities[1024];
static u16 counts[2],entries[2],source_off,totalvol,volno,payload,chunkno;
static u32 setid,streamlen,streampos,dirhash[2];
static u8 mode,phase,verified,selected,last_drive;
static u16 bdos(u8 n,u16 p){call_fn=n;call_arg=p;return sys();}
static void text(const char*s){while(*s)bdos(2,*s++);}
static void number(u16 n){char digits[6];u8 k=0;do{digits[k++]='0'+n%10;n/=10;}while(n);while(k)bdos(2,digits[--k]);}
static void fail(const char*s){text("\r\nERROR: ");text(s);text("\r\nSTOPPED. Keep all backup disks. Reboot from A: to retry.\r\n");quit();}
static u8 equal(const u8*a,const u8*b,u16 n){while(n--)if(*a++!=*b++)return 0;return 1;}
static void clear(u8*a,u16 n){while(n--)*a++=0;}
static void copy(u8*a,const u8*b,u16 n){while(n--)*a++=*b++;}
static u16 word(const u8*p){return p[0]|((u16)p[1]<<8);}
static u32 dword(const u8*p){return (u32)word(p)|((u32)word(p+2)<<16);}
static void putw(u8*p,u16 n){p[0]=n;p[1]=n>>8;}
static void putl(u8*p,u32 n){putw(p,(u16)n);putw(p+2,(u16)(n>>16));}
static const u32 crc_table[256]={0x00000000UL,0x77073096UL,0xee0e612cUL,0x990951baUL,0x076dc419UL,0x706af48fUL,0xe963a535UL,0x9e6495a3UL,0x0edb8832UL,0x79dcb8a4UL,0xe0d5e91eUL,0x97d2d988UL,0x09b64c2bUL,0x7eb17cbdUL,0xe7b82d07UL,0x90bf1d91UL,0x1db71064UL,0x6ab020f2UL,0xf3b97148UL,0x84be41deUL,0x1adad47dUL,0x6ddde4ebUL,0xf4d4b551UL,0x83d385c7UL,0x136c9856UL,0x646ba8c0UL,0xfd62f97aUL,0x8a65c9ecUL,0x14015c4fUL,0x63066cd9UL,0xfa0f3d63UL,0x8d080df5UL,0x3b6e20c8UL,0x4c69105eUL,0xd56041e4UL,0xa2677172UL,0x3c03e4d1UL,0x4b04d447UL,0xd20d85fdUL,0xa50ab56bUL,0x35b5a8faUL,0x42b2986cUL,0xdbbbc9d6UL,0xacbcf940UL,0x32d86ce3UL,0x45df5c75UL,0xdcd60dcfUL,0xabd13d59UL,0x26d930acUL,0x51de003aUL,0xc8d75180UL,0xbfd06116UL,0x21b4f4b5UL,0x56b3c423UL,0xcfba9599UL,0xb8bda50fUL,0x2802b89eUL,0x5f058808UL,0xc60cd9b2UL,0xb10be924UL,0x2f6f7c87UL,0x58684c11UL,0xc1611dabUL,0xb6662d3dUL,0x76dc4190UL,0x01db7106UL,0x98d220bcUL,0xefd5102aUL,0x71b18589UL,0x06b6b51fUL,0x9fbfe4a5UL,0xe8b8d433UL,0x7807c9a2UL,0x0f00f934UL,0x9609a88eUL,0xe10e9818UL,0x7f6a0dbbUL,0x086d3d2dUL,0x91646c97UL,0xe6635c01UL,0x6b6b51f4UL,0x1c6c6162UL,0x856530d8UL,0xf262004eUL,0x6c0695edUL,0x1b01a57bUL,0x8208f4c1UL,0xf50fc457UL,0x65b0d9c6UL,0x12b7e950UL,0x8bbeb8eaUL,0xfcb9887cUL,0x62dd1ddfUL,0x15da2d49UL,0x8cd37cf3UL,0xfbd44c65UL,0x4db26158UL,0x3ab551ceUL,0xa3bc0074UL,0xd4bb30e2UL,0x4adfa541UL,0x3dd895d7UL,0xa4d1c46dUL,0xd3d6f4fbUL,0x4369e96aUL,0x346ed9fcUL,0xad678846UL,0xda60b8d0UL,0x44042d73UL,0x33031de5UL,0xaa0a4c5fUL,0xdd0d7cc9UL,0x5005713cUL,0x270241aaUL,0xbe0b1010UL,0xc90c2086UL,0x5768b525UL,0x206f85b3UL,0xb966d409UL,0xce61e49fUL,0x5edef90eUL,0x29d9c998UL,0xb0d09822UL,0xc7d7a8b4UL,0x59b33d17UL,0x2eb40d81UL,0xb7bd5c3bUL,0xc0ba6cadUL,0xedb88320UL,0x9abfb3b6UL,0x03b6e20cUL,0x74b1d29aUL,0xead54739UL,0x9dd277afUL,0x04db2615UL,0x73dc1683UL,0xe3630b12UL,0x94643b84UL,0x0d6d6a3eUL,0x7a6a5aa8UL,0xe40ecf0bUL,0x9309ff9dUL,0x0a00ae27UL,0x7d079eb1UL,0xf00f9344UL,0x8708a3d2UL,0x1e01f268UL,0x6906c2feUL,0xf762575dUL,0x806567cbUL,0x196c3671UL,0x6e6b06e7UL,0xfed41b76UL,0x89d32be0UL,0x10da7a5aUL,0x67dd4accUL,0xf9b9df6fUL,0x8ebeeff9UL,0x17b7be43UL,0x60b08ed5UL,0xd6d6a3e8UL,0xa1d1937eUL,0x38d8c2c4UL,0x4fdff252UL,0xd1bb67f1UL,0xa6bc5767UL,0x3fb506ddUL,0x48b2364bUL,0xd80d2bdaUL,0xaf0a1b4cUL,0x36034af6UL,0x41047a60UL,0xdf60efc3UL,0xa867df55UL,0x316e8eefUL,0x4669be79UL,0xcb61b38cUL,0xbc66831aUL,0x256fd2a0UL,0x5268e236UL,0xcc0c7795UL,0xbb0b4703UL,0x220216b9UL,0x5505262fUL,0xc5ba3bbeUL,0xb2bd0b28UL,0x2bb45a92UL,0x5cb36a04UL,0xc2d7ffa7UL,0xb5d0cf31UL,0x2cd99e8bUL,0x5bdeae1dUL,0x9b64c2b0UL,0xec63f226UL,0x756aa39cUL,0x026d930aUL,0x9c0906a9UL,0xeb0e363fUL,0x72076785UL,0x05005713UL,0x95bf4a82UL,0xe2b87a14UL,0x7bb12baeUL,0x0cb61b38UL,0x92d28e9bUL,0xe5d5be0dUL,0x7cdcefb7UL,0x0bdbdf21UL,0x86d3d2d4UL,0xf1d4e242UL,0x68ddb3f8UL,0x1fda836eUL,0x81be16cdUL,0xf6b9265bUL,0x6fb077e1UL,0x18b74777UL,0x88085ae6UL,0xff0f6a70UL,0x66063bcaUL,0x11010b5cUL,0x8f659effUL,0xf862ae69UL,0x616bffd3UL,0x166ccf45UL,0xa00ae278UL,0xd70dd2eeUL,0x4e048354UL,0x3903b3c2UL,0xa7672661UL,0xd06016f7UL,0x4969474dUL,0x3e6e77dbUL,0xaed16a4aUL,0xd9d65adcUL,0x40df0b66UL,0x37d83bf0UL,0xa9bcae53UL,0xdebb9ec5UL,0x47b2cf7fUL,0x30b5ffe9UL,0xbdbdf21cUL,0xcabac28aUL,0x53b39330UL,0x24b4a3a6UL,0xbad03605UL,0xcdd70693UL,0x54de5729UL,0x23d967bfUL,0xb3667a2eUL,0xc4614ab8UL,0x5d681b02UL,0x2a6f2b94UL,0xb40bbe37UL,0xc30c8ea1UL,0x5a05df1bUL,0x2d02ef8dUL};
static u32 crc(u32 c,const u8*p,u16 n){while(n--){u8 i=(u8)c^*p++;c=(c>>8)^crc_table[i];}return c;}
static u32 checksum(const u8*p,u16 n){return crc(0xffffffffUL,p,n)^0xffffffffUL;}
static void ask(const char*expected){u8 i;line[0]=16;line[1]=0;bdos(10,(u16)line);text("\r\n");for(i=0;expected[i];i++)if(i>=line[1]||(line[i+2]&0xdf)!=expected[i])fail("CANCELLED");if(i!=line[1])fail("CANCELLED");}
static void io(u8 d,u16 r,u8*p,u8 wr){if(last_drive!=d){if(flush_disk())fail("DISK FLUSH FAILED");last_drive=d;}io_drive=d;io_rec=r;io_buf=p;io_write=wr;if(disk())fail(wr?"DISK WRITE FAILED":"DISK READ FAILED");}
/* Evict the BIOS physical-sector cache through a different drive after swaps. */
static void evict(void){io(0,32,scratch,0);}
static void prompt(u8 writing){text("\r\nINSERT B: VOL ");number(volno);text(writing?" - ALL CONTENTS WILL BE ERASED. TYPE WRITE: ":" - TYPE READ: ");ask(writing?"WRITE":"READ");evict();}
static void check_boot(void){io(0,32,scratch,0);if(!equal(scratch+1,(const u8*)"IPLPROCP/M-PLUS",14)||scratch[32]!=12||scratch[33]!=13||scratch[34]!=14||scratch[35]!=7||scratch[36]!=255)fail("USE THE MATCHING MIGRATION BOOT FD IN A:");}
static void identify(void){io(2,0,scratch,0);if(!equal(scratch+1,(const u8*)"IPLPRO",6))fail("UNKNOWN HDD HEADER");
 if(equal(scratch+7,(const u8*)"CP/M-2.2",8))source_off=3;
 else if(equal(scratch+7,(const u8*)"CP/M-PLUS",9)&&scratch[32]==5)source_off=4;
 else fail("SOURCE MUST BE CP/M 2.2 OR NONBANKED v3.0.0");
 text("SOURCE RESERVED TRACKS: ");number(source_off);text("\r\n");}
static u8 same_identity(const u8*a,const u8*b){u8 i;if(a[0]!=b[0]||((a[12]>>1)!=(b[12]>>1))||a[14]!=b[14])return 0;for(i=1;i<12;i++)if((a[i]&127)!=(b[i]&127))return 0;return 1;}
static u16 records(const u8*e){if(e[15]>128||e[12]>31||e[14]>63)fail("INVALID EXTENT");return (e[12]&1)*128+e[15];}
static void scan(u8 drive,u8 slot){u16 r,i,j,k,n,nb,b,next=8,entry=0;u32 hash=0xffffffffUL,id;u8*e;
 clear(used,sizeof used);clear((u8*)identities,sizeof identities);for(i=0;i<8;i++)used[i]=1;
 entries[slot]=0;
 for(r=0;r<DIRREC;r++){
  io(drive,source_off*64+r,catalogbuf,0);hash=crc(hash,catalogbuf,128);
  for(i=0;i<4;i++,entry++){
   e=catalogbuf+i*32;if(e[0]==229)continue;if(e[0]>15)fail("UNSUPPORTED DIRECTORY RECORD");
   if((e[1]&127)<=32)fail("INVALID FILENAME");for(j=1;j<12;j++)if((e[j]&127)<32||(e[j]&127)>126)fail("INVALID FILENAME");
   n=records(e);nb=(n+31)/32;id=0xffffffffUL;for(j=0;j<12;j++){u8 c=e[j]&127;id=crc(id,&c,1);} {u8 ex[2];ex[0]=e[12]>>1;ex[1]=e[14];id=crc(id,ex,2);}if(!id)id=1;
   for(k=0;k<entry;k++)if(identities[k]==id){io(drive,source_off*64+k/4,scratch,0);if(same_identity(e,scratch+(k%4)*32))fail("DUPLICATE FILE EXTENT");}
   identities[entry]=id;entries[slot]++;
   for(j=0;j<8;j++){b=word(e+16+j*2);if(j<nb){if(b<8||b>=(source_off==3?2042:2040)||used[b])fail("INVALID OR SHARED DATA BLOCK");used[b]=1;}else if(b)fail("UNEXPECTED ALLOCATION POINTER");}
  }
 }
 for(i=8;i<MAXBLK;i++)if(used[i]){mapping[i]=next;blocks[next-8]=i;next++;}
 counts[slot]=next-8;dirhash[slot]=hash^0xffffffffUL;
 if(next+(slot==0?INSTALL_BLOCKS:0)>NEWMAX||entries[slot]+(slot==0?INSTALL_ENTRIES:0)>1024)fail("NOT ENOUGH SPACE IN NEW FORMAT");
 text(drive==2?"C: DATA BLOCKS ":"D: DATA BLOCKS ");number(counts[slot]);text(" DIRECTORY ENTRIES ");number(entries[slot]);text("\r\n");
}
static void meta(void){clear(header,512);copy(header,(const u8*)"MZMG31\r\n",8);putw(header+8,1);putw(header+10,source_off);putl(header+12,setid);putw(header+16,volno);putw(header+18,totalvol);putl(header+20,streamlen);putw(header+24,counts[0]);putw(header+26,counts[1]);putw(header+28,payload);putw(header+30,entries[0]);putw(header+32,entries[1]);}
static void header_write(void){u8 r;putl(header+508,checksum(header,508));for(r=1;r<4;r++)io(1,r,header+r*128,1);io(1,0,header,1);}
static void header_read(u8 first){u8 r;for(r=0;r<4;r++)io(1,r,header+r*128,0);
 if(!equal(header,(const u8*)"MZMG31\r\n",8)||word(header+8)!=1||checksum(header,508)!=dword(header+508))fail("INVALID BACKUP HEADER");
 if(word(header+16)!=volno)fail("WRONG VOLUME NUMBER");
 if(first){source_off=word(header+10);setid=dword(header+12);totalvol=word(header+18);streamlen=dword(header+20);counts[0]=word(header+24);counts[1]=word(header+26);entries[0]=word(header+30);entries[1]=word(header+32);
  if((source_off!=3&&source_off!=4)||counts[0]+8+INSTALL_BLOCKS>NEWMAX||counts[1]+8>NEWMAX||entries[0]+INSTALL_ENTRIES>1024||entries[1]>1024||streamlen!=512UL+32UL*((u32)counts[0]+counts[1])||totalvol!=(streamlen+VOLREC-1)/VOLREC||!totalvol||totalvol>MAXVOL)fail("INVALID BACKUP GEOMETRY");
 }else if(dword(header+12)!=setid||word(header+18)!=totalvol||dword(header+20)!=streamlen||word(header+10)!=source_off||word(header+24)!=counts[0]||word(header+26)!=counts[1]||word(header+30)!=entries[0]||word(header+32)!=entries[1])fail("WRONG BACKUP SET");
 payload=word(header+28);if(payload!=(u16)((streamlen-streampos)>VOLREC?VOLREC:streamlen-streampos))fail("INVALID VOLUME LENGTH");
}
static void generate(u32 pos,u8*p){u32 first=256UL+32UL*counts[0];u16 local,r,b,i,j;u8 slot=pos>=first;u8*e;
 if(slot)pos-=first;local=(u16)pos;
 if(selected!=slot){u16 c=counts[slot],n=entries[slot];u32 h=dirhash[slot];scan(slot+2,slot);if(counts[slot]!=c||entries[slot]!=n||dirhash[slot]!=h)fail("SOURCE CHANGED");selected=slot;}
 if(local<256){io(slot+2,source_off*64+local,p,0);for(i=0;i<4;i++){e=p+i*32;if(e[0]==229)continue;for(j=0;j<8;j++){b=word(e+16+j*2);if(b)putw(e+16+j*2,mapping[b]);}}}
 else{r=local-256;b=blocks[r/32];io(slot+2,source_off*64+b*32+(r%32),p,0);}
}
static void backup(void){u16 r,n;u32 h,pos;
 identify();scan(2,0);scan(3,1);setid=dirhash[0]^(dirhash[1]<<1)^0x310022UL;streamlen=512UL+32UL*((u32)counts[0]+counts[1]);totalvol=(streamlen+VOLREC-1)/VOLREC;
 text("BACKUP VOLUMES REQUIRED: ");number(totalvol);text("\r\nA: stays inserted. B: needs preformatted 640K 2DD disks.\r\n");
 text("CHECKING SOURCE CONTENT...\r\n");selected=255;h=0xffffffffUL;
 for(pos=0;pos<streamlen;pos++){generate(pos,scratch);h=crc(h,scratch,128);}setid=h^0xffffffffUL;
 streampos=0;selected=255;
 for(volno=1;volno<=totalvol;volno++){
  payload=(u16)((streamlen-streampos)>VOLREC?VOLREC:streamlen-streampos);prompt(1);meta();clear(scratch,128);io(1,0,scratch,1);
  for(chunkno=0;chunkno<(payload+63)/64;chunkno++){
   n=payload-chunkno*64;if(n>64)n=64;clear(buffer,CHUNK);
   for(r=0;r<n;r++)generate(streampos+chunkno*64+r,buffer+r*128);
   h=checksum(buffer,CHUNK);putl(header+64+chunkno*4,h);
   for(r=0;r<64;r++)io(1,HDRREC+chunkno*64+r,buffer+r*128,2);
   /* Read from media after evicting the BIOS cache, then compare the CRC. */
   evict();for(r=0;r<64;r++)io(1,HDRREC+chunkno*64+r,buffer+r*128,0);
   if(checksum(buffer,CHUNK)!=h)fail("BACKUP READBACK CRC FAILED");
  }
  header_write();streampos+=payload;text("VOLUME WRITTEN AND VERIFIED: ");number(volno);text("\r\n");
 }
 verified=0;text("BACKUP COMPLETE. Select V to verify all volumes before restore.\r\n");
}
static void archive(u8 restoring){u16 r,n;u32 at,first,sum=0xffffffffUL;
 streampos=0;volno=1;do{
  prompt(0);header_read(volno==1&&!restoring);
  if(restoring){if(dword(header+508)!=verified_headers[volno-1])fail("BACKUP CHANGED AFTER VERIFICATION");}
  else verified_headers[volno-1]=dword(header+508);
  first=256UL+32UL*counts[0];
  for(chunkno=0;chunkno<(payload+63)/64;chunkno++){
   for(r=0;r<64;r++)io(1,HDRREC+chunkno*64+r,buffer+r*128,0);
   if(checksum(buffer,CHUNK)!=dword(header+64+chunkno*4))fail("BACKUP PAYLOAD CRC FAILED");
   n=payload-chunkno*64;if(n>64)n=64;
   sum=crc(sum,buffer,n*128);
   if(restoring){
    for(r=0;r<n;r++){u8 d;u16 target;at=streampos+chunkno*64+r;d=at>=first?3:2;if(d==3)at-=first;target=320+(u16)at;io(d,target,buffer+r*128,2);}
    evict();
    for(r=0;r<n;r++){u8 d;u16 target;at=streampos+chunkno*64+r;d=at>=first?3:2;if(d==3)at-=first;target=320+(u16)at;io(d,target,scratch,0);if(!equal(scratch,buffer+r*128,128)){text("READBACK DRIVE/RECORD: ");number(d);text("/");number(target);text(" GOT/EXPECTED: ");number(scratch[0]);text("/");number(buffer[r*128]);text("\r\n");fail("HDD READBACK FAILED");}}
   }
  }
  streampos+=payload;text(restoring?"RESTORED VOLUME ":"VERIFIED VOLUME ");number(volno);text("\r\n");volno++;
 }while(volno<=totalvol);
 if((sum^0xffffffffUL)!=setid)fail("BACKUP SET CONTENT CRC FAILED");
 if(!restoring){verified=1;text("ALL VOLUMES VERIFIED. R will erase and rebuild C: and D:.\r\n");}
}
static void setup_fcb(u8*p,u8 drive,const char*name){u8 i=1;clear(p,36);p[0]=drive;for(i=1;i<12;i++)p[i]=' ';i=1;while(*name){if(*name=='.'){i=9;name++;}else p[i++]=*name++;}}
static void install_files(void){u16 k;u8 rc;u32 a,b;
 bdos(13,0);bdos(14,0);bdos(32,0);
 for(k=0;k<INSTALL_COUNT;k++){
  setup_fcb(fcb,1,install_names[k]);setup_fcb(dstfcb,3,install_names[k]);
  if((u8)bdos(15,(u16)fcb)==255)fail("SYSTEM FILE MISSING ON A:");
  bdos(30,(u16)dstfcb);bdos(19,(u16)dstfcb);
  if((u8)bdos(22,(u16)dstfcb)==255)fail("CANNOT CREATE SYSTEM FILE");
  bdos(26,(u16)buffer);a=0xffffffffUL;
  while(!(rc=(u8)bdos(20,(u16)fcb))){a=crc(a,buffer,128);if((u8)bdos(21,(u16)dstfcb))fail("SYSTEM FILE WRITE FAILED");}
  if(rc!=1||(u8)bdos(16,(u16)dstfcb)==255)fail("SYSTEM FILE CLOSE FAILED");bdos(16,(u16)fcb);bdos(48,0);
  setup_fcb(dstfcb,3,install_names[k]);if((u8)bdos(15,(u16)dstfcb)==255)fail("SYSTEM FILE VERIFY OPEN FAILED");b=0xffffffffUL;
  while(!(rc=(u8)bdos(20,(u16)dstfcb)))b=crc(b,buffer,128);
  if(rc!=1||a!=b)fail("SYSTEM FILE VERIFY FAILED");bdos(16,(u16)dstfcb);
 }
 bdos(48,0);text("CP/M PLUS SYSTEM FILES INSTALLED AND VERIFIED.\r\n");
}
static void install_boot(void){u16 bank,r,src,dst;u32 sum=0xffffffffUL;
 check_boot();
 for(bank=0;bank<4;bank++)for(r=0;r<64;r++){
  src=bank*64+r+(r>=32?64:0);dst=32+bank*64+r;io(0,src,buffer,0);
  if(dst==BOOT_PATCH_RECORD)buffer[BOOT_PATCH_OFFSET]=2;
  sum=crc(sum,buffer,128);io(2,dst,buffer,1);evict();io(2,dst,scratch,0);if(!equal(buffer,scratch,128))fail("BOOT READBACK FAILED");
 }
 if((sum^0xffffffffUL)!=BOOT_CRC)fail("BOOT FD DOES NOT MATCH THIS TOOL");
 io(0,33,buffer,0);io(2,1,buffer,1);io(0,32,buffer,0);io(2,0,buffer,1);evict();io(2,0,scratch,0);if(!equal(buffer,scratch,128))fail("BOOT HEADER READBACK FAILED");
}
static void restore(void){u16 r;u8 d;
 if(!verified)fail("RUN V AND VERIFY EVERY BACKUP VOLUME FIRST");
 text("C: AND D: WILL BE REPLACED. Old system commands stay in backups.\r\nTYPE ERASE TO START: ");ask("ERASE");check_boot();
 clear(buffer,128);for(d=2;d<4;d++)for(r=0;r<320;r++)io(d,r,buffer,1);
 archive(1);install_files();install_boot();verified=0;
 text("MIGRATION COMPLETE. Remove A: and press IPL for HDD boot.\r\n");
}
void main(void){u8 op;verified=0;last_drive=255;
 if((u8)bdos(12,0)!=0x31||(*(u16*)1)!=0xe803)fail("CP/M PLUS v3.1 MIGRATION FD REQUIRED");
 check_boot();text("MZ-2500 MIGRATE 1.0\r\nBackup/verify do not write the HDD. Only supported C:/D: 8MB layout.\r\n");
 for(;;){text("\r\nB=BACKUP  V=VERIFY  R=RESTORE  Q=QUIT\r\nCOMMAND: ");line[0]=1;line[1]=0;bdos(10,(u16)line);text("\r\n");if(line[1]!=1)continue;op=line[2]&0xdf;if(op=='B')backup();else if(op=='V')archive(0);else if(op=='R')restore();else if(op=='Q')quit();}
}
