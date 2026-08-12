#include <gtest/gtest.h>

#include "reading.hpp"

using namespace std::chrono;

TEST(Reading, TimestampIsIsoUtcWithMillis) {
    // 2026-10-28T17:36:01.123Z
    system_clock::time_point tp{seconds{1793208961} + milliseconds{123}};
    EXPECT_EQ(format_timestamp(tp), "2026-10-28T17:36:01.123Z");
}

TEST(Reading, JsonHasAllFieldsInOrder) {
    Reading r;
    r.timestamp = system_clock::time_point{seconds{0}};
    r.bus_voltage_v = 3.9124;
    r.shunt_voltage_mv = 38.21;
    r.current_ma = 382.1;
    r.power_mw = 1494.0;
    r.soc_pct = 97.425;
    EXPECT_EQ(to_json(r),
              "{\"timestamp\":\"1970-01-01T00:00:00.000Z\",\"bus_voltage_v\":3.9124,"
              "\"shunt_voltage_mv\":38.210,\"current_ma\":382.10,\"power_mw\":1494.00,"
              "\"soc_pct\":97.425}");
}

TEST(Reading, NegativeCurrentFormats) {
    Reading r;
    r.timestamp = system_clock::time_point{seconds{0}};
    r.current_ma = -12.5;
    EXPECT_NE(to_json(r).find("\"current_ma\":-12.50"), std::string::npos);
}
