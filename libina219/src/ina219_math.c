/*
 * ina219_math.c - Pure conversion and calibration math for the INA219.
 * Nothing in this file does I/O, so it can be unit-tested anywhere.
 * Equation numbers refer to the TI INA219 datasheet (SBOS448), section 8.5.
 */
#include "ina219.h"

#include <math.h>

/* Fixed scaling constant from the datasheet calibration equation. */
#define INA219_CAL_CONSTANT 0.04096

uint16_t ina219_be16_decode(const uint8_t bytes[2])
{
    return (uint16_t)(((uint16_t)bytes[0] << 8) | bytes[1]);
}

void ina219_be16_encode(uint16_t value, uint8_t bytes[2])
{
    bytes[0] = (uint8_t)(value >> 8);
    bytes[1] = (uint8_t)(value & 0xFF);
}

uint16_t ina219_calc_calibration(double shunt_ohms, double max_current_a)
{
    if (shunt_ohms <= 0.0 || max_current_a <= 0.0) {
        return 0;
    }

    /* Eq. 2: Current_LSB = Max_Expected_I / 2^15 */
    double current_lsb = max_current_a / 32768.0;

    /* Eq. 1: Cal = trunc(0.04096 / (Current_LSB * R_shunt)) */
    double cal = floor(INA219_CAL_CONSTANT / (current_lsb * shunt_ohms));
    if (cal < 1.0 || cal > 65534.0) {
        return 0;
    }

    /* Bit 0 of the calibration register is read-only and always 0. */
    return (uint16_t)((uint16_t)cal & 0xFFFE);
}

double ina219_calc_current_lsb(uint16_t calibration, double shunt_ohms)
{
    if (calibration == 0 || shunt_ohms <= 0.0) {
        return 0.0;
    }
    /* Eq. 1 solved for Current_LSB, using the value actually programmed. */
    return INA219_CAL_CONSTANT / ((double)calibration * shunt_ohms);
}

double ina219_shunt_raw_to_mv(uint16_t raw)
{
    /* Two's complement; with PGA /8 the sign extends through bit 15. */
    int16_t signed_raw = (int16_t)raw;
    return signed_raw * 0.01; /* 10 uV per bit = 0.01 mV */
}

double ina219_bus_raw_to_v(uint16_t raw)
{
    /* Bits 15:3 hold the reading; bit 1 = CNVR, bit 0 = OVF. */
    return (double)(raw >> 3) * 0.004; /* 4 mV per bit */
}

int ina219_bus_overflow(uint16_t raw)
{
    return (raw & 0x0001) ? 1 : 0;
}

double ina219_current_raw_to_ma(uint16_t raw, double current_lsb_a)
{
    int16_t signed_raw = (int16_t)raw;
    return signed_raw * current_lsb_a * 1000.0;
}

double ina219_power_raw_to_mw(uint16_t raw, double current_lsb_a)
{
    /* Eq. 3: Power_LSB = 20 * Current_LSB */
    return (double)raw * 20.0 * current_lsb_a * 1000.0;
}
