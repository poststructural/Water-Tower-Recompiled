# Host tests for the Archipelago bridge (Linux/macOS; no game build needed).
#   cmake -S tests/ap -B build-aptest && cmake --build build-aptest
#   ctest --test-dir build-aptest --output-on-failure
#   python tests/ap/run_live.py build-aptest/test_ap   # against a real server
cmake_minimum_required(VERSION 3.20)
project(ani_ap_tests C)
set(CMAKE_C_STANDARD 11)
set(AP ${CMAKE_CURRENT_SOURCE_DIR}/../../src/ap)
add_executable(test_ap test_ap.c ${AP}/ap_json.c ${AP}/ap_net.c ${AP}/ap_game.c ${AP}/ap_ui.c ${AP}/ap_names.c ${AP}/ap_font.c
               ${AP}/ap_ws_posix.c)
target_include_directories(test_ap PRIVATE ${AP} ${CMAKE_CURRENT_SOURCE_DIR}/../../tools/ngbrecomp/xboxrecomp/third_party/stb)
target_compile_options(test_ap PRIVATE -Wall -Wextra -Wno-unused-parameter -g
                       -fsanitize=address,undefined)
target_link_options(test_ap PRIVATE -fsanitize=address,undefined)
find_package(Threads REQUIRED)
target_link_libraries(test_ap PRIVATE Threads::Threads m)
enable_testing()
add_test(NAME ap_json COMMAND test_ap json)
add_test(NAME ap_game COMMAND test_ap game)
add_test(NAME ap_ui COMMAND test_ap ui)
add_test(NAME ap_font COMMAND test_ap font)
add_test(NAME ap_names COMMAND test_ap names ${CMAKE_CURRENT_BINARY_DIR}/names)
find_package(Python3 COMPONENTS Interpreter)
if(Python3_FOUND)
    add_test(NAME ap_catalog_header
             COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../../scripts/gen_ap_catalog.py --check)
endif()
