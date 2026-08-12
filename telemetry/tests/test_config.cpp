#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "config.hpp"

namespace {
// Run parse_args on a list of strings.
bool parse(std::vector<std::string> args, Config &cfg, std::string &error) {
    args.insert(args.begin(), "battery_telemetry");
    std::vector<char *> argv;
    for (auto &a : args) {
        argv.push_back(a.data());
    }
    bool help = false;
    return parse_args(static_cast<int>(argv.size()), argv.data(), cfg, help, error);
}
}  // namespace

TEST(Config, Defaults) {
    Config cfg;
    std::string error;
    ASSERT_TRUE(parse({}, cfg, error));
    EXPECT_EQ(cfg.host, "localhost");
    EXPECT_EQ(cfg.port, 1883);
    EXPECT_EQ(cfg.topic, "battery/telemetry");
    EXPECT_DOUBLE_EQ(cfg.rate_hz, 10.0);
    EXPECT_FALSE(cfg.mock);
    EXPECT_EQ(cfg.i2c_address, 0x40);
}

TEST(Config, ParsesAllFlags) {
    Config cfg;
    std::string error;
    ASSERT_TRUE(parse({"--host", "pi.local", "--port", "1884", "--rate-hz", "5",
                       "--capacity-mah", "3000", "--initial-soc", "80", "--mock",
                       "--address", "0x41", "--topic", "lab/battery"},
                      cfg, error))
        << error;
    EXPECT_EQ(cfg.host, "pi.local");
    EXPECT_EQ(cfg.port, 1884);
    EXPECT_DOUBLE_EQ(cfg.rate_hz, 5.0);
    EXPECT_DOUBLE_EQ(cfg.capacity_mah, 3000.0);
    EXPECT_DOUBLE_EQ(cfg.initial_soc_pct, 80.0);
    EXPECT_TRUE(cfg.mock);
    EXPECT_EQ(cfg.i2c_address, 0x41);
    EXPECT_EQ(cfg.topic, "lab/battery");
}

TEST(Config, RejectsBadValues) {
    Config cfg;
    std::string error;
    EXPECT_FALSE(parse({"--rate-hz", "fast"}, cfg, error));
    EXPECT_FALSE(parse({"--port", "99999"}, cfg, error));
    EXPECT_FALSE(parse({"--initial-soc", "120"}, cfg, error));
    EXPECT_FALSE(parse({"--host"}, cfg, error));
    EXPECT_FALSE(parse({"--nope", "1"}, cfg, error));
}

TEST(Config, HelpFlag) {
    Config cfg;
    std::vector<std::string> args = {"prog", "--help"};
    std::vector<char *> argv;
    for (auto &a : args) argv.push_back(a.data());
    bool help = false;
    std::string error;
    EXPECT_TRUE(parse_args(2, argv.data(), cfg, help, error));
    EXPECT_TRUE(help);
    EXPECT_NE(usage_text("prog").find("--mock"), std::string::npos);
}
