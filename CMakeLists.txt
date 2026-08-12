cmake_minimum_required(VERSION 3.16)
project(battery_telemetry LANGUAGES C CXX)

# BUILD_TESTS: GoogleTest suites (no hardware or MQTT broker needed)
# BUILD_TELEMETRY_APP: the telemetry executable (needs libmosquitto-dev)
option(BUILD_TESTS "Build GoogleTest unit tests" ON)
option(BUILD_TELEMETRY_APP "Build the telemetry executable (needs libmosquitto)" ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

if(BUILD_TESTS)
    include(FetchContent)
    FetchContent_Declare(
        googletest
        GIT_REPOSITORY https://github.com/google/googletest.git
        GIT_TAG        v1.15.2
        GIT_SHALLOW    TRUE
    )
    set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)
    include(GoogleTest)
    enable_testing()
endif()

add_subdirectory(libina219)
add_subdirectory(telemetry)
