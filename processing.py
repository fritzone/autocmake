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
import sys
import os
import re
import glob
import time
from os.path import join as pjoin

import variables
from classes import CMakeFile, TargetType, Library, Option
from utils import (
    warning, has_library, count_parentheses, replace_quotes, get_library_for_name, 
    similar, should_exclude, remove_garbage, find_file, make_nice_library_name, 
    filelist_to_string, find_wildcard_file, moc_header
)

# TODO: Refactor variable names for clarity and add comments documenting this workflow.
def process_argument(line):
    s = line[len("AC_ARG_ENABLE("):].strip()
    arg_name = ""
    for c in s:
        if c == ',':
            break
        arg_name += c
    description = ""
    for i in range(len(s)):
        if s[i] == '[':
            i += 1
            while s[i] == ' ' and i < len(s):
                i += 1
            while s[i] != ' ' and i < len(s):
                i += 1
            while s[i] == ' ' and i < len(s):
                i += 1
            while s[i] != ']' and i < len(s):
                description += s[i]
                i += 1
            break

    is_enabled = "OFF"
    if "=yes" in s:
        is_enabled = "ON"

    arg_name = arg_name.replace("-", "_")

    if not (arg_name in variables.options):
        variables.options[arg_name] = Option(arg_name, description, is_enabled, "", "", "")
    else:
        variables.options[arg_name].set_name(arg_name)
        variables.options[arg_name].set_description(description)
        variables.options[arg_name].set_status(is_enabled)


# Currently works as intended no work is required here as of 2026-07-21.
def processable_line(line):
    possible_starts = ["AC_ARG_ENABLE(", "AM_CONDITIONAL(", "AC_DEFINE(", "AC_CONFIG_FILES("]
    for start in possible_starts:
        if line.startswith(start):
            return start[:-1]
    return ""


# TODO: Refactor for clarity
def process_conditional(line):
    stripped_line = line[len("AM_CONDITIONAL("):].strip()
    define_name = ""
    for c in stripped_line:
        if c == ',':
            break
        define_name += c
    bound_option = ""
    stage = 1  # 1 - skipping, 2 - adding

    for c in stripped_line:
        if (c == '"' or c == ' ' or c == '=') and stage == 2: break
        if stage == 2: bound_option += c
        if c == '$': stage = 2

    bound_option = bound_option.replace("-", "_")

    if bound_option in variables.options:
        variables.options[bound_option].set_define(define_name)

    else:
        variables.options[bound_option] = Option(bound_option, "", "", define_name, "", "")


# Refactored on 2026-07-21 to address an conditional formatting bug.
def process_a_define(line):
    if not line.startswith("AC_DEFINE("):
        return
        
    stripped_line = line[len("AC_DEFINE("):].strip()
    define_string = ""
    defined_to_value = ""
    define_description = ""

    stage = 1  # 1: name, 2: value, 3: description
    sqp = 0    # The depth of the square bracket
    roup = 0   # The depth of the round parenthesis depth (This starts at 0 since '(' will be stripped below.)
    
    for c in stripped_line:
        if c == '[': sqp += 1
        elif c == ']': sqp -= 1
        elif c == '(': roup += 1
        elif c == ')':
            if roup == 0:
                break
            roup -= 1
        
        elif c == ',' and sqp == 0 and roup == 0:
            stage += 1
            continue  # Skips the inclusion of a comma for seperation.
        
        if stage == 1: define_string += c
        elif stage == 2: defined_to_value += c
        elif stage == 3: define_description += c

    # Sanitizing values to remove any leftover whitespace from the raw slicing operations.
    define_string = define_string.strip()
    defined_to_value = defined_to_value.strip()
    define_description = define_description.strip()
    
    # Extracting the name of the option from its value if the name contains a shell variable (example: '$var')
    variable_name = ""
    in_var = False

    for c in defined_to_value:
        
        if in_var:
            
            if c.isalnum() or c == '_':
                variable_name += c
            
            else:
                break
        
        elif c == '$':
            in_var = True

    variables.temp_defines[define_string] = {
        "name": define_string,
        "option_name": variable_name.upper(),
        "description": define_description,
        "value": defined_to_value,
        "used": 0
    }

