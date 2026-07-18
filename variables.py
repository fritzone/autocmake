cpp_extensions = [".c", ".cpp", ".cxx", ".c++", ".cc"]
header_extensions = [".h", ".hpp", ".hxx", ".h++", ".hh"]
qrc_extensions = [".qrc"]

quick = False
recursive = False
quick_gen_lib = True
cmake_automoc = True
upcase_identifiers = 1
generate_comments = 1
more_newlines = 1
working_directory = "."
excluded_directories = []

cmake_maximum_version = None
cmake_installed_version = None

libraries = []
options = {}
temp_defines = {}
cmake_files = {}
config_ac_variables = {}
extra_content = {}
required_directories = []

from classes import CMakeVersion
cmake_minimum_version = CMakeVersion("2.8")