/*
 * ina219.c - Register-level I/O for the INA219 over Linux i2c-dev,
 * plus a mock backend that fabricates register values for testing.
 */
#define _POSIX_C_SOURCE 200809L

#include "ina219.h"

#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifdef __linux__
#include <linux/i2c-dev.h>
#include <sys/ioctl.h>
#endif

/* ---- Mock backend ------------------------------------------------------ */
/*
 * The mock simulates the hardware in the README: an 18650 cell feeding a
 * 10 ohm load through the 0.1 ohm shunt. The load switches on for 20 s and
 * off for 10 s, and the cell's open-circuit voltage sags from 4.10 V to
 * 3.50 V over an hour, then starts again. Values are turned into raw
 * register contents so that they pass through the real conversion code.
 */
#define MOCK_LOAD_OHMS     10.0
#define MOCK_CELL_R_OHMS   0.08
#define MOCK_PERIOD_S      30.0
#define MOCK_ON_S          20.0
#define MOCK_DRAIN_S       3600.0

static double monotonic_seconds(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static uint16_t mock_register(const ina219_t *dev, uint8_t reg)
{
    double t = monotonic_seconds() - dev->mock_start_s;
    double ocv = 4.10 - 0.60 * fmod(t, MOCK_DRAIN_S) / MOCK_DRAIN_S;
    int load_on = fmod(t, MOCK_PERIOD_S) < MOCK_ON_S;

    double amps = 0.0;
    if (load_on) {
        amps = ocv / (MOCK_LOAD_OHMS + dev->shunt_ohms + MOCK_CELL_R_OHMS);
        amps += 0.002 * sin(t * 7.0); /* a little ripple so charts move */
    }
    double bus_v = ocv - amps * (MOCK_CELL_R_OHMS + dev->shunt_ohms);
    double shunt_v = amps * dev->shunt_ohms;

    switch (reg) {
    case INA219_REG_CONFIG:
        return INA219_CONFIG_16V_320MV;
    case INA219_REG_SHUNT:
        return (uint16_t)(int16_t)lround(shunt_v / 10e-6);
    case INA219_REG_BUS:
        /* value in bits 15:3, CNVR (bit 1) set */
        return (uint16_t)((lround(bus_v / 0.004) << 3) | 0x2);
    case INA219_REG_CURRENT:
        return (uint16_t)(int16_t)lround(amps / dev->current_lsb_a);
    case INA219_REG_POWER:
        return (uint16_t)lround(amps * bus_v / (20.0 * dev->current_lsb_a));
    case INA219_REG_CALIBRATION:
        return dev->calibration;
    default:
        return 0;
    }
}

/* ---- Register access ------------------------------------------------------ */

int ina219_write_register(ina219_t *dev, uint8_t reg, uint16_t value)
{
    if (dev->mock) {
        return 0; /* nothing to write to */
    }
    /* Frame: register pointer, then the 16-bit value MSB first. */
    uint8_t buf[3];
    buf[0] = reg;
    ina219_be16_encode(value, &buf[1]);
    if (write(dev->fd, buf, sizeof buf) != (ssize_t)sizeof buf) {
        fprintf(stderr, "ina219: write reg 0x%02x failed: %s\n", reg, strerror(errno));
        return -1;
    }
    return 0;
}

int ina219_read_register(ina219_t *dev, uint8_t reg, uint16_t *value)
{
    if (dev->mock) {
        *value = mock_register(dev, reg);
        return 0;
    }
    /* Set the register pointer, then read two bytes (MSB first). */
    uint8_t buf[2];
    if (write(dev->fd, &reg, 1) != 1) {
        fprintf(stderr, "ina219: set pointer 0x%02x failed: %s\n", reg, strerror(errno));
        return -1;
    }
    if (read(dev->fd, buf, sizeof buf) != (ssize_t)sizeof buf) {
        fprintf(stderr, "ina219: read reg 0x%02x failed: %s\n", reg, strerror(errno));
        return -1;
    }
    *value = ina219_be16_decode(buf);
    return 0;
}

/* ---- Public API ----------------------------------------------------------- */

static int open_bus(ina219_t *dev, const char *bus_path, uint8_t addr)
{
#ifdef __linux__
    dev->fd = open(bus_path, O_RDWR);
    if (dev->fd < 0) {
        fprintf(stderr, "ina219: cannot open %s: %s\n", bus_path, strerror(errno));
        return -1;
    }
    /* Every following read/write on this fd goes to this 7-bit address. */
    if (ioctl(dev->fd, I2C_SLAVE, addr) < 0) {
        fprintf(stderr, "ina219: cannot select address 0x%02x: %s\n", addr, strerror(errno));
        close(dev->fd);
        dev->fd = -1;
        return -1;
    }
    return 0;
#else
    (void)addr;
    fprintf(stderr, "ina219: %s: real I2C needs Linux; use the mock bus\n", bus_path);
    return -1;
#endif
}

int ina219_init(ina219_t *dev, const char *bus_path, uint8_t addr,
                double shunt_ohms, double max_current_a)
{
    memset(dev, 0, sizeof *dev);
    dev->fd = -1;
    dev->shunt_ohms = shunt_ohms;
    dev->calibration = ina219_calc_calibration(shunt_ohms, max_current_a);
    dev->current_lsb_a = ina219_calc_current_lsb(dev->calibration, shunt_ohms);
    if (dev->calibration == 0) {
        fprintf(stderr, "ina219: invalid shunt (%g ohm) or max current (%g A)\n",
                shunt_ohms, max_current_a);
        return -1;
    }

    if (bus_path == NULL || strcmp(bus_path, INA219_MOCK_BUS) == 0) {
        dev->mock = 1;
        dev->mock_start_s = monotonic_seconds();
        return 0;
    }

    if (open_bus(dev, bus_path, addr) != 0) {
        return -1;
    }
    if (ina219_write_register(dev, INA219_REG_CONFIG, INA219_CONFIG_16V_320MV) != 0 ||
        ina219_write_register(dev, INA219_REG_CALIBRATION, dev->calibration) != 0) {
        ina219_close(dev);
        return -1;
    }
    return 0;
}

int ina219_read_bus_voltage(ina219_t *dev, double *volts)
{
    uint16_t raw;
    if (ina219_read_register(dev, INA219_REG_BUS, &raw) != 0) {
        return -1;
    }
    if (ina219_bus_overflow(raw)) {
        fprintf(stderr, "ina219: math overflow flag set; current/power invalid\n");
    }
    *volts = ina219_bus_raw_to_v(raw);
    return 0;
}

int ina219_read_shunt_voltage(ina219_t *dev, double *millivolts)
{
    uint16_t raw;
    if (ina219_read_register(dev, INA219_REG_SHUNT, &raw) != 0) {
        return -1;
    }
    *millivolts = ina219_shunt_raw_to_mv(raw);
    return 0;
}

int ina219_read_current(ina219_t *dev, double *milliamps)
{
    /*
     * The chip forgets its calibration after a brown-out reset, after which
     * CURRENT and POWER read 0. Re-writing it before each read is cheap and
     * makes the driver recover on its own.
     */
    uint16_t raw;
    if (ina219_write_register(dev, INA219_REG_CALIBRATION, dev->calibration) != 0 ||
        ina219_read_register(dev, INA219_REG_CURRENT, &raw) != 0) {
        return -1;
    }
    *milliamps = ina219_current_raw_to_ma(raw, dev->current_lsb_a);
    return 0;
}

int ina219_read_power(ina219_t *dev, double *milliwatts)
{
    uint16_t raw;
    if (ina219_read_register(dev, INA219_REG_POWER, &raw) != 0) {
        return -1;
    }
    *milliwatts = ina219_power_raw_to_mw(raw, dev->current_lsb_a);
    return 0;
}

void ina219_close(ina219_t *dev)
{
    if (dev->fd >= 0) {
        close(dev->fd);
        dev->fd = -1;
    }
}