# TODO: Refactor for clarity and break this into multiple smaller helper functions.
def process_makefile_am(file):
    if not os.path.isfile(file):
        warning("File not found:", file)
        return

    current_directory = os.path.dirname(file)

    if should_exclude(current_directory):
        return

    dirs_to_go_in = []
    defined_variables = {}
    libraries_in_this_file = []
    with open(file) as f:
        content = f.readlines()

    for line in content:
        line = line.strip()
        
        if line.startswith("#"):
            continue

        if line.find("_LIBRARIES") != -1 or line.find("_PROGRAMS") != -1:
            elements = line.split()
            library_names = elements[2:]
            makefiles_directory = current_directory
            process_it = True
            
            for excluded_directory in variables.excluded_directories:
                if makefiles_directory.startswith(excluded_directory) and excluded_directory:
                    process_it = False

            if process_it:
                for library_name in library_names:
                    library = Library(library_name, makefiles_directory)
                    
                    if line.find("_PROGRAMS") != -1:
                        library.target_type = TargetType.PROGRAM
                        library.referred_name = library.canonic_name
                    
                    if not has_library(library.canonic_name):
                        variables.libraries.append(library)

    if_condition = ""
    for i in range(len(content)):
        line = content[i].strip()
        if line.startswith("#"):
            continue

        if line.startswith("if"):
            elements = line.split()
            if_condition = elements[1]
        
        if line.startswith("endif"):
            if_condition = ""

        if '=' in line or "+=" in line:
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

            if variable.endswith("_SOURCES"):
                target_lib_name = variable[:-len("_SOURCES")]
                library = get_library_for_name(target_lib_name)

                if library:
                    used = True
                    libraries_in_this_file.append(target_lib_name)

                    if if_condition:
                        library.condition += if_condition

                    if "+=" in line:
                        library.filelist += elements[1].split()
                    else:
                        library.filelist = elements[1].split()

            if variable.endswith("_LDADD"):
                target_lib_name = variable[:-len("_LDADD")]
                library = get_library_for_name(target_lib_name)

                if library in variables.libraries:
                    used = True
                    libraries_in_this_file.append(target_lib_name)
                    
                    if if_condition:
                        library.condition += if_condition

                    if "+=" in line:
                        library.link_with_libs += elements[1].split()
                    else:
                        library.link_with_libs = elements[1].split()

            if variable.endswith("_CXXFLAGS") or variable.endswith("_CPPFLAGS") or variable.endswith("_CFLAGS"):
                if variable.endswith("_CFLAGS"):
                    target_lib_name = variable[:-len("_CFLAGS")]
                else:
                    target_lib_name = variable[:-len("_CXXFLAGS")]

                library = get_library_for_name(target_lib_name)

                if library in variables.libraries:
                    used = True
                    libraries_in_this_file.append(target_lib_name)

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
                target_lib_name = variable[:-len("_LDFLAGS")]
                library = get_library_for_name(target_lib_name)

                if library in variables.libraries:
                    used = True
                    libraries_in_this_file.append(target_lib_name)

                    if if_condition:
                        library.condition += if_condition
                    
                    if "+=" in line:
                        library.linker_flags += elements[1].split()
                    else:
                        library.linker_flags = elements[1].split()

            if not used:
                if variable == "SUBDIRS":
                    dirs_to_go_in = elements[1]
                
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

    if defined_variables:
        for var_name in defined_variables:
            for defined_lib_name in set(libraries_in_this_file):
                found = False
                library = get_library_for_name(defined_lib_name)

                for file in library.filelist:
                    inside_varname = "$(" + var_name + ")"
                    if file.find(inside_varname) != -1:
                        condition_iterable = zip(defined_variables[var_name]["condition"], defined_variables[var_name]["value"])
                        for condition, value in condition_iterable:
                            condition_name = remove_garbage(condition)
                            if condition_name in library.conditional_appends:
                                library.conditional_appends[condition_name].append(' '.join(value))
                            else:
                                library.conditional_appends[condition_name] = value
                            found = True
                        break
                if not found:
                    library.just_variables[var_name] = defined_variables[var_name]["value"]

    if dirs_to_go_in:
        extra_dir = ""
        for subdir in dirs_to_go_in.split():
            if not should_exclude(current_directory + "/" + subdir):
                if "$(" in subdir or "${" in subdir:
                    subdir = subdir.replace("$(", "${")
                    extra_dir += "\nif( " + subdir + " )\n    add_subdirectory( " + subdir + " )\nendif()"
                else:
                    extra_dir += "\nadd_subdirectory( " + subdir + " )"
                variables.required_directories.append(current_directory + "/" + subdir)
        variables.extra_content[current_directory] = extra_dir

