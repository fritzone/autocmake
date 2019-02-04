#!/usr/bin/python3
# script to convert an autotools project to more or less corresponding CMakeLists.txt structure
# Interpret the linker flags
# interpret the programs, generate add_executable
# specify the target link dependencies
# the gather the files mode
# include directory generation based on parsing the file for #include

import sys, getopt, time, os, re
from difflib import SequenceMatcher
from enum import Enum
import glob
from os.path import join as pjoin

########################################################################################################################
#                 Global variables used by the application, specified on command line                                  #
########################################################################################################################

#
# whether this is a quick conversion
quick = False
# whether the quick conversion is recursive or not
recursive = False
# whether the quick conversion generates a library or an executable
quick_gen_lib = True
# whether to use CMakes AUTOMOC or manually generate the moc files
cmake_automoc = False

# all the options should be upcase? -u switch
upcase_identifiers = 1
# should we generate some coments in the CMakeLists.txt? -c switch
generate_comments = 1
# generate more empty lines in the output file. -n switch
more_newlines = 1
# The working directory. Will be set by the -d argument to the script
working_directory = "."
# these directories will be excluded when searching for Makefile.am's (or any other processing). -e is the argument
exclude_directories = []

########################################################################################################################
#                                       The application logic structures                                               #
########################################################################################################################

# the list of libraries that will be built. contains Library objects
libraries = []
# will contain all the options that were gathered from configure.ac in form of Option objects
options = {}
# will contain all the defines from the configure.ac
temp_defines = {}
# will contain the CMakeLists of the converted system. Key is the directory
cmake_files = {}
# will contain all the variables defined in configure.ac
config_ac_variables = {}
# will hold extra content for CMakeLists in specific directories
extra_content = {}
# The list of all the directories that will need a CMakeLists.txt in them
required_directories = []

########################################################################################################################
# Constants
########################################################################################################################
cpp_extensions = [".c", ".cpp", ".cxx", ".c++", ".cc"]
header_extensions = [".h", ".hpp", ".hxx", ".h++", ".hh"]
qrc_extensions = [".qrc"]

########################################################################################################################
#                                       Classes used by the application                                                #
########################################################################################################################

########################################################################################################################
# represents a cmake file that will be generated at a later stage
########################################################################################################################
class CMakeFile:
    def __init__(self, directory):
        self.directory = directory                  # The directory where this can be found
        self.contained_libraries_content = []       # All the content of the libraries that are created in here
        self.libraries = []                         # All the libraries that are created by this file
        self.extra_content = ""                     # Extra stuff such as add_subdriectory

########################################################################################################################
# Whether a target is a library (noinst_LIBRARIES) or an application (bin_PROGRAMS)
########################################################################################################################
class TargetType(Enum):
    LIBRARY = 1
    PROGRAM = 2

########################################################################################################################
# represents a library that will be built by a specific make command
########################################################################################################################
class Library:
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


########################################################################################################################
# represents an option that will go in the CMakeLists.txt and also in the generated header if has a define
########################################################################################################################
class Option:

    def __init__(self, name, description, status, define, define_value, define_description):
        name = name.replace("-", "_")
        if upcase_identifiers:
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



########################################################################################################################
#                                       Helper functions used by the application                                       #
########################################################################################################################

########################################################################################################################
# prints a warning message
########################################################################################################################
def warning(*s):
    print("".join(s))

########################################################################################################################
# Checks if there is already a library called
########################################################################################################################
def has_library(name):
    for l in libraries:
        if l.canonic_name == name:
            return True
    return False

########################################################################################################################
# counts the parentheses in the line. Returns 0 if the number of opened parenthesis equals the number of closed ones
########################################################################################################################
def count_parentheses(line):
    parco = 0
    for char in line:
        if char == '(':
            parco += 1
        if char == ')':
            parco -= 1
    return parco


########################################################################################################################
# Replaces the quotes with escaped quotes to be put in the CMakeLists.txt
########################################################################################################################
def replace_quotes(a):
    a = a.replace('\"', '\\"')
    return a


def get_library_for_name(name):
    for l in libraries:
        if l.canonic_name == name:
            return l
    return None

########################################################################################################################
# returns the similarity of two strings.
########################################################################################################################
def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


########################################################################################################################
# Whether the directory is ecluded or not
########################################################################################################################
def should_exclude(dire):
    for exc_dir in exclude_directories:
        if dire.startswith(exc_dir):
            return True
    return False

########################################################################################################################
# removes the garbage characters from the given string
########################################################################################################################
def remove_garbage(extra_value):
    extra_value = extra_value.replace(']', '')
    extra_value = extra_value.replace(',', '')
    extra_value = extra_value.replace('[', '')
    extra_value = extra_value.replace('$', '')
    extra_value = extra_value.replace('(', '')
    extra_value = extra_value.replace(')', '')
    extra_value = extra_value.strip()
    return extra_value


########################################################################################################################
# All characters in the name except for letters, numbers, the strudel (@), and the underscore are turned into underscores
########################################################################################################################
def canonicalize(a):
    canonic_name = ""
    for c in a:
        if c.isdigit() or c.isalpha() or c =='_':
            canonic_name += c
        else:
            canonic_name += "_"
    return canonic_name


########################################################################################################################
# Finds a file with the given name
########################################################################################################################
def find_file(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)


