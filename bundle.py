# Instead of cramming all 2000+ lines of auto2cmake in a single file, this bundler serves as a good middleground.
# The portability factor of the project remains untouched for end-users, and maintainers gain much needed organization!
import os
import re
import sys

# The order of imports should NOT be adjusted here.
# Order modifications will cause a cascading set of resolution issues. 
# A list of internal modules to strip
INTERNAL_MODULES = ['constants', 'variables', 'classes', 'utils', 'processing']

# The order of imports should NOT be adjusted here.
# Order modifications will cause a cascading set of resolution issues. 
# A list of Files to bundle
FILES = ['constants.py', 'classes.py', 'utils.py', 'processing.py', 'main.py']

OUTPUT = 'auto2cmake.py'

# Regex Breakdown:
# - ^\s* - Removes optional leading whitespace. 
# - (import|'from') - Removes import keywords
# - ({"|".join(INTERNAL_MODULES)}) - This will skip lines containing internal modules.
# - The \b (word boundary) ensures we don't match 'constants_test' if we only want 'constants'
IMPORT_PATTERN = re.compile(
    fr'^\s*(import|from)\s+({"|".join(INTERNAL_MODULES)})\b', 
    re.IGNORECASE
)

def bundle():
    print(f"Bundling {len(FILES)} files into {OUTPUT}...")
    
    try:
        with open(OUTPUT, 'w') as portable_script:
            
            for filename in FILES:
                if not os.path.exists(filename):
                    print(f"Warning: {filename} not found, skipping.")
                    continue
                
                with open(filename, 'r') as input_file:
                    portable_script.write("# Created by Auto2CMake's bundler.\n")
                    portable_script.write(f"\n# --- START OF: {filename} ---\n")
                    
                    line_has_internal_import = False
                    
                    for line in input_file:
                        # 1. Detect the start of a multi-line import block
                        if not line_has_internal_import and IMPORT_PATTERN.match(line) and '(' in line:
                            line_has_internal_import = True
                            continue # Skip the line containing 'from ... ('
                        
                        # 2. If we are currently inside an import block, skip lines until we hit ')'
                        if line_has_internal_import:
                            if ')' in line:
                                line_has_internal_import = False
                            continue # Skip all lines inside the ( ... )
                        
                        # 3. Detect and skip standard single-line internal imports
                        if IMPORT_PATTERN.match(line):
                            continue
                            
                        portable_script.write(line)
                    
                    portable_script.write(f"\n# --- END OF: {filename} ---\n")
                    
        print(f"Successfully generated: {OUTPUT}")
        
        if sys.platform in ["linux", "darwin"]:
            # 755 is the executable bit for unix file systems.
            os.chmod(OUTPUT, 0o755)
        
    except Exception as e:
        print(f"An error occurred during bundling: {e}")

if __name__ == "__main__":
    bundle()
