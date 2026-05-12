import os
import re

def migrate(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith((".py", ".json", ".md")):
                path = os.path.join(root, file)
                with open(path, "r") as f:
                    try:
                        content = f.read()
                    except UnicodeDecodeError:
                        continue
                
                new_content = content
                
                # 1. ~/.gemini -> ~/.gemini-manager
                # Use negative lookahead to avoid ~/.gemini-manager
                new_content = re.sub(r'~/\.gemini(?![a-zA-Z0-9_-])', '~/.gemini-manager', new_content)
                
                # 2. .gemini/ -> .gemini-manager/
                new_content = re.sub(r'\.gemini/(?![a-zA-Z0-9_-])', '.gemini-manager/', new_content)
                
                # 3. .gemini.tar.gz -> .gemini-manager.tar.gz
                new_content = new_content.replace(".gemini.tar.gz", ".gemini-manager.tar.gz")
                
                # 4. gemini.toml -> gemini-manager.toml
                # Avoid gemini-manager.toml
                new_content = re.sub(r'(?<!-)gemini\.toml', 'gemini-manager.toml', new_content)
                
                # 5. Handle directory names without trailing slash in tests
                # e.g. "2025-10-22_042211-test.gemini"
                new_content = re.sub(r'(\d{4}-\d{2}-\d{2}_\d{6}-.+)\.gemini(?=["\'])', r'\1.gemini-manager', new_content)

                # 6. \bgemini\b -> gm
                # Avoid gemini-manager, gemini_manager, and tool.gemini (as it might be needed for toml)
                # Actually, let's see if we should replace tool.gemini. 
                # If we don't, some tests might still pass if they use tool.gemini.
                # The user said "for command mocks like sys.argv = ["gemini", ...]"
                # So maybe we should be more restrictive.
                
                # For now, let's do the broad replacement but avoid -manager and _manager.
                # and avoid "tool.gemini"
                
                def replace_gemini(match):
                    full_match = match.group(0)
                    start = match.start()
                    # Check if preceded by "tool."
                    if start >= 5 and new_content[start-5:start] == "tool.":
                        return full_match
                    return "gm"

                new_content = re.sub(r'\bgemini\b(?![_-]manager)', replace_gemini, new_content)
                
                if new_content != content:
                    with open(path, "w") as f:
                        f.write(new_content)
                    print(f"Updated {path}")

migrate("src")
migrate("tests")