########################################################################################################################
# processes the given AC_ARG_ENABLE and creates an entry in the global options
########################################################################################################################
def process_argument(line):
    s = line[len("AC_ARG_ENABLE("):].strip()
    # fetch the name of the argument
    arg_name = ""
    for c in s:
        if c == ',':
            break
        arg_name += c
    # fetch the description of the argument
    description = ""
    for i in range(len(s)):
        if s[i] == '[':
            # after the [ come spaces
            i += 1
            while s[i] == ' ' and i < len(s):
                i += 1
            # then comes the option names, skip that
            while s[i] != ' ' and i < len(s):
                i += 1
            # and then again a lot of spaces
            while s[i] == ' ' and i < len(s):
                i += 1
            # then finally the description, till the closing ]
            while s[i] != ']' and i < len(s):
                description += s[i]
                i += 1
            # we have the description, just break out from here
            break

    # now see if this is on or off
    on_off = "OFF"
    if "=yes" in s:
        on_off = "ON"

    arg_name = arg_name.replace("-", "_")

    # and add to the big options structure above
    if not (arg_name in options):
        options[arg_name] = Option(arg_name, description, on_off, "", "", "")
    else:
        options[arg_name].set_name(arg_name)
        options[arg_name].set_description(description)
        options[arg_name].set_status(on_off)


########################################################################################################################
# Checks whether this line os processable by the script or not
########################################################################################################################
def processable_line(line):
    possible_starts = ["AC_ARG_ENABLE(", "AM_CONDITIONAL(", "AC_DEFINE(", "AC_CONFIG_FILES("]
    for start in possible_starts:
        if line.startswith(start):
            return start[:-1]
    return ""


########################################################################################################################
# processes the AM_CONDITIONAL lines
########################################################################################################################
def process_conditional(line):
    s = line[len("AM_CONDITIONAL("):].strip()
    define_name = ""
    for c in s:
        if c == ',':
            break
        define_name += c
    bound_option = ""
    stage = 1  # 1 - skipping, 2 - adding
    for c in s:
        if (c == '"' or c == ' ' or c == '=') and stage == 2:
            break
        if stage == 2:
            bound_option += c
        if c == '$':
            stage = 2

    bound_option = bound_option.replace("-", "_")

    if bound_option in options:
        options[bound_option].set_define(define_name)
    else:
        options[bound_option] = Option(bound_option, "", "", define_name, "", "")

########################################################################################################################
# this will process the defines from the configure.ac, but puts them in a separate list, with the comments
########################################################################################################################
def process_a_define(line):
    s = line[len("AC_DEFINE("):].strip()
    # now parse out the define data from s

    define_string = ""
    defined_to_value = ""
    define_description = ""

    stage = 1  # 1 - parsing  the define name, 2 parsing the define value, 3 - parsing the define description
    sqp = 0
    roup = 1
    for c in s:
        if c == '[':
            sqp += 1
        if c == ']':
            sqp -= 1
        if c == '(':
            roup += 1
        if c == ')':
            roup -= 1
            # Did we close the parentheses for AC_DEFINE( ?
            if roup == 0:
                break
        if c == ',' and sqp == 0:
            stage += 1
            if stage == 4:
                break
        if stage == 1 and c != ',':
            define_string += c
        elif stage == 2 and c != ',':
            defined_to_value += c
        elif stage == 3:
            define_description += c

    # and finding the variable name (option name in later stages here)
    variable_name = ""
    stage = 1 # 1 - skipping, 2 - adding
    for c in s:
        if c == '"' and stage == 2:
            break
        if stage == 2:
            variable_name += c
        if c == '$':
            stage = 2

    temp_defines[define_string] = {}
    temp_defines[define_string]["name"] = define_string
    temp_defines[define_string]["option_name"] = variable_name.upper()
    temp_defines[define_string]["description"] = define_description
    temp_defines[define_string]["value"] = defined_to_value
    temp_defines[define_string]["used"] = 0


