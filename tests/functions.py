#!/usr/bin/env python3
import sys
sys.dont_write_bytecode = True

import os, subprocess, shutil
from typing import List

cwd = os.getcwd()

def run_command(command: str, cwd=cwd, packages_to_check=[]):
    for package in packages_to_check:

        if not shutil.which(package):
            print(f"Unable to locate '{package}' in the current system's path.")
            sys.exit()
    
    result = subprocess.run(args=command, shell=True, capture_output=True, text=True, cwd=cwd)

    if result.returncode != 0:
        print(f"Command failed with return code {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")

    return result

def run_test(repo_url: str, project_name, packages_to_check: List[str], test_number: int) -> bool:
    print(f"Running Test #{test_number}\n")

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
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

    print("Action 2/5: Cleaning up existing CMakeLists.txt in gnupg\n")
    for root, dirs, files in os.walk(project_path):
        for file in files:
            if file == "CMakeLists.txt":
                os.remove(os.path.join(root, file))

    print(f"Action 3/5: Running auto2cmake.py for {project_name}\n")

    # Using -d to specify the directory
    res = run_command(f"python3 {auto2cmake_py} -d {project_path}")
    if res.returncode != 0:
        print("auto2cmake.py failed.")
        sys.exit(1)

    print(f"Action 4/5: Attempting to configure {project_name} using CMake\n")
    build_dir = os.path.join(cwd, f"{project_name}_build_test")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

    # Warning are expected, but aslong as the return code is 0, the conversion operation was successful.
    res = run_command(f"cmake -S {project_path} -B {build_dir}")
    
    if res.returncode == 0:
        print(f"SUCCESS: {project_name} configured with CMake!\n")
    else:
        print("FAILURE: CMake configuration failed.\n")

    print("Action 5/5: Removing build artifacts associated with this test.\n")
    shutil.rmtree(project_path)
    shutil.rmtree(build_dir)
    print("SUCCESS: Removed build artifacts associated with this test.\n\n")
    return res.returncode == 0
    
    