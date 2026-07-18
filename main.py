# Disabling bytecode generation.
import sys
sys.dont_write_bytecode = True

import getopt
import os

import variables
from utils import update_version_info, validate_cmake_version, warning
from classes import CMakeVersion
from processing import convert


def usage():
    """Prints how to use the application."""
    print("auto2cmake - A pure python utility to convert Autotools & QMake projects to CMake\n")
    
    print("Usage: auto2cmake.py [OPTIONS] \n")
    print("OPTIONS:\n")
    
    print(
        "1.    [ -h | --help ]\n"
        "\tDisplays this message.\n"
    )

    print(
        "2.    [ -d <dir> | --directory=<dir> ]\n"
        "\tBy default, auto2cmake uses the current working directory for execution.\n"
        "\tBy passing this flag the working directory will be changed to reflect the provided directory.\n"
    )

    print(
        "3.    [ -e <dir> | --exclude=<dir1> | --exclude=<dir1:dir2:etc> ]\n"
        "\tBy passing this flag the provided directories will be skipped during execution.\n"
    )

    print(
        "4.    [ -c | --disable-comments ]\n"
        "\tBy default, auto2cmake generates comments in the newly created CMakeLists.txt\n"
        "\tBy passing this flag, these comments will NOT be generated.\n"
    )
    
    print(
        "5.    [ -q | --quick ]\n"
        "\tBy default auto2cmake disables Quick Mode.\n"
        "\tBy passing this flag, Quick Mode will be enabled.\n" 
        "\tQuick Mode:\n"
        "\t    - Ignores both Automake and QMake project files.\n"
        "\t    - Identify all usages of QT in the project's .cpp files.\n"
    )

    print(
        "6.    [ -r | --recursive ]\n"
        "\tBy default auto2cmake disables recursive directory walking.\n"
        "\tBy passing this flag, recursion will be enabled.\n"
    )
    
    print(
        "7.    [ -a | --automoc ]\n"
        "\tBy default auto2cmake uses CMake's Automoc generation.\n"
        "\tBy passing this flag, CMake Automoc generation will be disabled.\n"
        "\tThis flag also enables QT source wrapping.\n"
        "\tIf Quick Mode is enabled, this flag won't change any behavior.\n"
    )

    print(
        "8.    [ -v <version> | --version=<version> ]\n"
        "\tBy default auto2cmake pins minimum version support to CMake 2.8+\n"
        "\tBy passing this flag, auto2cmake will use the specified version.\n"
    )


def main(argv):
    update_version_info()

    try:
        opts, args = getopt.getopt(
            argv, 
            shortopts="d:e:v:hqrac", 
            longopts=["directory=", "exclude=", "version=", "help", "quick", "recursive" , "automoc", "disable-comments"]
        )
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    for opt, arg in opts:
        if opt == "-h" or opt == "--help":
            usage()
            sys.exit()

        elif opt == "-d" or opt == "--directory":
            variables.working_directory = os.path.expanduser(arg)
            print("Starting execution in directory: {}".format(variables.working_directory))
        
        elif opt == "-e" or opt == "--exclude":
            variables.excluded_directories = arg.split(':')
        
        elif opt == "-q" or opt == "--quick":
            variables.quick = True
        
        elif opt == "-r" or opt == "--recursive":
            variables.recursive = True
        
        elif opt == "-a" or opt == "--automoc":
            variables.cmake_automoc = False

        elif opt == "-c" or opt == "--disable-comments":
            variables.generate_comments = 0

        elif opt == "-v" or opt == "--version":
            print(f"CMake {variables.cmake_maximum_version} is the latest.")
            print(f"CMake {arg} was specified via flag.")
            print()
            print(f"Checking if auto2cmake supports CMake {arg}, please wait.")
            print()
            validate_cmake_version(provided_version=arg, latest_version=variables.cmake_maximum_version.full_version)
            variables.cmake_minimum_version = CMakeVersion(arg)

    convert()


if __name__ == "__main__":
    main(sys.argv[1:])