########################################################################################################################
# processes a Makefile.am
########################################################################################################################
def process_makefile_am(file):

    # the content of the outgoing CMakeLists.txt
    if not os.path.isfile(file):
        warning("File not found:", file)
        return
    current_directory = os.path.dirname(file)


    if should_exclude(current_directory):
        return

    # Will recurse into these dires
    dirs_to_go_in = []

    defined_variables = {}
    libraries_in_this_file = []
    with open(file) as f:
        content = f.readlines()

    # First run: parse out all the libraries
    for line in content:
        line = line.strip()
        # is this a valid line? ie. no comments?
        if line.startswith("#"):
            continue

        # Yes, valid line
        if line.find("_LIBRARIES") != -1 or line.find("_PROGRAMS") != -1:
            elements = line.split()
            library_names = elements[2:]
            makefiles_directory = current_directory
            process_it = True
            for excluded_dir in exclude_directories:
                if makefiles_directory.startswith(excluded_dir) and excluded_dir:
                    process_it = False
            if process_it:
                for library_name in library_names:
                    library = Library(library_name, makefiles_directory)
                    # program or library?
                    if line.find("_PROGRAMS") != -1:
                        library.target_type = TargetType.PROGRAM
                        library.referred_name = library.canonic_name
                    if not has_library(library.canonic_name):
                        libraries.append(library)

    # Next run: gather the source codes for all the libraries created in this file. Parse "if"'s also
    if_condition = ""
    for i in range(len(content)):

        line = content[i].strip()
        # is this a valid line? ie. no comments?
        if line.startswith("#"):
            continue
        if line.startswith("if"):
            elements = line.split()
            if_condition = elements[1]
        if line.startswith("endif"):
            if_condition = ""

        # see if this is an assignment or not
        if '=' in line or "+=" in line:
            # simple assignment
            # read in the line as long as we don't have ending \\
            while line.endswith('\\'):
                i += 1
                line += content[i].strip()

            line = line.replace("\\", "")
            line = ''.join('%-1s' % item for item in line.split('\t '))
            used = False

            elements = line.split("=")
            variable = elements[0].strip()

            if '+' in variable:
                variable = variable.replace('+', '').strip()

            # see if this is a SOURCE identifier for a specific library
            if variable.endswith("_SOURCES"):
                # find the lib name
                target_lib_name = variable[:-len("_SOURCES")]

                # now find the library from the libraries list, built in the previous step
                library = get_library_for_name(target_lib_name)

                if library:
                    used = True
                    libraries_in_this_file.append(target_lib_name)
                    # do we have a condition for this library?
                    if if_condition:
                        library.condition += if_condition

                    if "+=" in line:
                        library.filelist += elements[1].split()
                    else:
                        library.filelist = elements[1].split()

            if variable.endswith("_LDADD"):
                # find the lib name
                target_lib_name = variable[:-len("_LDADD")]
                library = get_library_for_name(target_lib_name)

                if library in libraries:
                    used = True
                    libraries_in_this_file.append(target_lib_name)
                    # do we have a condition for this library?
                    if if_condition:
                        library.condition += if_condition

                    if "+=" in line:
                        library.link_with_libs += elements[1].split()
                    else:
                        library.link_with_libs = elements[1].split()

            if variable.endswith("_CXXFLAGS") or variable.endswith("_CPPFLAGS") or variable.endswith("_CFLAGS"):
                # find the lib name
                if variable.endswith("_CFLAGS"):
                    target_lib_name = variable[:-len("_CFLAGS")]
                else:
                    target_lib_name = variable[:-len("_CXXFLAGS")]

                library = get_library_for_name(target_lib_name)

                if library in libraries:
                    used = True
                    libraries_in_this_file.append(target_lib_name)
                    # do we have a condition for this library?
                    if if_condition:
                        library.condition += if_condition
                    defines = line.replace(variable, "", 1)
                    defines = defines.replace("=", "", 1)
                    defines = defines.strip()
                    if "+=" in line:
                        library.compiler_flags += defines
                    else:
                        library.compiler_flags = defines

            if variable.endswith("_LDFLAGS"):
                # find the lib name
                target_lib_name = variable[:-len("_LDFLAGS")]
                library = get_library_for_name(target_lib_name)

                if library in libraries:
                    used = True
                    libraries_in_this_file.append(target_lib_name)
                    # do we have a condition for this library?
                    if if_condition:
                        library.condition += if_condition
                    if "+=" in line:
                        library.linker_flags += elements[1].split()
                    else:
                        library.linker_flags = elements[1].split()

            if not used:
                if variable == "SUBDIRS":
                    dirs_to_go_in = elements[1]
                # This is possibly just a "simple" variable. Highly possible just gathers
                # stuff and uses it at a later stage with $(varname)
                if variable.find("_LIBRARIES")  == -1 and variable.find("_PROGRAMS") == -1:
                    if not variable in defined_variables:
                        defined_variables[variable] = {}
                        defined_variables[variable]["value"] = []
                        defined_variables[variable]["value"].append(elements[1].split())
                        defined_variables[variable]["condition"] = []
                        defined_variables[variable]["condition"].append(if_condition)
                    else:
                        defined_variables[variable]["value"].append(elements[1].split())
                        defined_variables[variable]["condition"].append(if_condition)

    # now the entire file is parsed. See if we can make any replacement of values
    # from $(variable) to the actual definition of the variable

    # firstly let's identify the conditional variables
    if defined_variables:
        # go, through the defined variables see if we can replace any library.filelist element starting with $
        for var_name in defined_variables:
            for defined_lib_name in set(libraries_in_this_file):
                found = False
                library = get_library_for_name(defined_lib_name)

                for file in library.filelist:
                    inside_varname = "$(" + var_name + ")"
                    if file.find(inside_varname) != -1:
                        # Now, we have a list of #ifdef condition, append $source like stuff
                        for cond, value in zip(defined_variables[var_name]["condition"], defined_variables[var_name]["value"]):
                            cond_name = remove_garbage(cond)
                            if cond_name in library.conditional_appends:
                                library.conditional_appends[cond_name].append(' '.join(value))
                            else:
                                library.conditional_appends[cond_name] = value
                            found = True
                        break
                if not found:
                    library.just_variables[var_name] = defined_variables[var_name]["value"]

    if dirs_to_go_in:
        # These stuff will go in a directory -> add_subdirectory map above
        extra_dir = ""
        for subdir in dirs_to_go_in.split():
            if not should_exclude(current_directory + "/" + subdir):
                extra_dir += "\nadd_subdirectory( " + subdir + " )"
                required_directories.append(current_directory + "/" + subdir)
        extra_content[current_directory] = extra_dir


