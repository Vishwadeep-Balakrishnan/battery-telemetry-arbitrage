// reading.hpp - one sensor sample and its JSON form.
#pragma once

#include <chrono>
#include <string>

struct Reading {
    std::chrono::system_clock::time_point timestamp;
    double bus_voltage_v = 0.0;
    double shunt_voltage_mv = 0.0;
    double current_ma = 0.0;
    double power_mw = 0.0;
    double soc_pct = 0.0;
};

// ISO 8601 UTC with milliseconds, e.g. "2026-10-28T17:36:01.123Z".
std::string format_timestamp(std::chrono::system_clock::time_point tp);

// The MQTT payload:
// {"timestamp":"...","bus_voltage_v":3.912,"shunt_voltage_mv":38.21,
//  "current_ma":382.1,"power_mw":1494.0,"soc_pct":97.42}
std::string to_json(const Reading &r);