# TODO: Refactor for clarity and break this into multiple smaller helper functions.
def process_libraries():
    for library in variables.libraries:
        current_content = ""
        added_files = []
        
        if variables.generate_comments:
            current_content += "# Generating the library " + library.name + "\n"
        
        current_content += "set(project \"" + library.referred_name + "\")\n\n"
        current_content += "set(${project} \"\")\n"
        condition_required = ""

        for condition in library.conditional_appends:
            conditional_append = library.conditional_appends[condition]
            
            if condition:
                used_condition = False
                
                for opt_name in variables.options:
                    option = variables.options[opt_name]

                    if option.get_define() == condition:
                        used_condition = True
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
                            file_list = "\n        ".join(conditional_append)
                            current_content += "    list(APPEND ${project}_SOURCES\n        " + file_list
                            added_files.append(file_list)

                        current_content += "\n    )\nendif()\n"

                if not used_condition:
                    condition_required = condition
                    current_content += "\nif(" + condition + ")\n"
                    file_list = "\n        ".join(conditional_append)
                    current_content += "    list(APPEND ${project}_SOURCES\n        " + file_list
                    current_content += "\n    )\nendif()\n"
                    added_files.append(file_list)

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

        if library.condition:
            condition_used = False

            for option in variables.options:
                
                if variables.options[option].get_define() == library.condition:
                    current_content += "if (" + variables.options[option].get_name() + ")\n"
                    condition_required = variables.options[option].get_name()
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
                filelist = filelist_to_string(library.filelist, library.directory)
                current_content += "    list(APPEND ${project}_SOURCES\n    " + filelist + ")\nendif()\n\n"
                added_files.append(filelist)
        
        else:
            filelist = filelist_to_string(library.filelist, library.directory)
            work_list = filelist.strip()
            current_content += "list(APPEND ${project}_SOURCES\n    " + work_list + "\n)\n"
            added_files.append(work_list)

        # Do not remove the else clause here.
        # This will reintroduce a bug that causes:
        #   - add_executable and add_library to be wrapped in a conditional.
        #   - Compilation issues due to incorrect syntax.
        
        if library.condition:
            condition_required = library.condition
        else:
            condition_required = ""

        if condition_required:
            current_content += "if (" + condition_required + ")\n"
        
        has_libraries = False
        
        for file in added_files:
            lines = file.split('\n')
            
            for raw_line in lines:
                line = raw_line.strip()
                
                if line and not line.startswith('#'):
                    has_libraries = True
                    break
            
            if has_libraries:
                break

        if has_libraries:
            
            if library.target_type == TargetType.LIBRARY:
                current_content += "add_library ( " +library.referred_name + \
                                   " " + library.type + " " +  "${${project}_SOURCES} )\n"
            else:
                current_content += "add_executable(" + library.referred_name + " ${${project}_SOURCES} )\n"

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
                        match = re.search(r"\$\(.*\)", flag)
                        
                        if match:
                            desired_var = remove_garbage(match.group(0))
                            
                            if desired_var == "top_srcdir":
                                to_work_with_flags.append("{CMAKE_SOURCE_DIR}")
                            
                            elif desired_var in variables.config_ac_variables:
                                for v in variables.config_ac_variables[desired_var]["value"]:
                                    final_flags.append(v)

                    if flag in to_work_with_flags:
                        to_work_with_flags.remove(flag)

                done = True
                for flag in to_work_with_flags:
                    if '$' in flag:
                        done = False

            include_directories = []
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

            if library.link_with_libs:
                final_link_list = "\ntarget_link_libraries( " + library.referred_name
                
                for link_name in library.link_with_libs:
                    target_link_lib = make_nice_library_name(link_name)
                    
                    if target_link_lib.startswith("$"):
                        clean_tll_name = remove_garbage(target_link_lib)
                        
                        if clean_tll_name in library.just_variables:
                            
                            for more_link_names_list in library.just_variables[clean_tll_name]:
                                
                                for real_link in more_link_names_list:
                                    final_link_list += "\n    " + make_nice_library_name(real_link)
                    else:
                        
                        if target_link_lib.startswith("@"):
                            canname = target_link_lib.replace("@", '')
                            
                            if canname in variables.config_ac_variables:
                                libs = variables.config_ac_variables[canname]["value"]
                                
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
        
        else:
            warning("No source files found for ", library.referred_name, ". Skipping target generation." )

        if condition_required:
            current_content += "\nendif()\n"

        if not library.directory in variables.cmake_files:
            variables.cmake_files[library.directory] = CMakeFile(library.directory)

        cmake_file_holder = variables.cmake_files[library.directory]
        cmake_file_holder.contained_libraries_content.append(current_content)
        cmake_file_holder.libraries.append(library)