########################################################################################################################
# processes all the libraries, creates the requested CMakeFile list ofthe application
########################################################################################################################
def process_libraries():
    for library in libraries:
        if library.name == "libauth.a":
            print("asd")

        current_content = ""
        added_files = []
        if generate_comments:
            current_content += "# Generating the library " + library.name + "\n"
        current_content += "set(project \"" + library.referred_name + "\")\n\n"
        current_content += "set(${project}, \"\")\n"
        condition_required = ""

        # Here add the various conditional stuff for various files
        for cond in library.conditional_appends:
            conditional_append = library.conditional_appends[cond]
            if cond:
                # now find the condition from option, having define set to this "cond"
                used_cond = False
                for opt_name in options:
                    option = options[opt_name]
                    if option.get_define() == cond:
                        used_cond = True
                        # and of course parse out the "conditional_append" from the simple variables of the library
                        # and generate cmake code which updates a list :)... also should be valid
                        current_content += "\nif(" + option.get_name() + ")\n"
                        unfolded_conditionals = ""
                        condition_required = option.get_name()

                        for cond_append in conditional_append:
                            if '$' in cond_append:
                                nice_var_name = remove_garbage(cond_append)
                                if nice_var_name in library.just_variables:
                                    l = [item for sublist in library.just_variables[nice_var_name] for item in sublist]
                                    unfolded_conditionals = filelist_to_string(l, library.directory, 8)

                        if unfolded_conditionals:
                            current_content += "    list(APPEND ${project}_SOURCES" + unfolded_conditionals
                            added_files.append(unfolded_conditionals)
                        else:
                            current_content += "    list(APPEND ${project}_SOURCES\n        " + "\n        ".join(conditional_append)
                            added_files.append(conditional_append)

                        current_content += "\n    )\nendif()\n"

                if not used_cond:
                    # We did not find this above, regardless generate an if() for it and a source of files
                    condition_required = cond
                    current_content += "\nif(" + cond + ")\n"
                    current_content += "    list(APPEND ${project}_SOURCES\n        " + "\n        ".join(conditional_append)
                    current_content += "\n    )\nendif()\n"

            else:
                add_regardless = []
                unfolded_conditionals = ""
                for cond_append in conditional_append:
                    if '$' in cond_append:
                        nice_var_name = remove_garbage(cond_append)
                        if nice_var_name in library.just_variables:
                            l = [item for sublist in library.just_variables[nice_var_name] for item in sublist]
                            unfolded_conditionals = filelist_to_string(l, library.directory, 8)
                    else:
                        add_regardless.append(cond_append)
                unfolded_conditionals += filelist_to_string(add_regardless, library.directory, 8)
                current_content += "list(APPEND ${project}_SOURCES" + unfolded_conditionals
                added_files.append(unfolded_conditionals)
                current_content += "\n)\n"

        # Now match the option's define to the if_condition above
        if library.condition:
            condition_used = False
            for option in options:
                if options[option].get_define() == library.condition:
                    # add an "if (option)" to the CMakeLists.txt
                    current_content += "if (" + options[option].get_name() + ")\n"
                    condition_required = options[option].get_name()
                    # gather the list of files
                    filelist = filelist_to_string(library.filelist, library.directory)
                    current_content += "    list(APPEND ${project}_SOURCES\n    " + filelist + ")\nendif()\n\n"
                    added_files.append(filelist)
                    condition_used = True
            if not condition_used:
                new_condition = ""
                for c in library.condition:
                    new_condition += c
                library.condition = new_condition
                current_content += "if (" + new_condition + ")\n"
                condition_required = new_condition
                # gather the list of files
                filelist = filelist_to_string(library.filelist, library.directory)
                current_content += "    list(APPEND ${project}_SOURCES\n    " + filelist + ")\nendif()\n\n"
                added_files.append(filelist)

        else:
            # gather the list of files
            filelist = filelist_to_string(library.filelist, library.directory)
            work_list = filelist.strip()
            current_content += "list(APPEND ${project}_SOURCES\n    " + work_list + "\n)\n"
            added_files.append(work_list)

        if library.condition:
            condition_required = library.condition

        if condition_required:
            current_content += "if (" + condition_required + ")\n"

        if library.target_type == TargetType.LIBRARY:
            # and now add some stuff to create a library out of the current stuff
            current_content += "add_library ( " +library.referred_name + \
                               " " + library.type + " " +  "${${project}_SOURCES} )\n"
        else:
            current_content += "add_executable(" + library.name + " ${${project}_SOURCES} )\n"

        if not added_files:
            warning("No source files found for ", library.name )

        # Now add the CPPFLAGS for the library
        # Firstly: parse out the $ stuff, and find the corresponding values for them
        strflags = library.compiler_flags
        strflags = "".join(strflags)
        flags = strflags.split()

        final_flags = ""
        to_work_with_flags = []
        for flag in flags:
            if not '$' in flag and not '@' in flag:
                final_flags += replace_quotes(flag) + " "
            else:
                to_work_with_flags.append(flag)

        if final_flags:
            current_content += "set_target_properties( " + library.referred_name + "\n" \
                               "    PROPERTIES COMPILE_FLAGS \"" \
                               + final_flags + "\"\n)"


        final_flags = []
        done = False
        while not done:
            for flag in to_work_with_flags:
                if '$' in flag:
                    m = re.search("\$\(.*\)", flag)
                    if m:
                        desired_var = remove_garbage(m.group(0))
                        if desired_var == "top_srcdir":
                            to_work_with_flags.append("{CMAKE_SOURCE_DIR}")
                        elif desired_var in config_ac_variables:
                            for v in config_ac_variables[desired_var]["value"]:
                                final_flags.append(v)

                if flag in to_work_with_flags:
                    to_work_with_flags.remove(flag)

            # Are we done?
            done = True
            for flag in to_work_with_flags:
                if '$' in flag:
                    done = False

        include_directories = []
        # Now walk through the to_work_with_flags and see if we have any include directories stuff
        for flag in final_flags:
            flag = flag.replace("'", "")
            flag = flag.strip()

            flags = flag.split()

            for newflag in flags:
                if newflag.strip().startswith("-I"):
                    include_directories.append(newflag.replace("$(top_srcdir)", "${CMAKE_SOURCE_DIR}"))

        if include_directories:
            current_content += "\ntarget_include_directories( " + library.referred_name + " PRIVATE"
            for i_d in include_directories:
                current_content += "\n    " + i_d.replace("-I", "")
            current_content += "\n)\n"

        # See if we need to put in any target_link_libraries command
        if library.link_with_libs:

            final_link_list = "\ntarget_link_libraries( " + library.referred_name

            for link_name in library.link_with_libs:
                target_link_lib = make_nice_library_name(link_name)
                if target_link_lib.startswith("$"):
                    # Find the just_variable for this target stuff, put it's value in here
                    clean_tll_name = remove_garbage(target_link_lib)
                    if clean_tll_name in library.just_variables:
                        for more_link_names_list in library.just_variables[clean_tll_name]:
                            for real_link in more_link_names_list:
                                final_link_list += "\n    " + make_nice_library_name(real_link)
                else:
                    if target_link_lib.startswith("@"):
                        # coming from configure.ac options
                        canname = target_link_lib.replace("@", '')
                        if canname in config_ac_variables:
                            libs = config_ac_variables[canname]["value"]
                            for lib in "".join(libs).split():
                                link_lib_name = make_nice_library_name(lib)
                                if not link_lib_name.startswith("-L"):
                                    final_link_list += "\n    " + link_lib_name
                        else:
                            final_link_list += "\n#    " + target_link_lib + " # <-- FIX THIS"
                            warning ("WARNING: ", target_link_lib, " in ", library.directory + "/CMakeLists.txt",
                                   " was not indentifiable, fix it manually")
                    else:
                        final_link_list += "\n    " + target_link_lib
            final_link_list += "\n)\n"

            current_content += final_link_list

        if condition_required:
            current_content += "\nendif()\n"

        # And now put the CMakeLists to the given location
        # f = open(library.directory + '/CMakeLists.txt','w')
        # f.write(current_content)
        # f.close()

        if not library.directory in cmake_files:
            cmake_files[library.directory] = CMakeFile(library.directory)

        # and fill it up
        cmake_file_holder = cmake_files[library.directory]
        cmake_file_holder.contained_libraries_content.append(current_content)
        cmake_file_holder.libraries.append(library)


