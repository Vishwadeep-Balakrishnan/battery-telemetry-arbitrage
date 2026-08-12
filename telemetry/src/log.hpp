// log.hpp - one-line, thread-safe logging to stderr (journald picks it up).
#pragma once

#include <iostream>
#include <mutex>
#include <string>

inline std::mutex &log_mutex() {
    static std::mutex m;
    return m;
}

inline void log_info(const std::string &msg) {
    std::lock_guard<std::mutex> lock(log_mutex());
    std::cerr << "[info] " << msg << std::endl;
}

inline void log_error(const std::string &msg) {
    std::lock_guard<std::mutex> lock(log_mutex());
    std::cerr << "[error] " << msg << std::endl;
}
