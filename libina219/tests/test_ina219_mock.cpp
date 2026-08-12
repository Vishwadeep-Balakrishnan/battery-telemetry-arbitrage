// Tests the device API end to end against the built-in mock backend.
#include <gtest/gtest.h>

#include <cmath>

#include "ina219.h"

TEST(Ina219Mock, InitAndReadPlausibleValues) {
    ina219_t dev;
    ASSERT_EQ(ina219_init(&dev, INA219_MOCK_BUS, INA219_DEFAULT_ADDR, 0.1, 2.0), 0);
    EXPECT_EQ(dev.mock, 1);
    EXPECT_EQ(dev.calibration, 6710);

    double bus_v = 0, shunt_mv = 0, current_ma = 0, power_mw = 0;
    ASSERT_EQ(ina219_read_bus_voltage(&dev, &bus_v), 0);
    ASSERT_EQ(ina219_read_shunt_voltage(&dev, &shunt_mv), 0);
    ASSERT_EQ(ina219_read_current(&dev, &current_ma), 0);
    ASSERT_EQ(ina219_read_power(&dev, &power_mw), 0);

    // Mock starts with the load on: about 4.1 V across ~10.2 ohm.
    EXPECT_GT(bus_v, 3.4);
    EXPECT_LT(bus_v, 4.2);
    EXPECT_GT(current_ma, 300.0);
    EXPECT_LT(current_ma, 450.0);
    // Shunt voltage and current must agree through Ohm's law (0.1 ohm).
    EXPECT_NEAR(shunt_mv / 0.1, current_ma, 5.0);
    // Power ~= V * I (within the 2 mW power LSB plus rounding).
    EXPECT_NEAR(power_mw, bus_v * current_ma, 15.0);

    ina219_close(&dev);
    ina219_close(&dev);  // closing twice is safe
}

TEST(Ina219Mock, CalibrationRegisterReadsBack) {
    ina219_t dev;
    ASSERT_EQ(ina219_init(&dev, INA219_MOCK_BUS, INA219_DEFAULT_ADDR, 0.1, 2.0), 0);
    uint16_t value = 0;
    ASSERT_EQ(ina219_read_register(&dev, INA219_REG_CALIBRATION, &value), 0);
    EXPECT_EQ(value, dev.calibration);
    ina219_close(&dev);
}

TEST(Ina219Init, RejectsBadShunt) {
    ina219_t dev;
    EXPECT_EQ(ina219_init(&dev, INA219_MOCK_BUS, INA219_DEFAULT_ADDR, 0.0, 2.0), -1);
}

TEST(Ina219Init, MissingBusFails) {
    ina219_t dev;
    EXPECT_EQ(ina219_init(&dev, "/dev/i2c-does-not-exist", INA219_DEFAULT_ADDR, 0.1, 2.0), -1);
    EXPECT_EQ(dev.fd, -1);
}