# TODO: Refactor variable names in this function for added clarity.
def process_config_files(line):
    s = line[len("AC_CONFIG_FILES("):].strip()
    s = remove_garbage(s)
    vec = s.split()
    
    for file in vec:
        makefile_am = variables.working_directory + "/" + file + ".am"
        
        if os.path.isfile(makefile_am):
            process_makefile_am(makefile_am)

# TODO: Refactor variable names for clarity and break this into multiple smaller helper functions.
def process_configure_ac(fname):
    """Processes the configure.ac and creates some options for the outgoing CmakeLists.txt"""
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

        if '=' in current_line:

            if current_line[0].isalpha():
                j = 0
                varname = ""

                while current_line[j].isalnum() or current_line[j] == '_':
                    varname += current_line[j]
                    j += 1

                while current_line[j].isspace():
                    j += 1

                if current_line[j] == '=':
                    var_value = ""
                    j += 1

                    while j < len(current_line):
                        var_value += current_line[j]
                        j += 1

                    if not varname in variables.config_ac_variables:
                        variables.config_ac_variables[varname] = {}
                        variables.config_ac_variables[varname]["value"] = []

                    variables.config_ac_variables[varname]["value"].append(var_value)

        method = processable_line(current_line)
        if method:
            full_line = ""
            while True:

                current_line = content[i].strip()
                full_line += current_line + " "
                parco = count_parentheses(full_line)

                if parco == 0:
                    break

                else:
                    i += 1

            if method == "AC_DEFINE":
                full_line += previous_line

            parameters = {'line': full_line}
            function_list[method](**parameters)

    for option_name in variables.options:
        option = variables.options[option_name]

        for temp_define_name in variables.temp_defines:
            temp_define = variables.temp_defines[temp_define_name]
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

    for temp_define_name in variables.temp_defines:
        temp_define = variables.temp_defines[temp_define_name]

        if temp_define["used"] == 0:

            for option_name in variables.options:
                option = variables.options[option_name]
                td_upper = temp_define_name
                td_upper = td_upper.upper()
                opt_upper = option_name
                opt_upper= opt_upper.upper()
                sim_v = similar(td_upper, opt_upper)

                if (sim_v > 0.5) or (td_upper in opt_upper) or (opt_upper in td_upper):
                    option.add_extra_define(temp_define_name)
                    temp_define["used"] = 1