########################################################################################################################
# Makes a cmake internal library name from what comes in
########################################################################################################################
def make_nice_library_name(link_name):
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


########################################################################################################################
# Transform a list (of files) to a string
########################################################################################################################
def filelist_to_string(elements, source_directory, spacecount = 4):
    filelist = ""
    for file in sorted(elements):
        if os.path.isfile(source_directory + "/" + file):
            filelist += "\n" +" " * spacecount + "${CMAKE_CURRENT_SOURCE_DIR}/" + file
        else:
            filelist += "\n#" +" " * spacecount + "${CMAKE_CURRENT_SOURCE_DIR}/" + file + " # File not found. Fix manually"
            warning("WARNING!!! The file: " + source_directory + "/" + file + " is present in the Makefile.am but cannot be found in the filesystem")
    return filelist

########################################################################################################################
# processes the AC_CONFIG_FILES directive
########################################################################################################################
def process_config_files(line):
    s = line[len("AC_CONFIG_FILES("):].strip()
    s = remove_garbage(s)
    vec = s.split()
    for file in vec:
        makefile_am = working_directory + "/" + file + ".am"
        if os.path.isfile(makefile_am):
            process_makefile_am(makefile_am)


########################################################################################################################
# processes the configure.ac and creates some options for the outgoing CmakeLists.txt
########################################################################################################################
def process_configure_ac(fname):
    with open(fname) as f:
        content = f.readlines()

    function_list = {"AC_ARG_ENABLE": process_argument,
                     "AM_CONDITIONAL": process_conditional,
                     "AC_DEFINE": process_a_define,
                     "AC_CONFIG_FILES": process_config_files}

    current_line = ""
    previous_line = ""
    line_distance = 0
    for i in range(len(content)):
        # This is horrible.... but I want to keep the line with the "if" before the AC_DEFINE since that is the one
        # having the actual variable name, except for cases when not, so don't keep too old lines,
        # funny results will come out of it.
        if len(current_line) > 1 and '$' in current_line:
            previous_line = current_line
            line_distance = 0
        else:
            if line_distance < 3:
                if '$' in current_line:
                    previous_line = current_line
                    line_distance = 0
                else:
                    line_distance += 1
            else:
                previous_line = ""
                line_distance += 1

        current_line = content[i].strip()

        if current_line.startswith("#") or not current_line:
            continue

        # see if this is a variable defintion or not
        if '=' in current_line:
            if current_line[0].isalpha():
                # normal variable defintion, find the name
                j = 0
                varname = ""
                while current_line[j].isalnum() or current_line[j] == '_':
                    varname += current_line[j]
                    j += 1
                while current_line[j].isspace():
                    j += 1
                if current_line[j] == '=':
                    # this is actually a variable
                    var_value = ""
                    j += 1 # skip =
                    while j < len(current_line):
                        var_value += current_line[j]
                        j += 1
                    # do we have it?
                    if not varname in config_ac_variables:
                        config_ac_variables[varname] = {}
                        config_ac_variables[varname]["value"] = []
                    # Add it in there
                    config_ac_variables[varname]["value"].append(var_value)

        # And finally see if this is somethign we can work with
        method = processable_line(current_line)
        if method:
            full_line = ""
            while True:
                current_line = content[i].strip()
                full_line += current_line + " "
                # now start counting the open parenthesis
                parco = count_parentheses(full_line)
                if parco == 0:
                    # full AC_ARG line
                    break
                else:
                    # fetch continuously lines from the content till parco will become 0
                    i += 1
            # for AC_DEFINES we'll keep also the "if" line
            if method == "AC_DEFINE":
                full_line += previous_line
            parameters = {'line': full_line}
            function_list[method](**parameters)

    # now merge the global defines into the global options
    for option_name in options:
        option = options[option_name]
        for temp_define_name in temp_defines:
            temp_define = temp_defines[temp_define_name]
            enter = False
            if option.get_define() == temp_define["name"]:
                option.set_define_description(temp_define["description"])
                option.set_define_value(temp_define["value"])
                temp_define["used"] = 1
                enter = True
            if option.get_name() == temp_define["option_name"]:
                option.set_define(temp_define["name"])
                option.set_define_description(temp_define["description"])
                option.set_define_value(temp_define["value"])
                temp_define["used"] = 1
                enter = True
            if enter:
                break

    # Now let's see which are the temp defines that were not used and match them somehow to various options
    for temp_define_name in temp_defines:
        temp_define = temp_defines[temp_define_name]
        if temp_define["used"] == 0:
            # find an option which is similar to it:
            for option_name in options:
                option = options[option_name]
                td_upper = temp_define_name
                td_upper = td_upper.upper()
                opt_upper = option_name
                opt_upper= opt_upper.upper()
                sim_v = similar(td_upper, opt_upper)
                if (sim_v > 0.5) or (td_upper in opt_upper) or (opt_upper in td_upper):
                    option.add_extra_define(temp_define_name)
                    temp_define["used"] = 1

