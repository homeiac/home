# Investigation Discipline Methodology

**Purpose**: Prevent assumption-driven debugging and enforce systematic investigation

## Core Investigation Failures

### Assumption-Driven Investigation (ANTI-PATTERN)
❌ **Making technical assumptions** before reading documentation
❌ **Jumping to conclusions** based on keywords or partial information  
❌ **Skipping local documentation** in favor of external searches
❌ **Guessing root causes** instead of following diagnostic procedures

### Systematic Documentation-First Investigation (CORRECT PATTERN)
✅ **Read ALL local documentation** completely before any investigation
✅ **Follow documented diagnostic steps** systematically
✅ **Verify user experience** before assuming technical causes
✅ **Use tool-specific methodology** when available

## Investigation Sequence (MANDATORY)

### Phase 0: Tool-Specific Methodology Check
1. **Check for tool-specific methodology**: `docs/methodology/<tool>-investigation.md`
2. **If exists**: Follow tool-specific methodology completely
3. **If missing**: Use general methodology but create tool-specific docs afterward

### Phase 1: Official Documentation Review (MANDATORY FIRST)
1. **Read OFFICIAL tool documentation FIRST** - never start with local docs
2. **Understand tool capabilities from source** - timeline functionality, configuration options, all approaches
3. **Read complete official docs start-to-finish** - never skip sections or search for keywords first
4. **Map user requirements to official approaches** before reading local implementation details
5. **NOTE**: Official docs often describe capabilities but lack troubleshooting specifics

### Phase 2: Local Documentation Review (ONLY AFTER OFFICIAL DOCS)
1. **Find ALL local documentation** for the tool/integration
2. **Read local configuration hints** for implementation details
3. **Identify documented diagnostic procedures** and troubleshooting steps
4. **Note documented failure patterns** and their solutions
5. **Compare local approaches to official documentation** for accuracy

### Phase 2.5: Official + Local Synthesis (MANDATORY)
1. **Combine official capabilities** with local implementation specifics
2. **Map user issue to official approach** + local troubleshooting procedures  
3. **Use official docs for "what is possible"** and local docs for "how to implement/fix"
4. **Validate that local procedures align** with official tool capabilities

### Phase 3: User Experience Verification
1. **Understand exact user experience** - what did they see/experience?
2. **Match user experience** to documented failure patterns
3. **Follow documented diagnostic steps** systematically
4. **Never assume technical causes** without following documented procedures

### Phase 4: Systematic Diagnosis
1. **Execute documented diagnostic steps** in order
2. **Verify each step** before proceeding to next
3. **Document findings** at each step
4. **Only investigate beyond docs** if documented steps don't resolve

### Phase 5: MANDATORY Solution Verification (CRITICAL)
**STOP: NO SOLUTION SUGGESTIONS UNTIL VERIFICATION COMPLETE**

**ENFORCEMENT**: Any solution recommendation without completing ALL verification steps below is a methodology violation.

1. **Access Required Systems**: Get tokens/credentials to verify proposed solutions
2. **Test Solution Feasibility**: Verify the suggested approach is actually possible
3. **Validate Solution Steps**: Confirm each step works in the actual system interface
4. **Verify Solution Outcome**: Test that the solution produces expected results
5. **Document Verification Process**: Record what was verified and how

**VERIFICATION COMPLETE CHECKPOINT**: Only after running actual commands and confirming feasibility can solution be recommended.

#### Solution Verification Requirements:
- **Access Required Systems**: Get tokens/credentials for the specific tool being investigated
- **Test Solution Feasibility**: Verify the suggested approach is actually possible in that system
- **Validate Against Tool Documentation**: Confirm solution aligns with tool-specific capabilities
- **No Solution Without Verification**: NEVER suggest fixes without testing feasibility first
- **Failed Verification**: If solution can't be verified, state "requires system access to verify"
- **Tool-Specific Verification**: See `docs/methodology/<tool>-investigation.md` for tool-specific verification procedures

