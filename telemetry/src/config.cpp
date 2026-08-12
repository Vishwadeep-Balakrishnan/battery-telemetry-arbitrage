#include "config.hpp"

#include <stdexcept>

namespace {

// Convert a flag's value, turning conversion errors into readable messages.
bool to_double(const std::string &flag, const std::string &text, double &out, std::string &error) {
    try {
        std::size_t used = 0;
        out = std::stod(text, &used);
        if (used != text.size()) {
            throw std::invalid_argument("trailing characters");
        }
        return true;
    } catch (const std::exception &) {
        error = flag + ": expected a number, got '" + text + "'";
        return false;
    }
}

bool to_int(const std::string &flag, const std::string &text, int &out, std::string &error) {
    try {
        std::size_t used = 0;
        out = std::stoi(text, &used, 0);  // base 0 accepts "0x40"
        if (used != text.size()) {
            throw std::invalid_argument("trailing characters");
        }
        return true;
    } catch (const std::exception &) {
        error = flag + ": expected an integer, got '" + text + "'";
        return false;
    }
}

bool check_ranges(const Config &cfg, std::string &error) {
    if (cfg.port < 1 || cfg.port > 65535) {
        error = "--port must be 1..65535";
    } else if (cfg.rate_hz <= 0.0 || cfg.rate_hz > 200.0) {
        error = "--rate-hz must be in (0, 200]";
    } else if (cfg.capacity_mah <= 0.0) {
        error = "--capacity-mah must be positive";
    } else if (cfg.initial_soc_pct < 0.0 || cfg.initial_soc_pct > 100.0) {
        error = "--initial-soc must be 0..100";
    } else if (cfg.i2c_address < 0x03 || cfg.i2c_address > 0x77) {
        error = "--address must be a 7-bit I2C address (0x03..0x77)";
    } else if (cfg.shunt_ohms <= 0.0 || cfg.max_current_a <= 0.0) {
        error = "--shunt-ohms and --max-current must be positive";
    } else {
        return true;
    }
    return false;
}

}  // namespace

bool parse_args(int argc, char **argv, Config &cfg, bool &show_help, std::string &error) {
    show_help = false;
    for (int i = 1; i < argc; ++i) {
        std::string flag = argv[i];

        // Flags without a value
        if (flag == "--help" || flag == "-h") {
            show_help = true;
            return true;
        }
        if (flag == "--mock") {
            cfg.mock = true;
            continue;
        }

        // Every other flag takes one value
        if (i + 1 >= argc) {
            error = flag + ": missing value";
            return false;
        }
        std::string value = argv[++i];
        bool ok = true;

        if (flag == "--host") cfg.host = value;
        else if (flag == "--port") ok = to_int(flag, value, cfg.port, error);
        else if (flag == "--topic") cfg.topic = value;
        else if (flag == "--client-id") cfg.client_id = value;
        else if (flag == "--rate-hz") ok = to_double(flag, value, cfg.rate_hz, error);
        else if (flag == "--capacity-mah") ok = to_double(flag, value, cfg.capacity_mah, error);
        else if (flag == "--initial-soc") ok = to_double(flag, value, cfg.initial_soc_pct, error);
        else if (flag == "--bus") cfg.i2c_bus = value;
        else if (flag == "--address") ok = to_int(flag, value, cfg.i2c_address, error);
        else if (flag == "--shunt-ohms") ok = to_double(flag, value, cfg.shunt_ohms, error);
        else if (flag == "--max-current") ok = to_double(flag, value, cfg.max_current_a, error);
        else {
            error = "unknown option: " + flag;
            return false;
        }
        if (!ok) {
            return false;
        }
    }
    return check_ranges(cfg, error);
}

std::string usage_text(const char *program) {
    return std::string("Usage: ") + program + " [options]\n"
        "\n"
        "MQTT:\n"
        "  --host HOST            broker host (default localhost)\n"
        "  --port PORT            broker port (default 1883)\n"
        "  --topic TOPIC          topic (default battery/telemetry)\n"
        "  --client-id ID         MQTT client id (default battery-telemetry)\n"
        "\n"
        "Sampling and battery:\n"
        "  --rate-hz HZ           sample rate (default 10)\n"
        "  --capacity-mah MAH     battery capacity for SoC (default 2500)\n"
        "  --initial-soc PCT      SoC at start, 0-100 (default 100)\n"
        "\n"
        "Sensor:\n"
        "  --mock                 fake readings, no hardware needed\n"
        "  --bus PATH             I2C bus device (default /dev/i2c-1)\n"
        "  --address ADDR         INA219 address (default 0x40)\n"
        "  --shunt-ohms OHMS      shunt resistor (default 0.1)\n"
        "  --max-current AMPS     expected max current for calibration (default 2.0)\n"
        "\n"
        "  -h, --help             show this help\n";
}
