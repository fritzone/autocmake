#!/usr/bin/env python3
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
sys.dont_write_bytecode = True

import os, subprocess, shutil
from typing import List, Optional

cwd = os.getcwd()

def run_command(command: str, cwd=cwd, packages_to_check=[], command_should_fail: bool = False, capture_output: bool = True):
    for package in packages_to_check:

        if not shutil.which(package):
            print(f"Unable to locate '{package}' in the current system's path.")
            sys.exit()
    
    result = subprocess.run(args=command, shell=True, capture_output=True, text=True, cwd=cwd)

    if result.returncode != 0 and not command_should_fail:
        print(f"Command failed with return code: {result.returncode}")
        print(result.stdout)
        print(result.stderr)

    return result

def run_test(repo_url: str, project_name, packages_to_check: List[str], test_number: int, cmake_version: Optional[str], test_info: str = "Not Provided", test_should_fail: bool = False, keep_test_artifacts: bool = False, skip_test: bool = False, recursive_scan: bool = False) -> bool:
    
    if skip_test:
        print(f"Skipping Test #{test_number}")
        return False
    
    print(f"Running Test #{test_number}")
    print(f"Test Description: {test_info}\n")

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    project_root = os.path.join(repo_root, project_name)
    
    if (os.path.exists(project_root)):
        print(f"Deleting old test artifact at: {repo_root}")
        try:
            shutil.rmtree(project_root)
            print("Deleted old test artifact.\n")
        except Exception as e:
            print("Unable to remove old test artifacts.")
            print("Please delete the directory manually.")
            print(f"Error Log: {e}\n")

    print(f"Action 1/6: Cloning the repository from: {repo_url}\n")

    res = run_command(command=f"git clone {repo_url}", packages_to_check=["git"])

    if (res.returncode != 0):
        print(f"Failure: Unable to clone {project_name}\n")
        print(f"Error:\n{res.stderr}\n")
        sys.exit()
        
    project_path = os.path.join(cwd, project_name)

    auto2cmake_py = os.path.join(repo_root, "main.py")

    if not os.path.exists(project_path):
        print(f"Error: {project_path} does not exist.")
        sys.exit(1)

    print(f"Action 2/6: Cleaning up existing CMakeLists.txt in {project_name}\n")
    for root, dirs, files in os.walk(project_path):
        for file in files:
            if file == "CMakeLists.txt":
                os.remove(os.path.join(root, file))


    # Using -d to specify the working directory.
    test_command = f"python3 {auto2cmake_py} -d {project_path}"
    
    # Using -v to specify a CMake version override.
    test_command += f" -v {cmake_version}" if cmake_version is not None else test_command
    
    # Using -r if recursive_scan is set to True.
    test_command += f" -r" if recursive_scan else test_command

    
    print(f"Action 3/6: Running auto2cmake.py for {project_name}")
    print(f"Command: {test_command}\n")
    
    res = run_command(test_command, command_should_fail=test_should_fail)

    if res.returncode != 0:
        # Handling the results of the test depending on the value passed to the parameter "test_should_fail"
        message_prefix = "SUCCESS: " if test_should_fail else "FAILURE: "
        message = "Test passed!\n\n" if test_should_fail else "Execution of auto2cmake.py failed.\n\n"
        
        print(message_prefix + message)
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
        return test_should_fail

    cmake_version_string = "CMake" + f" {cmake_version}" if cmake_version is not None else ""
    
    print(f"Action 4/6: Attempting to configure {project_name} using {cmake_version_string}\n")
    build_dir = os.path.join(cwd, f"{project_name}_build_test")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

    # Warning are expected, but aslong as the return code is 0, the conversion operation was successful.
    res = run_command(f"cmake -S {project_path} -B {build_dir}")
    
    # Tracking the status of both the config and build phases
    test_passed = False 

    if res.returncode == 0:
        print(f"SUCCESS: {project_name} configured with {cmake_version_string}!\n")
        
        build_cmd = f"cmake --build {build_dir}"
        print(f"Action 5/6: Attempting to compile {project_name}\nCommand: {build_cmd}\n")
        
        # Attempting to compile the newly translate project.
        # If this fails, then the translation done in processing.py needs to be refactored further.
        build_res = run_command(build_cmd)
        
        if build_res.returncode == 0:
            print(f"SUCCESS: {project_name} compiled successfully!\n")
            test_passed = True
        else:
            print(f"FAILURE: Unable to compile {project_name}, exit code {build_res.returncode}.\n")
            
    else:
        print(f"FAILURE: Unable to configure {project_name} using {cmake_version_string}.\n")

    print("Action 6/6: Removing build artifacts associated with this test.\n")
    
    if not keep_test_artifacts:
        shutil.rmtree(project_path)
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir)
    
    print("SUCCESS: Removed build artifacts associated with this test.\n\n")
    return test_passed
    
    