// config.hpp - command-line configuration for the telemetry program.
#pragma once

#include <string>

struct Config {
    // MQTT
    std::string host = "localhost";
    int port = 1883;
    std::string topic = "battery/telemetry";
    std::string client_id = "battery-telemetry";

    // Sampling and battery
    double rate_hz = 10.0;
    double capacity_mah = 2500.0;
    double initial_soc_pct = 100.0;

    // Sensor
    bool mock = false;
    std::string i2c_bus = "/dev/i2c-1";
    int i2c_address = 0x40;
    double shunt_ohms = 0.1;
    double max_current_a = 2.0;
};

// Parse argv into cfg. Returns false and fills `error` on bad input.
// Sets `show_help` when --help is given.
bool parse_args(int argc, char **argv, Config &cfg, bool &show_help, std::string &error);

// Text printed for --help.
std::string usage_text(const char *program);
