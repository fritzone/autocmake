#!/usr/bin/env python3
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

def run_test(repo_url: str, project_name, packages_to_check: List[str], test_number: int, cmake_version: Optional[str], test_info: str = "Not Provided", test_should_fail: bool = False) -> bool:
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

    print(f"Action 1/5: Cloning the repository from: {repo_url}\n")

    res = run_command(command=f"git clone {repo_url}", packages_to_check=["git"])

    if (res.returncode != 0):
        print(f"Failure: Unable to clone {project_name}\n")
        print(f"Error:\n{res.stderr}\n")
        sys.exit()
        
    project_path = os.path.join(cwd, project_name)

    auto2cmake_py = os.path.join(repo_root, "auto2cmake.py")

    if not os.path.exists(project_path):
        print(f"Error: {project_path} does not exist.")
        sys.exit(1)

    print(f"Action 2/5: Cleaning up existing CMakeLists.txt in {project_name}\n")
    for root, dirs, files in os.walk(project_path):
        for file in files:
            if file == "CMakeLists.txt":
                os.remove(os.path.join(root, file))


    # Using -d to specify the working directory.
    test_command = f"python3 {auto2cmake_py} -d {project_path}"
    
    # Using -v to specify a CMake version override.
    test_command += f" -v {cmake_version}" if cmake_version is not None else test_command

    
    print(f"Action 3/5: Running auto2cmake.py for {project_name}")
    print(f"Command: {test_command}\n")
    
    res = run_command(test_command, command_should_fail=test_should_fail)

    if res.returncode != 0:
        # Handling the results of the test depending on the value passed to the parameter "test_should_fail"
        message_prefix = "SUCCESS: " if test_should_fail else "FAILURE: "
        message = "Test passed!\n\n" if test_should_fail else "Execution of auto2cmake.py failed.\n\n"
        
        print(message_prefix + message)
        return test_should_fail

    cmake_version_string = "CMake" + f" {cmake_version}" if cmake_version is not None else ""
    
    print(f"Action 4/5: Attempting to configure {project_name} using {cmake_version_string}\n")
    build_dir = os.path.join(cwd, f"{project_name}_build_test")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

    # Warning are expected, but aslong as the return code is 0, the conversion operation was successful.
    res = run_command(f"cmake -S {project_path} -B {build_dir}")
    
    if res.returncode == 0:
        print(f"SUCCESS: {project_name} configured with {cmake_version_string}!\n")
    else:
        print(f"FAILURE: Unable to configure {project_name} using {cmake_version_string}.\n")

    print("Action 5/5: Removing build artifacts associated with this test.\n")
    shutil.rmtree(project_path)
    shutil.rmtree(build_dir)
    print("SUCCESS: Removed build artifacts associated with this test.\n\n")
    return res.returncode == 0
    
    