# TODO: Add comments documenting this workflow.
def generate_default_cmake(req_dir):
    """Generates default CMakeLists.txt in the given directory with content of source files"""
    projname = req_dir.split("/")[-1]
    sources = "set (project " + projname + ")\n"
    sources += "set(${project}_SOURCES\n"
    has_code = False
    files = glob.glob(req_dir + "/*.c*")

    if files:
        has_code = True

    for f in files:
        sources += "\t${CMAKE_CURRENT_SOURCE_DIR}/" + f.split("/")[-1] + "\n"

    files = glob.glob(req_dir + "/*.h*")

    for f in files:
        sources += "\t${CMAKE_CURRENT_SOURCE_DIR}/" + f.split("/")[-1] + "\n"

    sources += ")\n"

    r_cmake_file = open(req_dir + "/CMakeLists.txt", "w")
    r_cmake_file.write(f"cmake_minimum_required(VERSION {variables.cmake_minimum_version})\n")

    if has_code:
        r_cmake_file.write(sources)
        r_cmake_file.write("add_library(${project} STATIC ${${project}_SOURCES} )")

    r_cmake_file.close()

# TODO: Add comments documenting this workflow.
def process_cmake_file_directories():
    """Adds extra content to the correct cmake file"""
    for dirname in variables.extra_content:
        extra_c = variables.extra_content[dirname]

        if not dirname in variables.cmake_files:
            variables.cmake_files[dirname] = CMakeFile(dirname)

        c_cmake_file = variables.cmake_files[dirname]
        c_cmake_file.extra_content = extra_c

# TODO: Refactor variable names for clarity and add comments documenting this workflow.
def create_cmakefile(path, cpps, headers, module):
    cpps_found = False
    headers_found = False
    mocs_found = False

    full_module = path[len(variables.working_directory):]
    if len(full_module) > 1 and full_module[0] == '/':
        full_module = full_module[1:]
        full_module = full_module.replace("/", "_")

    f = open(pjoin(path,"CMakeLists.txt"), "w+")

    f.write(f"cmake_minimum_required(VERSION {variables.cmake_minimum_version})\n")
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

# TODO: Add comments for clarity and break this into multiple smaller helper functions.
def convert_sourcetree_to_cmake(start_path):
    print("Converting: {}".format(start_path))

    if ".git" in start_path:
        print("Not actually")
        return ""

    modules = []
    
    try:
        source_tree_entries = os.listdir(start_path)
    except OSError:
        return ""

    cpp_files = []
    header_files = []
    resource_files = []
    dirs = []

    for source_tree_entry in source_tree_entries:
        full_path = pjoin(start_path, source_tree_entry)

        if os.path.isfile(full_path):
            file_name, file_extension = os.path.splitext(source_tree_entry)
            file_extension = file_extension.lower()

            if file_extension in variables.cpp_extensions:
                cpp_files.append(source_tree_entry)
            
            if file_extension in variables.header_extensions:
                header_files.append(source_tree_entry)

            if file_extension in variables.qrc_extensions:
                resource_files.append(source_tree_entry)

        elif os.path.isdir(full_path) and source_tree_entry != ".git":
            dirs.append(source_tree_entry)

    temp_module = os.path.basename(start_path)
    cpps_found, headers_found, mocs_found, used_module = create_cmakefile(
        start_path, 
        cpp_files, 
        header_files, 
        temp_module
    )

    f = open(pjoin(start_path, "CMakeLists.txt"), "a")

    if variables.recursive:
        for cdir in sorted(dirs):
            f.write("add_subdirectory(" + cdir + ")\n")
            sub_module_path = pjoin(start_path, cdir)
            sub_module = convert_sourcetree_to_cmake(sub_module_path)
            
            if sub_module:
                modules.append(sub_module)

    if mocs_found:

        if not variables.cmake_automoc:
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
            if not variables.cmake_automoc:
                f.write("${${project}_MOC_SOURCES} ")
            else:
                f.write("${${project}_MOC_HEADERS}")

        f.write(")\n")

    if modules:
        f.write("\ntarget_link_libraries (${project}\n")
        
        for module in modules:
            f.write("    " + module + "\n")

        f.write(")\n")

    f.close()
    return used_module


