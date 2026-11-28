cmake_minimum_required(VERSION 3.18)
project(pogolab_battle LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Python 3.11 REQUIRED COMPONENTS Interpreter Development.Module)

execute_process(
    COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE nanobind_ROOT
)
find_package(nanobind CONFIG REQUIRED)

add_library(pogolab_battle STATIC
    cpp/src/mechanics.cpp
    cpp/src/engine.cpp
)
target_include_directories(pogolab_battle PUBLIC cpp/include)
set_target_properties(pogolab_battle PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    target_compile_options(pogolab_battle PRIVATE /W4)
else()
    target_compile_options(pogolab_battle PRIVATE -Wall -Wextra -Wpedantic)
endif()

nanobind_add_module(_core NB_STATIC cpp/bindings/battle_bindings.cpp)
target_link_libraries(_core PRIVATE pogolab_battle)

install(TARGETS _core LIBRARY DESTINATION pogolab/battle)
