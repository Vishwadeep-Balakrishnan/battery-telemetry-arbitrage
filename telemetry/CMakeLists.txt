# Logic that doesn't need MQTT, so unit tests can link it without libmosquitto.
add_library(telemetry_core STATIC
    src/config.cpp
    src/reading.cpp
    src/soc_estimator.cpp
)
target_include_directories(telemetry_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_compile_options(telemetry_core PRIVATE -Wall -Wextra)

find_package(Threads REQUIRED)

if(BUILD_TELEMETRY_APP)
    # libmosquitto ships a pkg-config file (libmosquitto-dev on Debian/Raspberry Pi OS).
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(MOSQUITTO REQUIRED IMPORTED_TARGET libmosquitto)

    add_executable(battery_telemetry
        src/main.cpp
        src/mqtt_publisher.cpp
    )
    target_link_libraries(battery_telemetry PRIVATE
        telemetry_core ina219 PkgConfig::MOSQUITTO Threads::Threads)
    target_compile_options(battery_telemetry PRIVATE -Wall -Wextra)
    install(TARGETS battery_telemetry RUNTIME DESTINATION bin)
endif()

if(BUILD_TESTS)
    add_executable(telemetry_tests
        tests/test_queue.cpp
        tests/test_soc.cpp
        tests/test_reading.cpp
        tests/test_config.cpp
    )
    target_link_libraries(telemetry_tests PRIVATE telemetry_core GTest::gtest_main Threads::Threads)
    gtest_discover_tests(telemetry_tests)
endif()