# TODO: Add comments and rename variables for clarity also break this into multiple smaller helper functions.
def convert_qmake_project(dir, fn):
    print("\nQMake project started in {} for {}".format(dir, fn))
    with open(fn) as f:
        content = f.readlines()
    content = [x.strip() for x in content]

    new_content = []
    i = 0

    while i < len(content):
        cl = content[i]

        if cl:

            if cl[0] == '#':
                i = i + 1
                continue

            if cl.endswith('\\'):
                cl = cl[:-1]
                j = i + 1
                nl = content[j]
                while nl.endswith('\\'):
                    nl = nl[:-1]
                    cl += nl.strip()
                    cl += " "
                    j = j + 1
                    nl = content[j]
                i = j

            new_content.append(cl)

        i = i + 1

    for l in new_content:
        print(l)

    qmake_proj_type = ""
    qmake_prj_subdirs = []
    qmake_prj_headers = []
    qmake_target_name = ""
    qmake_required_qt = {"core", "gui"}
    qvars = {}

    for l in new_content:
        clp = l.split('=')
        clp = [x.strip() for x in clp]

        print(clp)
        if clp and len(clp) > 1:

            if clp[0].upper() == "TEMPLATE":
                qmake_proj_type = clp[1]

            elif clp[0].upper() == "TARGET":
                qmake_target_name = clp[1]

            elif clp[0].upper().startswith("QT"):
                if clp[0].endswith('+'):
                    clp1s = clp[1].split()
                    for c in clp1s:
                        qmake_required_qt.add(c)

                elif clp[0].endswith('-'):
                    clp1s = clp[1].split()
                    for c in clp1s:
                        qmake_required_qt.remove(c)
                else:
                    qmake_required_qt.clear()
                    clp1s = clp[1].split()
                    for c in clp1s:
                        qmake_required_qt.add(c)
            else: 
                clp1s = clp[1].split()
                clp1s = [x.strip() for x in clp1s]
                qvars[clp[0]] = clp1s

    print("\nConverting\nProject type: {}".format(qmake_proj_type))
    print(qvars)

    if qmake_proj_type == "subdirs":
        print("subdirs project type not supported yet")
        sys.exit(2)

    cmake_file = open(dir + "/CMakeLists.txt", "w")
    cmake_file.write("# Autogenerated by auto2cmake on {0}\n\n".format(time.strftime("%Y-%m-%d %H:%M:%S")))
    cmake_file.write(f"cmake_minimum_required(VERSION {variables.cmake_minimum_version})\n\n")
    
    cmake_file.write("project (${project})\n\n")
    cmake_file.write("set(project \"" + qmake_target_name + "\")\n")

    if qmake_required_qt:
        req_qt_comps = "find_package(Qt5 COMPONENTS "

        for comp in qmake_required_qt:
            req_qt_comps += comp.capitalize() + " "

        req_qt_comps += "REQUIRED)\n"
        cmake_file.write(req_qt_comps)

    srcs = []
    for k in qvars.keys():
        if k.startswith("SOURCES"):
            srcs = qvars[k]
            break

    if srcs:
        cmake_file.write("\nset(${project}_SOURCES\n")
        for src in srcs:
            cmake_file.write("\t" + "${CMAKE_CURRENT_SOURCE_DIR}/" + src.strip() + "\n")

        cmake_file.write(")\n\n")

    headers = []
    for k in qvars.keys():
        if k.startswith("HEADERS"):
            headers = qvars[k]
            break

    moc_headers = []

    if headers:
        cmake_file.write("\nset(${project}_HEADERS\n")
        for header in headers:

            if header.startswith('$$'):
                varname = header[2:]
                found = False

                for vn in qvars.keys():

                    if vn.startswith(varname):
                        vv = qvars[vn]
                        found = True

                        for v in vv:
                            fn = v.strip()

                            if not moc_header(pjoin(variables.working_directory, fn)):
                                cmake_file.write("\t" + "${CMAKE_CURRENT_SOURCE_DIR}/" + fn + "\n")

                            else:

                                if not variables.cmake_automoc:
                                    moc_headers.append(fn)

                                else:
                                    cmake_file.write("\t" + "${CMAKE_CURRENT_SOURCE_DIR}/" + fn + "\n")

                        break

                if not found:
                    print("Error in qmake: var {} not found".format(vn))

            else:
                cmake_file.write("\t" + "${CMAKE_CURRENT_SOURCE_DIR}/" + header.strip() + "\n")

        cmake_file.write(")\n\n")

    if not variables.cmake_automoc:
        cmake_file.write("set(${project}_MOC_HEADERS\n")

        for mh in moc_headers:
            fn = mh.strip()
            cmake_file.write("\t" + "${CMAKE_CURRENT_SOURCE_DIR}/" + fn + "\n")

        cmake_file.write(")\n")
        cmake_file.write("qt_wrap_cpp( ${project}_MOC_SOURCES ${${project}_MOC_HEADERS} )\n")

    else:
        cmake_file.write("set(CMAKE_INCLUDE_CURRENT_DIR ON)\n")
        cmake_file.write("set(CMAKE_AUTOMOC ON)\n")

    resources = []
    for k in qvars.keys():

        if k.startswith("RESOURCES"):
            resources = qvars[k]
            break

    res_to_add = []
    if resources:
        cmake_file.write("\nset(CMAKE_AUTORCC ON)\n")

        for resource in resources:
            res_file = resource
            res_file_name = os.path.basename(resource)
            res_pieces = res_file_name.split('.')
            res_name = res_pieces[0]
            cmake_file.write("set_property(SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/%s PROPERTY AUTORCC_OPTIONS \"-name;%s\")" % (res_file, res_name))
            res_to_add.append(res_file)

    if qmake_proj_type.upper() == "APP":
        cmake_file.write("\n\nadd_executable( ${project} ${${project}_SOURCES} ")

    if qmake_proj_type.upper() == "LIB":
        cmake_file.write("\n\nadd_library( ${project} ${${project}_SOURCES} ")

    if res_to_add:
        for res in res_to_add:
            cmake_file.write("${CMAKE_CURRENT_SOURCE_DIR}/%s " % (res))

    cmake_file.write(")\n")
    cmake_file.close()
    sys.exit(0)

