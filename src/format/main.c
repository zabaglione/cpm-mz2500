/* Drive-selectable physical formatter. FDC register/data polarity follows MZ hardware.
 * MFM marks/CRC: Fujitsu MB8876A/MB8877A datasheet, IBM System 34 format.
 * No BIOS disk calls while the formatter owns the controller.
 */
#include "../migration/migration.h"
u8 cylinder,side,sector,drive,status;
u16 transferred;
u8 track[6400],readbuf[256];
u8 input[20];
u8 hw_start(void) __sdcccall(0);
u8 hw_seek(void) __sdcccall(0);
u8 hw_track(void) __sdcccall(0);
u8 hw_read(void) __sdcccall(0);
void hw_stop(void) __sdcccall(0);
static u16 bdos(u8 n,u16 p){call_fn=n;call_arg=p;return sys();}
static void text(const char*p){while(*p)bdos(2,*p++);}
static void hex(u8 n){const char*h="0123456789ABCDEF";bdos(2,h[n>>4]);bdos(2,h[n&15]);}
static void stop(const char*p){hw_stop();text(p);text("\r\n");quit();}
static void error(const char*p){hw_stop();text("\r\nERROR: ");text(p);text(" C/H/R=");hex(cylinder);text("/");hex(side);text("/");hex(sector);text(" STATUS=");hex(status);text(" BYTES=");hex(transferred>>8);hex(transferred);text("\r\nDISK NOT READY FOR BACKUP.\r\n");quit();}
static u16 pos;
static void emit(u8 b){track[pos++]=~b;}
static void repeat(u8 b,u16 n){while(n--)emit(b);}
static void make_track(void){u8 r;pos=0;repeat(0x4e,80);repeat(0,12);repeat(0xf6,3);emit(0xfc);repeat(0x4e,50);
 for(r=1;r<=16;r++){repeat(0,12);repeat(0xf5,3);emit(0xfe);emit(cylinder);emit(side);emit(r);emit(1);emit(0xf7);repeat(0x4e,22);repeat(0,12);repeat(0xf5,3);emit(0xfb);repeat(0x1a,256);emit(0xf7);repeat(0x4e,54);}
 while(pos<sizeof track)emit(0x4e);
}
void main(void){u8 i;u16 j;
 cylinder=side=sector=status=0;transferred=0;
 if((u8)bdos(12,0)!=0x31||(*(u16*)1)!=0xe803){text("USE THE CP/M PLUS MIGRATION BOOT FD.\r\n");quit();}
 /* Parse the CP/M command tail before any BDOS call can reuse DMA 0080h. */
 {u8 *tail=(u8*)0x81,n=*(u8*)0x80,k=0,ch;
  while(k<n&&(tail[k]==' '||tail[k]==9))k++;
  if(k>=n)goto usage;
  ch=tail[k++]&0xdf;if(ch!='A'&&ch!='B')goto usage;drive=ch-'A';
  if(k>=n||tail[k++]!=':')goto usage;
  while(k<n&&(tail[k]==' '||tail[k]==9))k++;
  if(k!=n)goto usage;
 }
 /* Flush before the prompt: the user may exchange the boot FD afterwards. */
 if((u8)bdos(48,0)){text("BIOS FLUSH FAILED.\r\n");quit();}
 text("FORMAT 1.1 - 640K 2DD\r\nTARGET: ");bdos(2,'A'+drive);
 text(": - ALL CONTENTS WILL BE ERASED.\r\nINSERT DISPOSABLE 2DD DISK IN TARGET DRIVE.\r\nTYPE FORMAT ");bdos(2,'A'+drive);text(": TO START: ");
 input[0]=16;input[1]=0;bdos(10,(u16)input);text("\r\n");
 if(input[1]!=9)goto cancelled;
 for(i=0;i<7;i++)if((input[i+2]>='a'&&input[i+2]<='z'?input[i+2]-32:input[i+2])!="FORMAT "[i])goto cancelled;
 if((input[9]&0xdf)!='A'+drive||input[10]!=':')goto cancelled;
 if(hw_start())error("DRIVE NOT READY, WRITE PROTECTED OR RESTORE FAILED");
 for(cylinder=0;cylinder<80;cylinder++){
  if(cylinder&&hw_seek())error("SEEK FAILED");
  for(side=0;side<2;side++){
   sector=0;make_track();text("FORMAT C/H=");hex(cylinder);text("/");hex(side);text("\r\n");
   if(hw_track())error("WRITE TRACK FAILED");
   for(sector=1;sector<=16;sector++){
    if(hw_read())error("SECTOR READ FAILED");
    for(j=0;j<256;j++)if(readbuf[j]!=0xe5)error("DATA VERIFY FAILED");
   }
  }
 }
 stop("FORMAT AND VERIFY COMPLETE: 2560 SECTORS. RESTORE BOOT MEDIA IF REMOVED.");
 return;
usage:
 text("USAGE: FORMAT A: | FORMAT B: (640K 2DD FDD ONLY)\r\n");quit();
cancelled:
 text("CANCELLED.\r\n");quit();
}
