/*
 * ina219.h - Minimal C99 driver for the TI INA219 current/voltage/power sensor.
 *
 * The driver talks to the chip through the Linux i2c-dev interface
 * (/dev/i2c-N) using plain open/ioctl/read/write. No third-party libraries.
 *
 * Two layers:
 *   1. Pure math (ina219_calc_*, ina219_*_raw_to_*): converts raw register
 *      values to physical units. No I/O, so it is unit-tested without hardware.
 *   2. Device I/O (ina219_init, ina219_read_*): reads/writes the registers.
 *
 * A mock backend is built in: pass INA219_MOCK_BUS as the bus path and the
 * driver returns plausible fake readings instead of touching hardware.
 * Mock readings go through the same raw->unit conversion as real ones.
 *
 * All functions that touch the device return 0 on success and -1 on error.
 */
#ifndef INA219_H
#define INA219_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- Register map (datasheet section 8.6) ------------------------------ */
#define INA219_REG_CONFIG      0x00 /* configuration                    */
#define INA219_REG_SHUNT       0x01 /* shunt voltage (signed, 10 uV/LSB) */
#define INA219_REG_BUS         0x02 /* bus voltage (4 mV/LSB, bits 15:3) */
#define INA219_REG_POWER       0x03 /* power (unsigned, 20 * current LSB) */
#define INA219_REG_CURRENT     0x04 /* current (signed, current LSB)    */
#define INA219_REG_CALIBRATION 0x05 /* calibration                      */

#define INA219_DEFAULT_ADDR 0x40
#define INA219_DEFAULT_BUS  "/dev/i2c-1"
#define INA219_MOCK_BUS     "mock"

/*
 * Configuration register value used by ina219_init():
 *   BRNG  = 0    -> 16 V bus range (a 1-cell Li-ion is at most 4.2 V)
 *   PG    = 11   -> /8 gain, +/-320 mV shunt range (3.2 A with 0.1 ohm)
 *   BADC  = 0011 -> 12-bit bus ADC, 532 us conversion
 *   SADC  = 0011 -> 12-bit shunt ADC, 532 us conversion
 *   MODE  = 111  -> shunt and bus, continuous
 * = 0b0001_1001_1001_1111 = 0x199F
 */
#define INA219_CONFIG_16V_320MV 0x199F

/* Device handle. Treat the fields as read-only outside the library. */
typedef struct {
    int fd;               /* i2c-dev file descriptor, -1 when closed or mock */
    int mock;             /* 1 when using the built-in mock backend          */
    double shunt_ohms;    /* shunt resistor value                            */
    double current_lsb_a; /* amps per bit of the CURRENT register            */
    uint16_t calibration; /* value written to the CALIBRATION register       */
    double mock_start_s;  /* monotonic time at init; drives the mock signal  */
} ina219_t;

/* ---- Pure math (no I/O) -------------------------------------------------- */

/* Combine two bytes received MSB-first into a 16-bit value (chip is big-endian). */
uint16_t ina219_be16_decode(const uint8_t bytes[2]);

/* Split a 16-bit value into two bytes, MSB first, ready to send to the chip. */
void ina219_be16_encode(uint16_t value, uint8_t bytes[2]);

/*
 * Calibration value (datasheet eq. 1 and 2):
 *   Current_LSB = Max_Expected_Current / 2^15
 *   Cal         = trunc(0.04096 / (Current_LSB * R_shunt))
 * Returns 0 if the inputs are invalid or the result does not fit in 16 bits
 * (bit 0 of the register is unused, so the value is also kept even).
 */
uint16_t ina219_calc_calibration(double shunt_ohms, double max_current_a);

/*
 * Effective current LSB after the calibration value was truncated:
 *   Current_LSB = 0.04096 / (Cal * R_shunt)
 * Using this (instead of Max/2^15) keeps readings exact for the value that
 * is actually in the chip.
 */
double ina219_calc_current_lsb(uint16_t calibration, double shunt_ohms);

/* SHUNT register -> millivolts. Two's complement, LSB = 10 uV. */
double ina219_shunt_raw_to_mv(uint16_t raw);

/* BUS register -> volts. Value is in bits 15:3, LSB = 4 mV. */
double ina219_bus_raw_to_v(uint16_t raw);

/* 1 if the BUS register's math-overflow flag (bit 0) is set. */
int ina219_bus_overflow(uint16_t raw);

/* CURRENT register -> milliamps. Two's complement, LSB = current_lsb_a. */
double ina219_current_raw_to_ma(uint16_t raw, double current_lsb_a);

/* POWER register -> milliwatts. Unsigned, LSB = 20 * current_lsb_a (eq. 3). */
double ina219_power_raw_to_mw(uint16_t raw, double current_lsb_a);

/* ---- Device I/O ---------------------------------------------------------- */

/*
 * Open the bus, then write the configuration and calibration registers.
 *   bus_path      e.g. "/dev/i2c-1", or INA219_MOCK_BUS for fake readings
 *   addr          7-bit I2C address, usually 0x40
 *   shunt_ohms    0.1 on common breakout boards
 *   max_current_a largest current you expect, e.g. 2.0
 */
int ina219_init(ina219_t *dev, const char *bus_path, uint8_t addr,
                double shunt_ohms, double max_current_a);

int ina219_read_bus_voltage(ina219_t *dev, double *volts);
int ina219_read_shunt_voltage(ina219_t *dev, double *millivolts);
int ina219_read_current(ina219_t *dev, double *milliamps);
int ina219_read_power(ina219_t *dev, double *milliwatts);

/* Low-level register access, exposed for debugging and tests. */
int ina219_read_register(ina219_t *dev, uint8_t reg, uint16_t *value);
int ina219_write_register(ina219_t *dev, uint8_t reg, uint16_t value);

/* Close the bus. Safe to call more than once. */
void ina219_close(ina219_t *dev);

#ifdef __cplusplus
}
#endif

#endif /* INA219_H */
