#!/usr/bin/env python3
import sys
sys.dont_write_bytecode = True

from functions import run_test

passed_tests = 0
total_tests = 0

if __name__ == "__main__":
    tests = [
    {
        "args": {
            "repo_url": "https://github.com/gpg/gnupg", 
            "project_name": "gnupg"
        },
        "result": run_test(
            repo_url="https://github.com/gpg/gnupg", 
            project_name="gnupg", 
            packages_to_check=["git"], 
            test_number=1,
            test_info="Testing compatibility with gnupg using a supported legacy version of CMake (3.1)",
            cmake_version="3.1"
        )
    },

    {
        "args": {
            "repo_url": "https://github.com/python/cpython", 
            "project_name": "cpython"
        },
        "result": run_test(
            repo_url="https://github.com/python/cpython", 
            project_name="cpython", 
            packages_to_check=["git"],
            test_number=2,
            test_info="Testing compatibility with cpython, which caused issues in older releases of auto2cmake.",
            cmake_version="3.28.3"
        )
    },

    {
        "args": {
            "repo_url": "https://github.com/gpg/gnupg", 
            "project_name": "gnupg"
        },
        "result": run_test(
            repo_url="https://github.com/gpg/gnupg", 
            project_name="gnupg", 
            packages_to_check=["git"],
            test_number=3,
            test_info="Testing the version parsing logic against an unsupported version of CMake (2.7)",
            cmake_version="2.7",
            test_should_fail=True
        )
    },

    {
        "args": {
            "repo_url": "https://github.com/gpg/gnupg", 
            "project_name": "gnupg"
        },
        "result": run_test(
            repo_url="https://github.com/gpg/gnupg", 
            project_name="gnupg", 
            packages_to_check=["git"],
            test_number=4,
            test_info="Testing the version parsing logic against an unreleased version of CMake (6.9)",
            cmake_version="6.9",
            test_should_fail=True
        )
    },

    ]
    
    for response in tests:
        total_tests += 1

        if response['result']:
            passed_tests += 1
            print(f"Test #{total_tests}: Passed")
        
        else:
            print(f"Test #{total_tests}: Failed")


    
    failed_tests = total_tests - passed_tests

    # A compound conditional operation is used here to avoid a "ZeroDivisionError" 
    success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
    failure_rate = (failed_tests / total_tests) * 100 if total_tests > 0 else 0

    print("\n\n\n")
    print("======================================")
    print("Test Statistics")
    print("======================================")
    print(f"Total Tests: {total_tests}")
    print(f"Passed Tests: {passed_tests}")
    print(f"Failed Tests: {failed_tests}")
    print()
    print(f"Success Rate: {round(success_rate, 2)}%")
    print(f"Failure Rate: {round(failure_rate, 2)}%")