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

project(animaniacs_vk VERSION 1.0.0 LANGUAGES C CXX)

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

# The in-process Archipelago client (src/ap, docs/ARCHIPELAGO.md).
set(ANI_AP_SOURCES
    ${ANI_ROOT}/src/ap/ap_bridge.c
    ${ANI_ROOT}/src/ap/ap_game.c
    ${ANI_ROOT}/src/ap/ap_ui.c
    ${ANI_ROOT}/src/ap/ap_json.c
    ${ANI_ROOT}/src/ap/ap_net.c
    ${ANI_ROOT}/src/ap/ap_ws_posix.c
    ${ANI_ROOT}/src/ap/ap_ws_winhttp.c)

add_executable(${PROJECT_NAME}
    ${ANI_ROOT}/src/main_vk.c
    ${ANI_ROOT}/src/settings.c
    ${ANI_ROOT}/src/recomp_manual.c
    ${ANI_AP_SOURCES}
    $<TARGET_OBJECTS:ani_gen>)
target_compile_definitions(${PROJECT_NAME} PRIVATE ANI_NV2A_VK ANI_AP
    ANI_VERSION="${PROJECT_VERSION}")
target_link_libraries(${PROJECT_NAME} PRIVATE xboxrecomp xbox_nv2a_vk)
target_include_directories(${PROJECT_NAME} PRIVATE
    ${ANI_ROOT}/src
    ${ANI_ROOT}/src/recomp/gen
    ${XBOXRECOMP_DIR}/include
    ${XBOXRECOMP_DIR}/src)
target_compile_options(${PROJECT_NAME} PRIVATE -O2 -fno-strict-aliasing)

if(WIN32)
    # A windowed program (no console); its output goes where it was redirected,
    # else to the parent console, else to log.txt (src/main_vk.c). ANI_GUI=OFF: console.
    option(ANI_GUI "Build without a console window" ON)
    set_target_properties(${PROJECT_NAME} PROPERTIES OUTPUT_NAME Animaniacs
                          WIN32_EXECUTABLE ${ANI_GUI})
    target_link_libraries(${PROJECT_NAME} PRIVATE winmm dbghelp winhttp)
    # A PDB beside the exe: every lifted function is a symbol (sub_XXXXXXXX),
    # so crash reports and scripts/sample_profile.py name guest functions.
    target_link_options(${PROJECT_NAME} PRIVATE -Wl,--pdb=)
    # Line tables for the GPU model, the usual hot spot in a profile.
    target_compile_options(xbox_nv2a_vk PRIVATE -gcodeview -gline-tables-only)
    # The DLLs it needs beside it (cmake/copy_dlls.cmake), so the build
    # folder is a runnable game folder.
    find_package(Python3 COMPONENTS Interpreter)
    get_filename_component(_tc_bin "${CMAKE_C_COMPILER}" DIRECTORY)
    if(Python3_FOUND)
        add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
            COMMAND ${CMAKE_COMMAND}
                -DPY=${Python3_EXECUTABLE}
                -DOBJDUMP=${_tc_bin}/llvm-objdump.exe
                -DEXE=$<TARGET_FILE:${PROJECT_NAME}>
                -DSCRIPT=${ANI_ROOT}/tools/ngbrecomp/packaging/windows/dlldeps.py
                "-DDIRS=${_tc_bin}/../x86_64-w64-mingw32/bin;${ANI_WIN_SYSROOT}/bin"
                -P ${ANI_ROOT}/cmake/copy_dlls.cmake
            VERBATIM)
    endif()
endif()

# The notices and license texts travel with the game folder.
set(_xr ${ANI_ROOT}/tools/ngbrecomp/xboxrecomp)
add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory $<TARGET_FILE_DIR:${PROJECT_NAME}>/licenses
    COMMAND ${CMAKE_COMMAND} -E copy_if_different ${ANI_ROOT}/THIRD_PARTY.md
        $<TARGET_FILE_DIR:${PROJECT_NAME}>/THIRD_PARTY.md
    COMMAND ${CMAKE_COMMAND} -E copy_if_different ${_xr}/LICENSE
        $<TARGET_FILE_DIR:${PROJECT_NAME}>/licenses/xboxrecomp-LICENSE.txt
    COMMAND ${CMAKE_COMMAND} -E copy_if_different ${_xr}/NOTICE
        $<TARGET_FILE_DIR:${PROJECT_NAME}>/licenses/xboxrecomp-NOTICE.txt
    COMMAND ${CMAKE_COMMAND} -E copy_if_different ${_xr}/LICENSES/LGPL-2.1.txt
        $<TARGET_FILE_DIR:${PROJECT_NAME}>/licenses/LGPL-2.1.txt
    VERBATIM)

# Profiling aid: ANI_PROFILE_NOINLINE=ON keeps the GPU model's helpers out of
# line, so a sample lands in the function that is actually hot.
option(ANI_PROFILE_NOINLINE "No inlining in the GPU model (profiling)" OFF)
if(ANI_PROFILE_NOINLINE)
    target_compile_options(xbox_nv2a_vk PRIVATE -fno-inline -fno-inline-functions)
endif()
