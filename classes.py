import variables
import sys
from enum import Enum
from typing import List, Optional



class CMakeFile:
    """Represents a CMake file that will be generated at a later stage."""
    def __init__(self, directory):
        self.directory = directory                  # The directory where this can be found
        self.contained_libraries_content = []       # All the content of the libraries that are created in here
        self.libraries = []                         # All the libraries that are created by this file
        self.extra_content = ""                     # Extra stuff such as add_subdriectory


class CMakeVersion:
    """Represents a CMake version object that will be utilized prior to, and during the generation stages."""
    def __init__(self, version_string: str):
        self.full_version: str = version_string
        
        self.major: Optional[int] = None
        self.minor: Optional[int] = None
        
        # Since the build version is not always specified, defaulting it to 0 will avoid AttributeError(s)
        self.build: int = 0 

        # Initializing the major, minor, and build versions
        self.__parse__(version_string)

    def __parse__(self, version_string: Optional[str]):
        if version_string is None:
            print("No CMake version string provided. Expected format: 'X.X' or 'X.X.X'")
            sys.exit(1)

        version_parts: List[int] = [int(part) for part in version_string.split('.') if part.isdigit()]
        number_of_parts: int = len(version_parts)

        if number_of_parts in [0, 1] or number_of_parts > 3:
            print("Unable to parse the provided CMake version string. Expected format: 'X.X' or 'X.X.X'")
            sys.exit(1)
        
        # Covering the major and minor version numbers
        if number_of_parts >= 2:
            self.major = version_parts[0]
            self.minor = version_parts[1]
        
        # Since this class will not be called more than a handful of times, this additional check:
        # - Covers the build version number
        # - Uses a neglible amount of memory
        # - Improves readability for future maintainers
        if number_of_parts == 3:
            self.build = version_parts[2]

    def __str__(self):
        return self.full_version


class TargetType(Enum):
    """Whether a target is a Library (noinst_LIBRARIES) or an Application (bin_PROGRAMS)"""
    LIBRARY = 1
    PROGRAM = 2


class Library:
    """Represents a library that will be built by a specific make command."""
    def __init__(self, name, directory):
        self.name = name
        self.dependant = False
        self.filelist = [] # the list of files of this library
        self.condition = [] # the list of conditions on which this library is built if any
        self.link_with_libs = [] # the list of libraries that were built by the script. target_link_libraries
        self.compiler_flags = [] # the compiler options
        self.linker_flags = []   # the linker flags. the -l flags will be parsed out into link_with_libs
        self.conditional_appends = {}
        self.just_variables = {}
        self.added_subdirectories = []
        self.target_type = TargetType.LIBRARY
        self.ttype = ""
        self.referred_name = name

        if '$' in self.name:
            self.name = self.name.replace('$', '')
            self.name = self.name.replace('(', '')
            self.name = self.name.replace(')', '')
            self.dependant = True

        from utils import canonicalize
        self.canonic_name = canonicalize(self.name)
        self.directory = directory

        if not self.dependant:
            if self.name.endswith(".a"):
                self.type = "STATIC"
                self.referred_name = self.name[3:]
                self.referred_name = self.referred_name[:-2]
            else:
                self.type = "DYNAMIC"
                self.referred_name = self.name[3:]
                self.referred_name = self.referred_name[:-3]
        else:
            self.type = "STATIC"
            self.referred_name = self.name


class Option:
    """Represents an option that will go in the CMakeLists.txt and also in the generated header if a define is present."""

    def __init__(self, name, description, status, define, define_value, define_description):
        name = name.replace("-", "_")
        if variables.upcase_identifiers:
            self.name = name.upper()
        else:
            self.name = name
        self.description = description
        self.status = status
        self.define = define
        define_value = define_value.replace(']', '')
        define_value = define_value.replace(',', '')
        define_value = define_value.replace('[', '')
        self.define_value = define_value
        self.define_description = define_description
        self.extra_defines = []

    def set_name(self, name):
        self.name = name

    def get_name(self):
        return self.name

    def set_description(self, description):
        self.description = description

    def get_description(self):
        return self.description

    def set_status(self, status):
        self.status = status

    def get_status(self):
        return self.status

    def set_define(self, define):
        self.define = define

    def get_define(self):
        return self.define

    def set_define_value(self, define_value):
        if '[' in define_value:
            define_value = define_value.replace(']', '')
            define_value = define_value.replace('[', '')
        self.define_value = define_value

    def get_define_value(self):
        return self.define_value

    def set_define_description(self, define_description):
        self.define_description = define_description

    def get_define_description(self):
        return self.define_description

    def finalize(self):
        if len(self.description) <= 1:
            self.description = "Enable " + self.name
        if len(self.status) <= 1:
            self.status = "OFF"
        if len(self.define_description) <= 1:
            self.define_description = self.description

    def add_extra_define(self, extra_define):
        self.extra_defines.append(extra_define)

    def get_extra_defines(self):
        return self.extra_defines