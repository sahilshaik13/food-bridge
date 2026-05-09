import os
import re

pages = ["donor", "ngo", "admin", "municipal", "volunteer"]

for page in pages:
    src = f"app/{page}/page.tsx"
    dest = f"app/demo/{page}/page.tsx"
    
    if not os.path.exists(src):
        print(f"Not found: {src}")
        continue
        
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Replace <RoleGuard ...> with <>
    content = re.sub(r'<RoleGuard allowedRoles=\{\[.*?\]\}>', '<>', content)
    # Replace </RoleGuard> with </>
    content = content.replace('</RoleGuard>', '</>')
    
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Created {dest}")