########################################################################################################################
# Generates default CMakeLists.txt in the given directory with content of source files
########################################################################################################################
def generate_default_cmake(req_dir):
    projname = req_dir.split("/")[-1] + ")\n"
    sources = "set (project "
    sources += projname
    sources += "set(${project}_SOURCES\n"
    files = glob.glob(req_dir + "/*.c*")
    for f in files:
        sources += "\t${CMAKE_CURRENT_SOURCE_DIR}/" + f.split("/")[-1] + "\n"
    files = glob.glob(req_dir + "/*.h*")
    for f in files:
        sources += "\t${CMAKE_CURRENT_SOURCE_DIR}/" + f.split("/")[-1] + "\n"

    sources += ")\n"

    r_cmake_file = open(req_dir + "/CMakeLists.txt", "w")
    r_cmake_file.write("cmake_minimum_required(VERSION 2.8)\n")
    r_cmake_file.write(sources)
    r_cmake_file.write("add_library(${project} STATIC ${${project}_SOURCES} )")
    r_cmake_file.close()

########################################################################################################################
# Adds extra content to the correct cmake file
########################################################################################################################
def process_cmake_file_directories():
    for dirname in extra_content:
        extra_c = extra_content[dirname]
        if not dirname in cmake_files:
            cmake_files[dirname] = CMakeFile(dirname)
        c_cmake_file = cmake_files[dirname]
        c_cmake_file.extra_content = extra_c

########################################################################################################################
# Will check if the incoming header file is a MOC header or not. Just scan for a Q_OBJECT macro in it
########################################################################################################################
def moc_header(fn):
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

########################################################################################################################
# Creates a CMakeLists project file from the given parameters
########################################################################################################################
def create_cmakefile(path, cpps, headers, module):

    # This will return: (bool, bool, bool)
    # Meaning: first bool: there were cpp files
    #          second bool: there were header files
    #          third bool: if set to process qt style moc headers and there were moc headers: true

    cpps_found = False
    headers_found = False
    mocs_found = False

    full_module = path[len(working_directory):]
    if len(full_module) > 1 and full_module[0] == '/':
        full_module = full_module[1:]
        full_module = full_module.replace("/", "_")

    f = open(pjoin(path,"CMakeLists.txt"), "w+")

    f.write("cmake_minimum_required(VERSION 2.8)\n")
    if full_module:
        f.write("set (project " + full_module + ")\n\n")
    else:
        f.write("set (project " + module + ")\n\n")
        full_module = module

    if cpps:
        cpps_found = True
        f.write("set(${project}_SOURCES\n")
        for fn in cpps:
            f.write("    ${CMAKE_CURRENT_SOURCE_DIR}/" + fn + "\n")
        f.write(")\n\n")

    moc_headers = []

    if headers:
        headers_found = True
        f.write("set(${project}_HEADERS\n")
        for fn in headers:
            if not moc_header(pjoin(path,fn)):
                f.write("    ${CMAKE_CURRENT_SOURCE_DIR}/" + fn + "\n")
            else:
                moc_headers.append(fn)
        f.write(")\n\n")

    if moc_headers:
        mocs_found = True
        f.write("set(${project}_MOC_HEADERS\n")
        for fn in moc_headers:
            f.write("    ${CMAKE_CURRENT_SOURCE_DIR}/" + fn + "\n")
        f.write(")\n\n")


    f.close()

    return cpps_found, headers_found, mocs_found, full_module

