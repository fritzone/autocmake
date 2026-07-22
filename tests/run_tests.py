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
            cmake_version="3.1",
            # skip_test=True,
            recursive_scan=True
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
            cmake_version="3.28.3",
            # skip_test=True,
            # keep_test_artifacts=True,
            recursive_scan=True
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
            test_should_fail=True,
            # skip_test=True,
            recursive_scan=True
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
            test_should_fail=True,
            # skip_test=True,
            recursive_scan=True
        )
    },

    {
        "args": {
            "repo_url": "https://github.com/strongswan/strongswan", 
            "project_name": "strongswan"
        },
        "result": run_test(
            repo_url="https://github.com/strongswan/strongswan", 
            project_name="strongswan", 
            packages_to_check=["git"],
            test_number=5,
            test_info="Testing another large project recommended by Autotools users.",
            cmake_version="3.28.3",
            test_should_fail=False,
            # keep_test_artifacts=True,
            # skip_test=True,
            recursive_scan=True
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