// Test-only probe: executes trusted generated ELF with simavr for 2.5 seconds.
#include <stdio.h>
#include <stdint.h>
#include "sim_avr.h"
#include "sim_elf.h"
#include "avr_ioport.h"
#include "avr_uart.h"
#include "sim_io.h"
static avr_t *mcu;
static int last=-1, edges=0, count=0;
static double changes[16];
static int levels[16];
static void output(struct avr_irq_t *irq,uint32_t value,void *param){
    (void)irq;(void)param;
    int level=value&1;
    if(level!=last){
        if(count<16){changes[count]=(double)mcu->cycle/16000;levels[count++]=level;}
        edges++;last=level;
    }
}
int main(int argc,char **argv){
    if(argc!=2)return 2;
    elf_firmware_t fw={0};if(elf_read_firmware(argv[1],&fw))return 3;
    mcu=avr_make_mcu_by_name("atmega328p");if(!mcu||avr_init(mcu))return 4;
    mcu->frequency=16000000;mcu->vcc=mcu->avcc=mcu->aref=5000;
    avr_load_firmware(mcu,&fw);
    uint32_t flags=0;avr_ioctl(mcu,AVR_IOCTL_UART_SET_FLAGS('0'),&flags);
    avr_irq_register_notify(avr_io_getirq(mcu,AVR_IOCTL_IOPORT_GETIRQ('D'),IOPORT_IRQ_PIN5),output,NULL);
    unsigned char seen[256]={0};
    while(mcu->cycle<40000000&&mcu->state!=cpu_Crashed){
        avr_run(mcu);
        seen[mcu->data[0x48]]=1; // ATmega328P OCR0B, D5 PWM compare register
    }
    printf("{\"edges\":%d,\"level\":%d,\"cycles\":%llu,\"changes\":[",edges,last,(unsigned long long)mcu->cycle);
    for(int i=0;i<count;i++)printf("%s[%.6f,%d]",i?",":"",changes[i],levels[i]);
    printf("],\"pwm_values\":[");int n=0;
    for(int i=0;i<256;i++)if(seen[i])printf("%s%d",n++?",":"",i);
    printf("]}\n");int ok=mcu->state!=cpu_Crashed;avr_terminate(mcu);return ok?0:5;
}
