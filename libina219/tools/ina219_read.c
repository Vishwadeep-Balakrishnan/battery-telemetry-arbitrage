/*
 * ina219_read - print one INA219 reading. Use it to check the wiring before
 * starting the telemetry service.
 *
 *   ./ina219_read             reads /dev/i2c-1, address 0x40
 *   ./ina219_read mock        uses the mock backend
 *   ./ina219_read /dev/i2c-1 0x41
 */
#include "ina219.h"

#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    const char *bus = argc > 1 ? argv[1] : INA219_DEFAULT_BUS;
    uint8_t addr = argc > 2 ? (uint8_t)strtol(argv[2], NULL, 0) : INA219_DEFAULT_ADDR;

    ina219_t dev;
    if (ina219_init(&dev, bus, addr, 0.1, 2.0) != 0) {
        return 1;
    }

    double bus_v, shunt_mv, current_ma, power_mw;
    if (ina219_read_bus_voltage(&dev, &bus_v) != 0 ||
        ina219_read_shunt_voltage(&dev, &shunt_mv) != 0 ||
        ina219_read_current(&dev, &current_ma) != 0 ||
        ina219_read_power(&dev, &power_mw) != 0) {
        ina219_close(&dev);
        return 1;
    }

    printf("bus voltage   : %.3f V\n", bus_v);
    printf("shunt voltage : %.2f mV\n", shunt_mv);
    printf("current       : %.1f mA\n", current_ma);
    printf("power         : %.1f mW\n", power_mw);
    printf("calibration   : %u (current LSB %.3f uA)\n",
           dev.calibration, dev.current_lsb_a * 1e6);

    ina219_close(&dev);
    return 0;
}
