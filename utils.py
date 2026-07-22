# Copyright (c) 2026 Ferenc Deak & Static Codes
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import os
import sys
import re
import glob
import shutil
import subprocess
from difflib import SequenceMatcher
from urllib import request
from json import loads
from typing import Optional

import variables
from classes import CMakeVersion


def get_installed_cmake_version() -> Optional[CMakeVersion]:
    """Checks for an installation of CMake and attempts to resolve the version installed."""
    print("Checking for a CMake installation, please wait.")
    print()
        
    # Checking for the existence of "cmake" in the current system's path.
    if not shutil.which("cmake"):
        print("CMake installation not found. Please install CMake and try again.")
        sys.exit()

    match = None
    
    try:
        result = subprocess.run(
            ["cmake", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        # Checking for the expected output of:
        # "cmake version X.X.X" or "cmake3 version X.X.X"
        match = re.search(r"version\s+([\d.]+)", result.stdout)
        
        if not match:
            print(
                f"CMake detected, but the version string could not be parsed.\nOutput: {result.stdout}"
            )
            sys.exit(1)

        print(f"CMake {match.group(1)} is installed.")

    except Exception as e:
        print("A CMake installation was found, however, an unexpected response was received.")
        print(f"Response:\n{e.stderr}")
        return None
    
    return CMakeVersion(match.group(1))
    

def cmake_version_is_invalid(lower_version_obj: CMakeVersion, higher_version_obj: CMakeVersion) -> bool:
    """
        Performs a comparison operation on two CMakeVersion objects.
        Returns True if lower_version_obj is greater than higher_version_obj when both objects are parsed.
        Returns False otherwise.
    """
    if (
        lower_version_obj.major is None or
        higher_version_obj.major is None or
        lower_version_obj.minor is None or
        higher_version_obj.minor is None
    ):
        return True
    elif (
        lower_version_obj.major > higher_version_obj.major or 
        lower_version_obj.major >= higher_version_obj.major and
        lower_version_obj.minor > higher_version_obj.minor
    ):
        return True
    elif (
        lower_version_obj.major >= higher_version_obj.major and
        lower_version_obj.minor >= higher_version_obj.minor and
        lower_version_obj.build > higher_version_obj.build
    ):
        return True

    return False


def validate_cmake_version(provided_version: str, latest_version: Optional[str]):
    """Validates the value for the arguments "-v <VERSION>" and --version="<VERSION>"""
    if latest_version is None:
        print("Unable to resolve the latest version of CMake.")
        return

    try:
        provided_version_obj: CMakeVersion = CMakeVersion(provided_version)
        latest_version_obj: CMakeVersion = CMakeVersion(latest_version)

        # Handles versions that are less than the minimum supported
        if (cmake_version_is_invalid(variables.cmake_minimum_version, provided_version_obj)):
            print(f"The specified version of CMake (v{provided_version_obj}) is not supported by auto2cmake.")
            print(f"Please specify a version at or greater than CMake {variables.cmake_minimum_version}")
            sys.exit(1)

        # Handles versions that are not released
        elif (cmake_version_is_invalid(provided_version_obj, latest_version_obj)):
            print("The specified version of CMake is not currently released.")
            print(f"The latest public release is v{latest_version_obj}")
            sys.exit(1)

        # General null check
        elif (not provided_version_obj or not variables.cmake_installed_version):
            print("The following parameter has a NoneType in validate_cmake_version:")
            print("\tprovided_version_obj" if not provided_version_obj else "\tcmake_installed_version")
            sys.exit(1)

        # Warning when the installed version is older
        elif (cmake_version_is_invalid(provided_version_obj, variables.cmake_installed_version)):
            print(f"The specified version of CMake (v{provided_version_obj}) is newer than the installed version on the current system.")
            warning(
                "This may cause unexpected behavior.\n"
                f"It is recommended to specify {variables.cmake_installed_version} instead of {provided_version_obj}"
            )
        else:
            print(f"Validation complete, all processing will be done using CMake {provided_version_obj}")
            
    except Exception as e:
        print(f"Error validating the provided version of CMake.")
        print(f"Type: {type(e)}")
        print(f"Error: {e}")
        print("Skipping version validation.")
        return


def get_latest_cmake_version():
    """Resolves the latest version of CMake from https://github.com/Kitware/CMake"""
    url = "https://api.github.com/repos/Kitware/CMake/releases"
    version = None
    json_data = None

    try:
        with request.urlopen(url) as req:
            str_data = req.read().decode('utf-8')
            json_data = loads(str_data)
            version = json_data[0]["tag_name"][1:]

    except Exception as e:
        print(e)

    if not json_data:
        print("Unable to resolve the latest version of CMake.")
    
    return CMakeVersion(version)


def update_version_info():
    """Updates the CMake version information used by the application."""
    variables.cmake_maximum_version = get_latest_cmake_version()
    variables.cmake_installed_version = get_installed_cmake_version()


def warning(*s):
    """Prints a warning message"""
    print("".join(s))


def has_library(name):
    """Checks if there is already a library with the specified name"""
    for library in variables.libraries:
        if library.canonic_name == name:
            return True
    return False


def count_parentheses(line):
    """Counts the parentheses in the line. Returns 0 if the number of opened parenthesis equals the number of closed ones"""
    parco = 0
    for char in line:
        if char == '(':
            parco += 1
        if char == ')':
            parco -= 1
    return parco


def replace_quotes(value):
    """Replaces the quotes with escaped quotes to be put in the CMakeLists.txt"""
    value = value.replace('\"', '\\"')
    return value


def get_library_for_name(name):
    """Returns a library object if the library's name matches the specified name string."""
    for library in variables.libraries:
        if library.canonic_name == name:
            return library
    return None


def similar(s1, s2):
    """Returns the similarity of two strings."""
    return SequenceMatcher(None, s1, s2).ratio()


def should_exclude(directory_path):
    """Whether the directory is excluded or not."""
    for excluded_directory in variables.excluded_directories:
        if directory_path.startswith(excluded_directory):
            return True
    return False


def remove_garbage(extra_value):
    chars = ",[]$()"
    for char in chars:
        extra_value = extra_value.replace(char, '')
    return extra_value.strip()


def canonicalize(a):
    canonic_name = ""
    for c in a:
        if c.isdigit() or c.isalpha() or c =='_':
            canonic_name += c
        else:
            canonic_name += "_"
    return canonic_name


def find_file(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)


def make_nice_library_name(link_name):
    """Makes a CMake internal library name from what comes in."""
    link_name = link_name.replace("'", "")
    if link_name.startswith("-L"):
        return link_name
    
    fullp = link_name.split('/')
    
    if len(fullp) > 1:
        target_link_lib = fullp[-1]
    else:
        target_link_lib = "".join(fullp)
    
    if '.' in target_link_lib:
        target_link_lib = target_link_lib.split(".")[0]
        if target_link_lib.startswith("lib"):
            target_link_lib = target_link_lib[3:]
    
    if target_link_lib.startswith("-l"):
        target_link_lib = target_link_lib[2:]
    
    return target_link_lib


def filelist_to_string(elements, source_directory, spacecount = 4):
    """Transform a list (of files) to a string."""
    filelist = ""
    for file in sorted(elements):
        if os.path.isfile(source_directory + "/" + file):
            filelist += "\n" +" " * spacecount + "${CMAKE_CURRENT_SOURCE_DIR}/" + file
        else:
            filelist += "\n#" +" " * spacecount + "${CMAKE_CURRENT_SOURCE_DIR}/" + file + " # File not found. Fix manually"
            warning("WARNING!!! The file: " + source_directory + "/" + file + " is present in the Makefile.am but cannot be found in the filesystem")
    return filelist


def find_wildcard_file(fn, dir):
    """Finds a list of files in the given directory"""
    fs = glob.glob(dir + "/" + fn)
    return fs


def moc_header(fn):
    """Will check if the incoming header file is a MOC header or not. Just scan for a Q_OBJECT macro in it"""
    with open(fn) as search:
        for line in search:
            line = line.strip()  # remove '\n' at end of line
            if "Q_OBJECT" == line:
                print('  Checking if {} is moc:{}'.format(fn, True))
                search.close()
                return True
    search.close()
    print('  Checking if {} is moc:{}'.format(fn, False))
    return False