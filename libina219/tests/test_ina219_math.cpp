// Unit tests for the pure INA219 math. No hardware needed.
#include <gtest/gtest.h>

#include "ina219.h"

TEST(Ina219Bytes, DecodesBigEndian) {
    const uint8_t bytes[2] = {0x12, 0x34};
    EXPECT_EQ(ina219_be16_decode(bytes), 0x1234);
}

TEST(Ina219Bytes, EncodeDecodeRoundTrip) {
    uint8_t bytes[2];
    ina219_be16_encode(0xBEEF, bytes);
    EXPECT_EQ(bytes[0], 0xBE);
    EXPECT_EQ(bytes[1], 0xEF);
    EXPECT_EQ(ina219_be16_decode(bytes), 0xBEEF);
}

TEST(Ina219Calibration, PointOneOhmTwoAmps) {
    // Current_LSB = 2 / 32768 = 61.035 uA; Cal = trunc(0.04096 / (61.035e-6 * 0.1)) = 6710
    EXPECT_EQ(ina219_calc_calibration(0.1, 2.0), 6710);
}

TEST(Ina219Calibration, RangeLimits) {
    // 0.1 A max at 0.1 ohm: Cal = 0.04096 / (3.0518e-6 * 0.1) = 134217, which
    // does not fit in 16 bits, so it is rejected.
    EXPECT_EQ(ina219_calc_calibration(0.1, 0.1), 0);
    // 3.2 A at 0.1 ohm: LSB = 97.66 uA -> Cal = 4194
    EXPECT_EQ(ina219_calc_calibration(0.1, 3.2), 4194);
}

TEST(Ina219Calibration, RejectsBadInput) {
    EXPECT_EQ(ina219_calc_calibration(0.0, 2.0), 0);
    EXPECT_EQ(ina219_calc_calibration(0.1, 0.0), 0);
    EXPECT_EQ(ina219_calc_calibration(-0.1, 2.0), 0);
}

TEST(Ina219Calibration, ResultIsEven) {
    // Bit 0 of the calibration register is unused.
    EXPECT_EQ(ina219_calc_calibration(0.1, 1.234) % 2, 0);
}

TEST(Ina219Calibration, EffectiveCurrentLsb) {
    double lsb = ina219_calc_current_lsb(4096, 0.1);
    EXPECT_NEAR(lsb, 100e-6, 1e-12);  // a round 100 uA/bit
    EXPECT_DOUBLE_EQ(ina219_calc_current_lsb(0, 0.1), 0.0);
}

TEST(Ina219Shunt, PositiveAndNegative) {
    EXPECT_NEAR(ina219_shunt_raw_to_mv(0x0000), 0.0, 1e-9);
    EXPECT_NEAR(ina219_shunt_raw_to_mv(4000), 40.0, 1e-9);        // 4000 * 10 uV
    EXPECT_NEAR(ina219_shunt_raw_to_mv(0x7D00), 320.0, 1e-9);     // full scale +
    EXPECT_NEAR(ina219_shunt_raw_to_mv(0x8300), -320.0, 1e-9);    // full scale -
    EXPECT_NEAR(ina219_shunt_raw_to_mv(0xFFFF), -0.01, 1e-9);
}

TEST(Ina219Bus, ShiftsOutStatusBits) {
    // 3.7 V -> 925 counts of 4 mV -> 925 << 3 = 7400, plus CNVR bit
    EXPECT_NEAR(ina219_bus_raw_to_v((925 << 3) | 0x2), 3.7, 1e-9);
    EXPECT_NEAR(ina219_bus_raw_to_v(0xFFF8), 32.764, 1e-9);  // 8191 * 4 mV
    EXPECT_EQ(ina219_bus_overflow((925 << 3) | 0x1), 1);
    EXPECT_EQ(ina219_bus_overflow((925 << 3) | 0x2), 0);
}

TEST(Ina219Current, SignedScaling) {
    const double lsb = 100e-6;  // 100 uA/bit
    EXPECT_NEAR(ina219_current_raw_to_ma(3700, lsb), 370.0, 1e-9);
    EXPECT_NEAR(ina219_current_raw_to_ma((uint16_t)-3700, lsb), -370.0, 1e-9);
}

TEST(Ina219Power, TwentyTimesCurrentLsb) {
    const double lsb = 100e-6;  // power LSB = 2 mW
    EXPECT_NEAR(ina219_power_raw_to_mw(685, lsb), 1370.0, 1e-9);
}