########################################################################################################################
# Converts a given directory to a CMake project
########################################################################################################################
def convert_sourcetree_to_cmake(start_path):

    print("Converting: {}".format(start_path))

    if ".git" in start_path:
        print("Not actually")
        return ""

    modules = []

    for path, dirs, files in os.walk(start_path):

        cpp_files = []
        header_files = []
        resource_files = []

        temp_module = os.path.basename(path)  # directory of file

        if ".git" in temp_module:
            continue

        for filename in files:
            full_name = os.path.join(path, filename)

            fn, ext = os.path.splitext(full_name)
            ext = ext.lower()
            if ext in cpp_extensions:
                cpp_files.append(filename)
            if ext in header_extensions:
                header_files.append(filename)
            if ext in qrc_extensions:
                resource_files.append(filename)

        cpps_found, headers_found, mocs_found, used_module = create_cmakefile(path, cpp_files, header_files, temp_module)

        # Now fix the cmake in the current directory to include the directories
        f = open(pjoin(path, "CMakeLists.txt"), "a")

        if recursive:
            for cdir in dirs:
                if ".git" in cdir:
                    continue
                f.write("add_subdirectory(" + cdir + ")\n")
                sub_module = convert_sourcetree_to_cmake(pjoin(path, cdir))
                if sub_module:
                    modules.append(sub_module)

        # See the cmake automoc status
        if mocs_found:
            if not cmake_automoc:
                f.write("qt_wrap_cpp(${project}_MOC_SOURCES ${${project}_MOC_HEADERS})\n")
            else:
                f.write("set(CMAKE_INCLUDE_CURRENT_DIR ON)\n")
                f.write("set(CMAKE_AUTOMOC ON)\n")

        if cpps_found or headers_found or mocs_found:
            f.write("add_library(${project} STATIC ")
        if cpps_found:
            f.write("${${project}_SOURCES} ")
        if headers_found:
            f.write("${${project}_HEADERS} ")

        if mocs_found:
            if not cmake_automoc:
                f.write("${${project}_MOC_SOURCES} ")
            else:
                f.write("${${project}_MOC_HEADERS}")

        if cpps_found or headers_found or mocs_found:
            f.write(")\n")

        if modules:
            f = open(pjoin(start_path, "CMakeLists.txt"), "a")

            f.write("\ntarget_link_libraries (${project}\n")

            for module in modules:
                if ".git" in module:
                    continue
                f.write("    " + module + "\n")

            f.write(")\n")

        if not recursive:
            exit(0)

    return used_module

########################################################################################################################
# Finds a list of files in the given directory
########################################################################################################################
def find_wildcard_file(fn, dir):
    fs = glob.glob(dir + "/" + fn)
    print(fs)
    return fs

########################################################################################################################
# converts the qmake solution in the given directory
########################################################################################################################
def convert_qmake_project(dir, fn):
    print("QMake project conversion coming shortly")
    exit(2)

