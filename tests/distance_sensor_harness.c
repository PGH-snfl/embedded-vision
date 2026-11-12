/* Test harness: run AVR instructions and model a single HC-SR04 echo pin. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "sim_avr.h"
#include "sim_elf.h"
#include "sim_io.h"
#include "sim_cycle_timers.h"
#include "avr_ioport.h"
#include "avr_uart.h"

static avr_t *mcu;
static avr_irq_t *echo_pin;
static unsigned distance_cm;
static unsigned trigger_previous;
static unsigned led_value;

static avr_cycle_count_t echo_low(struct avr_t *avr, avr_cycle_count_t when, void *param) {
    (void)avr; (void)when; (void)param; avr_raise_irq(echo_pin, 0); return 0;
}
static avr_cycle_count_t echo_high(struct avr_t *avr, avr_cycle_count_t when, void *param) {
    (void)when; (void)param;
    avr_raise_irq(echo_pin, 1);
    avr_cycle_timer_register_usec(avr, distance_cm * 20000UL / 343UL, echo_low, NULL);
    return 0;
}
static void trigger(struct avr_irq_t *irq, uint32_t value, void *param) {
    (void)irq; (void)param;
    unsigned high = !!(value & 1);
    if (trigger_previous && !high && distance_cm) avr_cycle_timer_register_usec(mcu, 600, echo_high, NULL);
    trigger_previous = high;
}
static void led(struct avr_irq_t *irq, uint32_t value, void *param) {
    (void)irq; (void)param; led_value = !!(value & 1);
}
static void uart(struct avr_irq_t *irq, uint32_t value, void *param) {
    (void)irq; (void)param; putchar(value & 255);
}
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    distance_cm = (unsigned)strtoul(argv[2], NULL, 10);
    elf_firmware_t firmware = {0}; if (elf_read_firmware(argv[1], &firmware)) return 3;
    mcu = avr_make_mcu_by_name("atmega328p"); if (!mcu || avr_init(mcu)) return 4;
    mcu->frequency = 16000000; mcu->vcc = mcu->avcc = mcu->aref = 5000;
    avr_load_firmware(mcu, &firmware);
    uint32_t flags = 0; avr_ioctl(mcu, AVR_IOCTL_UART_SET_FLAGS('0'), &flags);
    echo_pin = avr_io_getirq(mcu, AVR_IOCTL_IOPORT_GETIRQ('D'), IOPORT_IRQ_PIN6);
    avr_raise_irq(echo_pin, 0);
    avr_irq_register_notify(avr_io_getirq(mcu, AVR_IOCTL_IOPORT_GETIRQ('D'), IOPORT_IRQ_PIN7), trigger, NULL);
    avr_irq_register_notify(avr_io_getirq(mcu, AVR_IOCTL_IOPORT_GETIRQ('B'), IOPORT_IRQ_PIN0), led, NULL);
    avr_irq_register_notify(avr_io_getirq(mcu, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUTPUT), uart, NULL);
    while (mcu->cycle < 16000000 && mcu->state != cpu_Done && mcu->state != cpu_Crashed) avr_run(mcu);
    printf("\nLED=%u\n", led_value);
    int crashed = mcu->state == cpu_Crashed; avr_terminate(mcu); return crashed ? 5 : 0;
}
