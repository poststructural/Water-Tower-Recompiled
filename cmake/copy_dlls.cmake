# Post-build: copy the DLLs the exe needs that Windows does not ship (SDL2,
# glib, libc++, ...) beside it, so the build folder runs without PATH set up.
# Resolved recursively with ngbrecomp's dlldeps.py.
#   cmake -DPY= -DOBJDUMP= -DEXE= -DSCRIPT= -DDIRS="a;b" -P copy_dlls.cmake
get_filename_component(_out "${EXE}" DIRECTORY)
execute_process(COMMAND "${PY}" "${SCRIPT}" "${OBJDUMP}" "${EXE}" ${DIRS}
                OUTPUT_VARIABLE _dlls ERROR_QUIET RESULT_VARIABLE _rc)
if(NOT _rc EQUAL 0)
    message(WARNING "copy_dlls: dlldeps.py failed (${_rc})")
    return()
endif()
string(REPLACE "\r" "" _dlls "${_dlls}")
string(REPLACE "\n" ";" _dlls "${_dlls}")
foreach(_d ${_dlls})
    if(_d)
        file(COPY "${_d}" DESTINATION "${_out}")
    endif()
endforeach()