# TODO: Add comments for clarity and break this into multiple smaller helper functions.
def convert():
    if variables.quick:

        if not variables.working_directory:
            variables.working_directory = os.getcwd()

        convert_sourcetree_to_cmake(variables.working_directory)
        sys.exit()

    configure_ac = find_file("configure.ac", variables.working_directory)
    if configure_ac:
        process_configure_ac(configure_ac)

    else:
        qmake_pro = find_wildcard_file("*.pro", variables.working_directory)

        if qmake_pro:

            for current_qmake_pro in qmake_pro:
                convert_qmake_project(variables.working_directory, current_qmake_pro)

            sys.exit(0)

        if variables.recursive:
            msg_rec = ""

        else:
            msg_rec = "non "

        warning(variables.working_directory + "/configure.ac not found. Performing " + msg_rec + "recursive source dump in: " + variables.working_directory)
        convert_sourcetree_to_cmake(variables.working_directory)
        sys.exit()

    cmake_file = open(variables.working_directory + "/CMakeLists.txt", "w")

    if variables.generate_comments:
        cmake_file.write("# Autogenerated by auto2cmake on {0}\n\n# Options\n\n".
                         format(time.strftime("%Y-%m-%d %H:%M:%S")))

    cmake_file.write(f"cmake_minimum_required(VERSION {variables.cmake_minimum_version})\n")

    project_working_directory = os.path.basename(os.path.normpath(variables.working_directory))
    cmake_file.write("project({0})\n".format(project_working_directory))

    sorted_options = sorted(variables.options.items(), key=lambda x: x[1].get_name(), reverse=False)
    
    for option in sorted_options:
        option[1].finalize()
        clean_name = remove_garbage(option[1].get_name())
        clean_desc = remove_garbage(option[1].get_description())

        if variables.generate_comments:
            cmake_file.write("# Option to {0}\n".format(clean_desc))

        cmake_file.write("option( {0} \"{1}\" {2} )\n".format(
            clean_name,
            replace_quotes(clean_desc),
            option[1].get_status())
        )

        if variables.more_newlines:
            cmake_file.write("\n")

    if variables.generate_comments:
        cmake_file.write("# The lines below will generate the config.h based on the options above\n"
                         "# The file will be in the ${CMAKE_BINARY_DIR} location\n")

    cmake_file.write("set(CONFIG_H ${CMAKE_BINARY_DIR}/config.h)\n")
    cmake_file.write("string(TIMESTAMP CURRENT_TIMESTAMP)\n")
    cmake_file.write("file(WRITE ${CONFIG_H} \"/* WARNING: This file is auto-generated by CMake on ${CURRENT_TIMESTAMP}"
                     ". DO NOT EDIT!!! */\\n\\n\")\n")

    for option in sorted_options:
        cmake_file.write("if( {0} )\n".format(option[1].get_name()))
        cmake_file.write("    message(\" {0} Enabled\")\n".format(option[1].get_name()))

        sanitized_option_data = replace_quotes(remove_garbage(option[1].get_define_description()))
        cmake_file.write("    file(APPEND ${{CONFIG_H}} \"/* {0} */\\n\")\n".format(sanitized_option_data))

        if len(option[1].get_define()) >= 1:
            extra = remove_garbage(option[1].get_define_value())
            cmake_file.write("    file(APPEND ${{CONFIG_H}} \"#define {0} {1}\\n\\n\")\n".format(option[1].get_define(), replace_quotes(extra)))
        
        else:
            cmake_file.write("    file(APPEND ${{CONFIG_H}} \"#define HAVE_{0} \\n\\n\")\n".format(option[1].get_name()))

        for extra in option[1].get_extra_defines():
            extra_value = remove_garbage(extra)
            cmake_file.write("    message(\"## !!! WARNING {0} Identified with some pattern matching magic.\\n"
                             "## Remove if not relevant!\")\n".format(extra_value))
            cmake_file.write("    file(APPEND ${{CONFIG_H}} \"#define {0}\\n\\n\")\n".format(extra_value))

        cmake_file.write("endif( {0} )\n".format(option[1].get_name()))

    cmake_file.write("\n")
    cmake_file.write("## !!! WARNING These are the defines that were defined regardless of an option.\n"
                     "## !!! Or the script couldn't match them. Match them accordingly, delete them or keep them\n")

    for temp_define_name in variables.temp_defines:
        temp_define = variables.temp_defines[temp_define_name]
        
        if temp_define["used"] == 0:
            extra_value = remove_garbage(temp_define["value"])
            extra_description = replace_quotes(remove_garbage(temp_define["description"]))
            cmake_file.write("file(APPEND ${{CONFIG_H}} \"/* {0} */\\n\")\n".format(extra_description))
            cmake_file.write("file(APPEND ${{CONFIG_H}} \"#define {0} {1} \\n\\n \")\n".format(temp_define_name, replace_quotes(extra_value)))

    cmake_file.write("\n")
    
    if variables.generate_comments:
        cmake_file.write("# Setting the include directory for the application to find config.h\n")
    
    cmake_file.write("include_directories( ${CMAKE_BINARY_DIR} )")

    cmake_file.write("\n")
    
    if variables.generate_comments:
        cmake_file.write("# Since we have created a config.h add a global define for it\n")
    
    cmake_file.write("add_definitions( \"-DHAVE_CONFIG_H\" )")

    cmake_file.close()

    process_libraries()
    process_cmake_file_directories()

    for cmakefile_name in variables.cmake_files:
        cfile = variables.cmake_files[cmakefile_name]
        
        if os.path.isfile(cfile.directory + "/CMakeLists.txt"):
            
            if variables.working_directory != cfile.directory:
                os.remove(cfile.directory + "/CMakeLists.txt")

    for cmakefile_name in variables.cmake_files:
        cfile = variables.cmake_files[cmakefile_name]
        new_cmake_file = open(cfile.directory + "/CMakeLists.txt", "a")
        
        if cfile.directory in variables.required_directories:
            variables.required_directories.remove(cfile.directory)
        new_cmake_file.write(cfile.extra_content)
        
        for content in cfile.contained_libraries_content:
            new_cmake_file.write(content)
        new_cmake_file.close()

    final_list = [x for x in variables.required_directories if not should_exclude(x) and os.path.isdir(x)]

    if final_list:
        warning("WARNING!!! Creating default CMakeLists.txt in the directories below. Don't forget to fix these later")
        
        for req_dir in final_list:
            warning("Default CMakeLists.txt in:", req_dir)
            generate_default_cmake(req_dir)