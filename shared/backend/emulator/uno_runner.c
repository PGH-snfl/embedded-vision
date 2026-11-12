// SPDX-License-Identifier: GPL-3.0-or-later
// Bounded headless simavr harness. Executes compiled AVR instructions, not Arduino mocks.
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "sim_avr.h"
#include "sim_elf.h"
#include "avr_adc.h"
#include "avr_uart.h"
#include "sim_io.h"
static avr_t *mcu;
static unsigned nominal_mv;
static int steps;
static unsigned adc_count;
static double millis_now(void) { return (double)mcu->cycle * 1000.0 / mcu->frequency; }
static void adc_trigger(struct avr_irq_t *irq, uint32_t value, void *param) {
    (void)irq; (void)param;
    avr_adc_mux_t mux = {0};
    memcpy(&mux, &value, sizeof(value));
    unsigned mv = nominal_mv;
    if (steps) mv = millis_now() < 500 ? 1250 : millis_now() < 1000 ? 2500 : 3750;
    avr_raise_irq(avr_io_getirq(mcu, AVR_IOCTL_ADC_GETIRQ, ADC_IRQ_ADC0), mv);
    printf("{\"event\":\"adc\",\"ms\":%.6f,\"channel\":%u,\"mv\":%u}\n",millis_now(),(unsigned)mux.src,mv);
    adc_count++;
}
static void uart_output(struct avr_irq_t *irq, uint32_t value, void *param) {
    (void)irq; (void)param;
    printf("{\"event\":\"uart\",\"ms\":%.6f,\"byte\":%u}\n",millis_now(),value & 255);
}
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    char *end; long mv=strtol(argv[2],&end,10);
    if (*end || mv<0 || mv>5000) return 2;
    if (strcmp(argv[3],"circuit") && strcmp(argv[3],"input_steps")) return 2;
    nominal_mv=(unsigned)mv; steps=!strcmp(argv[3],"input_steps");
    elf_firmware_t firmware={0};
    if (elf_read_firmware(argv[1],&firmware)) return 3;
    mcu=avr_make_mcu_by_name("atmega328p");
    if (!mcu || avr_init(mcu)) return 4;
    mcu->frequency=16000000; mcu->vcc=mcu->avcc=mcu->aref=5000;
    avr_load_firmware(mcu,&firmware);
    uint32_t flags=0;
    avr_ioctl(mcu,AVR_IOCTL_UART_SET_FLAGS('0'),&flags);
    avr_irq_register_notify(avr_io_getirq(mcu,AVR_IOCTL_UART_GETIRQ('0'),UART_IRQ_OUTPUT),uart_output,NULL);
    avr_irq_register_notify(avr_io_getirq(mcu,AVR_IOCTL_ADC_GETIRQ,ADC_IRQ_OUT_TRIGGER),adc_trigger,NULL);
    const avr_cycle_count_t limit=24000000; // 1.5 virtual seconds, fixed resource bound
    while (mcu->cycle<limit && mcu->state!=cpu_Done && mcu->state!=cpu_Crashed) avr_run(mcu);
    printf("{\"event\":\"complete\",\"ms\":%.6f,\"cycles\":%llu,\"adc_count\":%u,\"crashed\":%s}\n",millis_now(),(unsigned long long)mcu->cycle,adc_count,mcu->state==cpu_Crashed?"true":"false");
    int ok=mcu->cycle>=limit && mcu->state!=cpu_Crashed;
    avr_terminate(mcu);return ok?0:5;
}