#### General Verification Patterns:
- **API/Interface Access**: Verify proposed UI paths and API endpoints actually exist
- **Configuration Changes**: Test that proposed configuration changes are possible and effective
- **Command Execution**: Run commands to verify they work as documented in the tool's environment
- **System State Validation**: Confirm proposed changes produce expected system state

## Documentation Reading Requirements

### Complete Documentation Review
- **Read entire files from start to finish** - not just search results or problem-specific sections
- **Understand ALL approaches and alternatives** before debugging any specific one
- **Follow cross-references** to related documentation
- **Understand context** - how docs relate to user's specific issue
- **Note diagnostic procedures** and troubleshooting sequences

### Tool-Specific Documentation Patterns
```
docs/methodology/<tool>-investigation.md    # Tool-specific investigation steps
docs/reference/<tool>-reference.md          # Tool capabilities and configuration
docs/troubleshooting/<tool>-*.md           # Known issues and solutions
docs/runbooks/<tool>-*.md                  # Step-by-step procedures
```

## Investigation Command Discipline

### Documentation-Driven Commands
✅ **Use commands from documentation** - don't invent new ones
✅ **Follow documented diagnostic sequences** 
✅ **Execute verification steps** as specified in docs
✅ **Limit investigation commands** - use docs to guide command selection

### Avoid Exploratory Investigation
❌ **Random command execution** hoping to find clues
❌ **Extensive system exploration** without documentation guidance
❌ **Multiple investigation rounds** when docs provide clear steps
❌ **Assumption-based command selection** 

## Success Metrics

### Investigation Efficiency
- **Time to diagnosis**: <30 minutes for documented issues
- **Command count**: <5 commands using documentation guidance
- **Accuracy**: Root cause matches documented patterns
- **Documentation usage**: Follow existing docs before creating new ones

### Documentation Discipline
- **Complete reading**: Read entire relevant documentation files
- **Systematic approach**: Follow documented diagnostic sequences
- **Tool-specific methodology**: Use or create tool-specific investigation guides
- **User experience focus**: Verify actual user experience vs technical assumptions

## Common Investigation Discipline Failures

### Technical Assumption Bias
- **Assuming complex technical causes** when simple configuration issues exist
- **Focusing on system internals** instead of user-facing symptoms
- **Jumping to advanced troubleshooting** without basic diagnostic steps

### Documentation Shortcuts
- **Keyword searching** instead of complete document reading from start to finish
- **Jumping to problem-specific sections** without reading entire document context
- **Skipping local docs** in favor of external documentation
- **Ignoring documented procedures** in favor of improvised investigation
- **Focusing on one approach** without understanding all available alternatives

### Experience Verification Failures
- **Assuming user experience** instead of asking for clarification
- **Technical diagnosis** without understanding actual symptoms
- **Solution implementation** without confirming user experience understanding

### CRITICAL: Premature Victory Declaration (ANTI-PATTERN)
- **Suggesting solutions without verification** - proposing fixes before testing feasibility
- **Declaring success based on documentation reading** - assuming solution works without actual testing
- **Skipping Phase 5 verification** - mentally stopping at solution planning instead of verification
- **Methodology phase incomplete** - ending investigation before all mandatory phases complete
- **Documentation ≠ Reality assumption** - believing documented approaches work without system testing

## Methodology Learning Process

### After Each Investigation Session
1. **Document investigation approach** - what worked, what didn't
2. **Update tool-specific methodology** based on findings
3. **Create missing documentation** if gaps were discovered
4. **Refine investigation discipline** based on efficiency metrics

### Investigation Pattern Recognition
- **Document common failure patterns** and their investigation approaches
- **Create tool-specific diagnostic sequences** for recurring issues
- **Build reusable investigation templates** for similar tool types
- **Establish investigation time/command benchmarks** for different issue types

This methodology enforces documentation-first investigation discipline to prevent assumption-driven debugging failures.