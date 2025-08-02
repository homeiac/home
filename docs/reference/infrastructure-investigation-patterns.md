# Infrastructure Investigation Patterns

*Generic patterns for AI assistants to investigate homelab state across different infrastructure layers*

## Investigation Methodology

### **Phase 1: GitOps Configuration Check**
```bash
# Check if service already exists in GitOps
grep -r <service-name> gitops/
find gitops/ -name "*.yaml" -exec grep -l <service-name> {} \;
ls -la gitops/clusters/homelab/  # Available applications
```

### **Phase 2: Kubernetes Layer Investigation**
*Reference: `kubernetes-investigation-commands.md`*

### **Phase 3: Virtualization Layer Investigation**  
*Reference: `proxmox-investigation-commands.md`*

### **Phase 4: Hardware Layer Investigation**
*Reference: `hardware-investigation-commands.md`*

### **Phase 5: Network Layer Investigation**
*Reference: `network-investigation-commands-safe.md`*

## AI Assistant Investigation Flow

1. **Start Local**: Always check GitOps/documentation first
2. **Kubernetes State**: Check running services and resources
3. **Virtualization**: Verify VM/container state when needed
4. **Hardware**: Only when troubleshooting performance/capacity
5. **Network**: Only from within homelab network, never external scanning

## Safety Guidelines

### **NEVER Do:**
- Run network scanning tools from client machines
- Execute privileged commands without understanding impact
- Make assumptions about infrastructure without verification
- Skip documentation of investigation results

### **ALWAYS Do:**
- Start with read-only investigation commands
- Document findings in reference materials
- Present complete investigation results before asking questions
- Update reference patterns based on learnings

## Expected Output Format

```
Investigation Results for <service-name>:

GitOps Status: [Found/Not Found] - <details>
Kubernetes Status: [Running/Missing/Error] - <details>  
Virtualization Status: [If applicable] - <details>
Hardware Requirements: [Met/Missing] - <details>
Network Access: [Available/Missing] - <details>

Recommendation: <next steps based on findings>
```

This modular approach enables reusable investigation patterns for any homelab infrastructure setup.