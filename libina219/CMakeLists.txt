# libina219 - static C99 library for the INA219 sensor
add_library(ina219 STATIC
    src/ina219.c
    src/ina219_math.c
)
target_include_directories(ina219 PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
set_target_properties(ina219 PROPERTIES C_STANDARD 99 C_STANDARD_REQUIRED ON)
target_compile_options(ina219 PRIVATE -Wall -Wextra)

# libm for floor/fmod/lround/sin
find_library(MATH_LIBRARY m)
if(MATH_LIBRARY)
    target_link_libraries(ina219 PUBLIC ${MATH_LIBRARY})
endif()

# Small command-line tool: prints one reading. Handy for checking wiring.
add_executable(ina219_read tools/ina219_read.c)
target_link_libraries(ina219_read PRIVATE ina219)
set_target_properties(ina219_read PROPERTIES C_STANDARD 99)

if(BUILD_TESTS)
    add_executable(ina219_tests tests/test_ina219_math.cpp tests/test_ina219_mock.cpp)
    target_link_libraries(ina219_tests PRIVATE ina219 GTest::gtest_main)
    gtest_discover_tests(ina219_tests)
endif()
