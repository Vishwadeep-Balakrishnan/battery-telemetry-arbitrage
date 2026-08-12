// main.cpp - battery telemetry: INA219 -> queue -> MQTT.
//
// Threads:
//   sensor thread    samples the INA219 every 1/rate_hz seconds, updates the
//                    SoC estimate, and pushes a Reading onto the queue.
//   publisher thread pops Readings, turns them into JSON, publishes to MQTT.
//   main thread      waits for SIGINT/SIGTERM, then shuts the others down.
#include <atomic>
#include <chrono>
#include <csignal>
#include <iostream>
#include <string>
#include <thread>

#include "config.hpp"
#include "ina219.h"
#include "log.hpp"
#include "mqtt_publisher.hpp"
#include "reading.hpp"
#include "soc_estimator.hpp"
#include "thread_safe_queue.hpp"

#include <mosquitto.h>

namespace {

using Clock = std::chrono::steady_clock;

std::atomic<bool> g_stop{false};

void handle_signal(int) { g_stop = true; }

// Read all four values. Returns false if any I2C transfer failed.
bool read_sensor(ina219_t &dev, Reading &r) {
    return ina219_read_bus_voltage(&dev, &r.bus_voltage_v) == 0 &&
           ina219_read_shunt_voltage(&dev, &r.shunt_voltage_mv) == 0 &&
           ina219_read_current(&dev, &r.current_ma) == 0 &&
           ina219_read_power(&dev, &r.power_mw) == 0;
}

void sensor_loop(const Config &cfg, ina219_t &dev, ThreadSafeQueue<Reading> &queue) {
    SocEstimator soc(cfg.capacity_mah, cfg.initial_soc_pct);
    const auto period = std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double>(1.0 / cfg.rate_hz));

    auto next_tick = Clock::now();
    auto last_sample = Clock::time_point{};  // zero = no sample yet
    long failures_in_a_row = 0;

    while (!g_stop) {
        Reading r;
        r.timestamp = std::chrono::system_clock::now();
        auto now = Clock::now();

        if (read_sensor(dev, r)) {
            if (failures_in_a_row > 0) {
                log_info("sensor: reads recovered after " + std::to_string(failures_in_a_row) +
                         " failures");
            }
            failures_in_a_row = 0;

            double dt_s = last_sample == Clock::time_point{}
                              ? 0.0
                              : std::chrono::duration<double>(now - last_sample).count();
            last_sample = now;
            r.soc_pct = soc.update(r.current_ma, dt_s);
            queue.push(r);
        } else {
            // Don't crash on a bad read: log (not every time) and try again.
            if (failures_in_a_row % 50 == 0) {
                log_error("sensor: I2C read failed (" + std::to_string(failures_in_a_row + 1) +
                          " in a row), check wiring");
            }
            ++failures_in_a_row;
        }

        next_tick += period;
        if (next_tick < Clock::now()) {
            next_tick = Clock::now();  // fell behind; don't try to catch up
        }
        std::this_thread::sleep_until(next_tick);
    }
}

void publisher_loop(const Config &cfg, MqttPublisher &mqtt, ThreadSafeQueue<Reading> &queue) {
    while (auto reading = queue.pop()) {
        std::string payload = to_json(*reading);

        // Hold this message until the broker is back. Meanwhile the bounded
        // queue keeps the newest readings and drops the oldest.
        while (!mqtt.publish(cfg.topic, payload)) {
            if (g_stop) {
                return;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
        }
    }
}

}  // namespace

int main(int argc, char **argv) {
    Config cfg;
    bool show_help = false;
    std::string error;
    if (!parse_args(argc, argv, cfg, show_help, error)) {
        log_error(error);
        log_error("run with --help for usage");
        return 2;
    }
    if (show_help) {
        std::cout << usage_text(argv[0]);
        return 0;
    }

    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    ina219_t dev;
    const char *bus = cfg.mock ? INA219_MOCK_BUS : cfg.i2c_bus.c_str();
    if (ina219_init(&dev, bus, static_cast<uint8_t>(cfg.i2c_address), cfg.shunt_ohms,
                    cfg.max_current_a) != 0) {
        log_error("sensor: could not initialise INA219 (try --mock to run without hardware)");
        return 1;
    }
    log_info(std::string("sensor: ") + (cfg.mock ? "mock backend" : cfg.i2c_bus) + ", " +
             std::to_string(cfg.rate_hz) + " Hz, calibration " + std::to_string(dev.calibration));

    mosquitto_lib_init();
    int exit_code = 0;
    {
        MqttPublisher mqtt(cfg.host, cfg.port, cfg.client_id);
        if (!mqtt.start()) {
            exit_code = 1;
        } else {
            // About 10 minutes of readings at the default 10 Hz.
            ThreadSafeQueue<Reading> queue(6000);

            std::thread sensor([&] { sensor_loop(cfg, dev, queue); });
            std::thread publisher([&] { publisher_loop(cfg, mqtt, queue); });

            while (!g_stop) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
            log_info("shutting down");

            sensor.join();   // exits on its next tick
            queue.close();   // wakes the publisher
            publisher.join();
            if (queue.dropped() > 0) {
                log_info("dropped " + std::to_string(queue.dropped()) +
                         " readings while the broker was unreachable");
            }
            mqtt.stop();
        }
    }
    mosquitto_lib_cleanup();
    ina219_close(&dev);
    return exit_code;
}