########################################################################################################################
# converts the solution in the current directory
########################################################################################################################
def convert():

    global working_directory

    # If this is a quick conversion mode:
    # 1. Just gather the cpp files in the current directory
    # 2. Create a CMakeLists.txt from them
    if quick:
        if not working_directory:
            working_directory = os.getcwd()
        convert_sourcetree_to_cmake(working_directory)
        exit()

    # first step: search for configure.ac
    configure_ac = find_file("configure.ac", working_directory)
    if configure_ac:
        process_configure_ac(configure_ac)
    else:

        qmake_pro = find_wildcard_file("*.pro", working_directory)
        if qmake_pro:
            for current_qmake_pro in qmake_pro:
                convert_qmake_project(working_directory, current_qmake_pro)
            exit()

        if recursive:
            msg_rec = ""
        else:
            msg_rec = "non "
        warning(working_directory + "/configure.ac not found. Performing " + msg_rec + "recursive source dump in: " + working_directory)
        convert_sourcetree_to_cmake(working_directory)
        exit()

    # next step: write the options in a CMakeLists.txt for the gathered data
    cmake_file = open(working_directory + "/CMakeLists.txt", "w")
    if generate_comments:
        cmake_file.write("# Autogenerated by auto2cmake on {0}\n\n# Options\n\n".
                         format(time.strftime("%Y-%m-%d %H:%M:%S")))

    # let's not be very cmake hungry
    cmake_file.write("cmake_minimum_required(VERSION 2.8)\n")

    sorted_options = sorted(options.items(), key=lambda x: x[1].get_name(), reverse=False)
    for option in sorted_options:
        option[1].finalize()
        if generate_comments:
            cmake_file.write("# Option to {0}\n".format(option[1].get_description()))

        cmake_file.write("option( {0} \"{1}\" {2} )\n".format(option[1].get_name(), option[1].get_description(),
                                                               option[1].get_status()))
        if more_newlines:
            cmake_file.write("\n")

    # next step: write CMake code that will write the header config.h
    if generate_comments:
        cmake_file.write("# The lines below will generate the config.h based on the options above\n"
                         "# The file will be in the ${CMAKE_BINARY_DIR} location\n")

    cmake_file.write("set(CONFIG_H ${CMAKE_BINARY_DIR}/config.h)\n")
    cmake_file.write("string(TIMESTAMP CURRENT_TIMESTAMP)\n")
    cmake_file.write("file(WRITE ${CONFIG_H} \"/* WARNING: This file is auto-generated by CMake on ${CURRENT_TIMESTAMP}"
                     ". DO NOT EDIT!!! */\\n\\n\")\n")

    for option in sorted_options:
        cmake_file.write("if( {0} )\n".format(option[1].get_name()))
        cmake_file.write("    message(\" {0} Enabled\")\n".format(option[1].get_name()))
        cmake_file.write("    file(APPEND ${{CONFIG_H}} \"/* {0} */\\n\")\n".format(remove_garbage(option[1].get_define_description())))

        # some non-automata-conforming configure entries (the very verbose ones) do not have option name. Let's guess
        # them and prepend HAVE_ ... hopefully the programmers will fix them in their CMakeLists files
        if len(option[1].get_define()) >= 1:
            extra = remove_garbage(option[1].get_define_value())
            cmake_file.write("    file(APPEND ${{CONFIG_H}} \"#define {0} {1}\\n\\n\")\n".format(option[1].get_define(), replace_quotes(extra)))
        else:
            cmake_file.write("    file(APPEND ${{CONFIG_H}} \"#define HAVE_{0} \\n\\n\")\n".format(option[1].get_name()))

        # now put out the extra defines of the option
        for extra in option[1].get_extra_defines():
            extra_value = remove_garbage(extra)
            cmake_file.write("## !!! WARNING {0} Identified with some pattern matching magic.\n"
                             "## Remove if not relevant!\")\n".format(extra_value))
            cmake_file.write("    file(APPEND ${{CONFIG_H}} \"#define {0}\\n\\n\")\n".format(extra_value))

        cmake_file.write("endif( {0} )\n".format(option[1].get_name()))

    cmake_file.write("\n")
    cmake_file.write("## !!! WARNING These are the defines that were defined regardless of an option.\n"
                     "## !!! Or the script couldn't match them. Match them accordingly, delete them or keep them\n")

    # Now put out all the temp_defines that are still not used
    for temp_define_name in temp_defines:
        temp_define = temp_defines[temp_define_name]
        if temp_define["used"] == 0:
            extra_value = remove_garbage(temp_define["value"])
            cmake_file.write("file(APPEND ${{CONFIG_H}} \"/* {0} */\\n\")\n".format(remove_garbage(temp_define["description"])))
            cmake_file.write("file(APPEND ${{CONFIG_H}} \"#define {0} {1} \\n\\n \")\n".format(temp_define_name, replace_quotes(extra_value)))

    # since the config.h went into the ${CMAKE_BINARY_DIR} let's add that to the include directories
    cmake_file.write("\n")
    if generate_comments:
        cmake_file.write("# Setting the include directory for the application to find config.h\n")
    cmake_file.write("include_directories( ${CMAKE_BINARY_DIR} )")

    cmake_file.write("\n")
    if generate_comments:
        cmake_file.write("# Since we have created a config.h add a global define for it\n")
    cmake_file.write("add_definitions( \"-DHAVE_CONFIG_H\" )")

    cmake_file.close()

    # Done with the top level CMakeLists.txt generated from configure.ac

    # Let's process the libraries identified, put them in their own CMakeLists.txt
    process_libraries()

    # Now merge together the extra things with the library generated cmake files, create new if necessary
    process_cmake_file_directories()

    # Firstly remove all attempts that were there
    for cmakefile_name in cmake_files:
        cfile = cmake_files[cmakefile_name]
        if os.path.isfile(cfile.directory + "/CMakeLists.txt"):
            if working_directory != cfile.directory:
                os.remove(cfile.directory + "/CMakeLists.txt")

    # Now just write the CMakeLists.txt
    for cmakefile_name in cmake_files:
        cfile = cmake_files[cmakefile_name]
        new_cmake_file = open(cfile.directory + "/CMakeLists.txt", "a")
        if cfile.directory in required_directories:
            required_directories.remove(cfile.directory)
        new_cmake_file.write(cfile.extra_content)
        for content in cfile.contained_libraries_content:
            new_cmake_file.write(content)
        new_cmake_file.close()

    # Now see how many required directories did not got their own CMakeLists.txt
    # and generate in there manually, after removing the entries which are in the do not include list
    final_list = [x for x in required_directories if not should_exclude(x)]

    warning("WARNING!!! Creating default CMakeLists.txt in the directories below. Don't forget to fix these later")
    for req_dir in final_list:
        warning("Default CMakeLists.txt in:", req_dir)
        generate_default_cmake(req_dir)

########################################################################################################################
# Prints how to use the application
########################################################################################################################
def usage():
    print("auto2cmake - a tool to convert autotools/qmake projects to cmake\n")
    print("Usage: auto2cmake.py -d <working_directory> [-e <exclude_directories>] [-q] [-r] [-a] [-h]\n")
    print("Specify exclude_directories: separated by ':'")
    print("\nOther parameters:")
    print(" - q = quick mode, just convert the entire directory into a CMake project file. Ignores both automake\n"
          "       and qmake project files in the directory")
    print(" - r = used in quick mode, do a recursive directory walking")
    print(" - a = used in quick mode, use CMake automoc set to true instead of manual qt source wrapping")

########################################################################################################################
# main
########################################################################################################################
def main(argv):

    global working_directory
    global exclude_directories
    global quick
    global recursive
    global cmake_automoc

    try:
        opts, args = getopt.getopt(argv, "d:e:hqra", ["directory=,exclude="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            usage()
            sys.exit()
        if opt == "-d":
            working_directory = arg
            print("Start in: {}".format(working_directory))
        if opt == "-e":
            exclude_directories = arg.split(':')
        if opt == "-q":
            quick = True
        if opt == "-r":
            recursive = True
        if opt == "-a":
            cmake_automoc = True

    convert()

########################################################################################################################
#                                       Main entry point of the application                                            #
########################################################################################################################
if __name__ == "__main__":
    main(sys.argv[1:])
