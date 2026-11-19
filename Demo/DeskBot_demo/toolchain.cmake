# Specify the cross-compilation toolchain
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

get_filename_component(ECHOMATE_DEFAULT_SDK "${CMAKE_CURRENT_LIST_DIR}/../../SDK/rv1106-sdk" ABSOLUTE)
set(SDK_PATH "${ECHOMATE_DEFAULT_SDK}" CACHE PATH "Echo-Mate SDK directory")

# Specify the compiler paths
set(CMAKE_C_COMPILER ${SDK_PATH}/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf-gcc)
set(CMAKE_CXX_COMPILER ${SDK_PATH}/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf-g++)

# Specify the sysroot (if available)
set(CMAKE_SYSROOT ${SDK_PATH}/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/arm-rockchip830-linux-uclibcgnueabihf/sysroot)

# Add paths to find libraries and includes
set(CMAKE_FIND_ROOT_PATH ${CMAKE_SYSROOT})

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
