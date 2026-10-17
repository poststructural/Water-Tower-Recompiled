cmake_minimum_required(VERSION 3.20)

# ============================================================================
# Animaniacs: The Great Edgar Hunt - static recompilation, Vulkan runtime
#
# The same recompiled game, built against ngbrecomp's xboxrecomp fork
# (tools/ngbrecomp/xboxrecomp): xemu's NV2A model with its Vulkan renderer in
# place of the CPU pushbuffer rasteriser, and one virtual CPU for the guest's
# threads. Windows builds need llvm-mingw (see cmake/toolchains).
#
#   cmake -S vk -B build-vk -G Ninja \
#       -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/windows-llvm-mingw.cmake
#
# The generated code must come from the same toolkit's pipeline:
#   TK=tools/ngbrecomp/xboxrecomp scripts/regen.sh
# ============================================================================

project(animaniacs_vk C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

set(ANI_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/..)
add_compile_definitions(WIN32_LEAN_AND_MEAN NOMINMAX)

set(XBOXRECOMP_NV2A_VK ON CACHE BOOL "" FORCE)
set(XBOXRECOMP_SDL_BACKENDS ON CACHE BOOL "" FORCE)
set(XBOXRECOMP_WIN_VCPU ON CACHE BOOL "" FORCE)
set(XBOXRECOMP_DIR "${ANI_ROOT}/tools/ngbrecomp/xboxrecomp" CACHE PATH
    "Path to the xboxrecomp fork with nv2a_vk")
add_subdirectory(${XBOXRECOMP_DIR} ${CMAKE_BINARY_DIR}/xboxrecomp)

# nv2a_vk/shim/hw/xbox/nv2a is a git symlink to nv2a_vk/xemu. A Windows
# checkout without core.symlinks makes it a text file, and every
# "hw/xbox/nv2a/..." include fails. Recreate it as a directory junction in the
# build tree and put that on the include path after the shim.
if(WIN32 AND NOT IS_DIRECTORY ${XBOXRECOMP_DIR}/src/nv2a_vk/shim/hw/xbox/nv2a)
    set(_shim ${CMAKE_BINARY_DIR}/nv2a_shim/hw/xbox)
    file(MAKE_DIRECTORY ${_shim})
    if(NOT EXISTS ${_shim}/nv2a)
        file(TO_NATIVE_PATH ${_shim}/nv2a _link)
        file(TO_NATIVE_PATH ${XBOXRECOMP_DIR}/src/nv2a_vk/xemu _target)
        execute_process(COMMAND cmd /c mklink /J "${_link}" "${_target}"
                        OUTPUT_QUIET RESULT_VARIABLE _rc)
        if(NOT _rc EQUAL 0)
            message(FATAL_ERROR "could not create the nv2a include junction")
        endif()
    endif()
    target_include_directories(xbox_nv2a_vk PRIVATE ${CMAKE_BINARY_DIR}/nv2a_shim)
endif()

file(GLOB RECOMP_GEN_SOURCES CONFIGURE_DEPENDS "${ANI_ROOT}/src/recomp/gen/*.c")
if(NOT RECOMP_GEN_SOURCES)
    message(FATAL_ERROR "src/recomp/gen is empty: TK=tools/ngbrecomp/xboxrecomp scripts/regen.sh")
endif()

# The generated chunks get their own flags and never rebuild on a host change.
add_library(ani_gen OBJECT ${RECOMP_GEN_SOURCES})
target_include_directories(ani_gen PRIVATE
    ${ANI_ROOT}/src/recomp/gen
    ${XBOXRECOMP_DIR}/include
    ${XBOXRECOMP_DIR}/src
    ${XBOXRECOMP_DIR}/src/kernel)
target_link_libraries(ani_gen PRIVATE platform)
# The guest memory model aliases freely through MEM32/MEMF.
target_compile_options(ani_gen PRIVATE
    -O2 -fno-strict-aliasing -fwrapv -w)

add_executable(${PROJECT_NAME}
    ${ANI_ROOT}/src/main_vk.c
    ${ANI_ROOT}/src/recomp_manual.c
    $<TARGET_OBJECTS:ani_gen>)
target_compile_definitions(${PROJECT_NAME} PRIVATE ANI_NV2A_VK)
target_link_libraries(${PROJECT_NAME} PRIVATE xboxrecomp xbox_nv2a_vk)
target_include_directories(${PROJECT_NAME} PRIVATE
    ${ANI_ROOT}/src
    ${ANI_ROOT}/src/recomp/gen
    ${XBOXRECOMP_DIR}/include
    ${XBOXRECOMP_DIR}/src)
target_compile_options(${PROJECT_NAME} PRIVATE -O2 -fno-strict-aliasing)

if(WIN32)
    # A console program while it is being brought up: its log is the
    # debugging tool. ANI_GUI=ON builds the windowed-only program.
    option(ANI_GUI "Build without a console window" OFF)
    set_target_properties(${PROJECT_NAME} PROPERTIES OUTPUT_NAME Animaniacs
                          WIN32_EXECUTABLE ${ANI_GUI})
    target_link_libraries(${PROJECT_NAME} PRIVATE winmm dbghelp)
endif()
