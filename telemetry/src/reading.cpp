#include "reading.hpp"

#include <cstdio>
#include <ctime>

std::string format_timestamp(std::chrono::system_clock::time_point tp) {
    using namespace std::chrono;
    std::time_t secs = system_clock::to_time_t(tp);
    long millis = static_cast<long>(
        duration_cast<milliseconds>(tp.time_since_epoch()).count() % 1000);
    if (millis < 0) {
        millis += 1000;  // timestamps before 1970; not expected, but be correct
    }

    std::tm utc{};
    gmtime_r(&secs, &utc);

    char buf[64];
    std::snprintf(buf, sizeof buf, "%04d-%02d-%02dT%02d:%02d:%02d.%03ldZ",
                  utc.tm_year + 1900, utc.tm_mon + 1, utc.tm_mday,
                  utc.tm_hour, utc.tm_min, utc.tm_sec, millis);
    return buf;
}

std::string to_json(const Reading &r) {
    char buf[256];
    std::snprintf(buf, sizeof buf,
                  "{\"timestamp\":\"%s\",\"bus_voltage_v\":%.4f,\"shunt_voltage_mv\":%.3f,"
                  "\"current_ma\":%.2f,\"power_mw\":%.2f,\"soc_pct\":%.3f}",
                  format_timestamp(r.timestamp).c_str(), r.bus_voltage_v,
                  r.shunt_voltage_mv, r.current_ma, r.power_mw, r.soc_pct);
    return buf;
}
