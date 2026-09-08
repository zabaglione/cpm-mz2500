typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
extern u8 call_fn,io_drive,io_write;
extern u16 call_arg,io_rec;
extern u8 *io_buf;
u16 sys(void) __sdcccall(0);
u8 disk(void) __sdcccall(0);
void quit(void) __sdcccall(0);

u8 flush_disk(void) __sdcccall(0);
